import os
import mimetypes
import json
import math
import random
import datetime
from pathlib import Path

VIDEO_EXTENSIONS = {'.mp4', '.webm', '.mov', '.mkv', '.avi', '.m4v'}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
FAVORITE_FILENAME = 'favorite.json'

class LibraryService:
    def __init__(self, media_root: str):
        self.media_root = Path(media_root)

    def _is_video(self, path: Path) -> bool:
        if path.suffix.lower() in VIDEO_EXTENSIONS:
            return True
        try:
            mime = mimetypes.guess_type(path.name)[0]
            return mime and mime.startswith('video/')
        except:
            return False

    def _is_image(self, path: Path) -> bool:
        if path.suffix.lower() in IMAGE_EXTENSIONS:
            return True
        try:
            mime = mimetypes.guess_type(path.name)[0]
            return mime and mime.startswith('image/')
        except:
            return False

    def scan_videos(self, recursive=True) -> list[Path]:
        """Scan for video files."""
        # Using glob for better performance than os.scandir recursive manual loop
        pattern = '**/*' if recursive else '*'
        videos = []
        try:
            for ext in VIDEO_EXTENSIONS:
                videos.extend(self.media_root.glob(f"{pattern}{ext}"))
            # Sort by modification time (newest first) by default
            return sorted(videos, key=lambda p: p.stat().st_mtime, reverse=True)
        except Exception:
            return []

    def scan_images(self, recursive=True) -> list[Path]:
        """Scan for image files."""
        pattern = '**/*' if recursive else '*'
        images = []
        try:
            for ext in IMAGE_EXTENSIONS:
                images.extend(self.media_root.glob(f"{pattern}{ext}"))
                images.extend(self.media_root.glob(f"{pattern}{ext.upper()}"))
            return images
        except Exception:
            return []
            
    def get_relative_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.media_root))
        except ValueError:
            return str(path)

    def resolve_path(self, relative_path: str) -> Path | None:
        """Securely resolve a relative path to an absolute path within media root."""
        try:
            # Unquote in case it's URL encoded, though usually handled by Flask
            target = (self.media_root / relative_path).resolve()
            if not str(target).startswith(str(self.media_root.resolve())):
                return None
            return target
        except Exception:
            return None


class FavoriteService:
    def __init__(self, media_root: str):
        self.db_path = Path(media_root) / FAVORITE_FILENAME

    def load(self) -> set[str]:
        if not self.db_path.exists():
            return set()
        try:
            with self.db_path.open('r', encoding='utf-8') as f:
                data = json.load(f)
                return set(data) if isinstance(data, list) else set()
        except:
            return set()

    def save(self, favorites: set[str]):
        try:
            with self.db_path.open('w', encoding='utf-8') as f:
                json.dump(list(favorites), f)
        except Exception as e:
            print(f"Failed to save favorites: {e}")

    def toggle(self, filename: str) -> bool:
        """Toggle favorite status, returns new state (True=fav, False=unfav)."""
        favs = self.load()
        if filename in favs:
            favs.remove(filename)
            is_fav = False
        else:
            favs.add(filename)
            is_fav = True
        self.save(favs)
        return is_fav

    def is_favorite(self, filename: str) -> bool:
        return filename in self.load()


class RecommendService:
    def __init__(self, library_service: LibraryService, favorite_service: FavoriteService):
        self.library = library_service
        self.favorites = favorite_service

    def get_weighted_selection(self, file_type='video', limit=20, seed=None) -> list[str]:
        """Get intelligent random selection of files."""
        # 1. Get Candidates
        if file_type == 'video':
            files = self.library.scan_videos()
        else:
            files = self.library.scan_images()
        
        if not files:
            return []

        # 2. Calculate Weights
        favs = self.favorites.load()
        now = datetime.datetime.now()
        weighted_pool = []
        root = self.library.media_root

        for f in files:
            try:
                rel_path = str(f.relative_to(root))
                mtime = f.stat().st_mtime
                
                # Weight Algo: Favorites * Recency
                is_fav = rel_path in favs
                base_score = 3.0 if is_fav else 1.0
                
                age_days = max((now - datetime.datetime.fromtimestamp(mtime)).total_seconds() / 86400, 0.0)
                # Decay: newer files have higher probability
                time_score = math.exp(-age_days / 90.0) 
                
                weight = base_score * (0.1 + time_score)
                weighted_pool.append((rel_path, weight))
            except Exception:
                continue

        # 3. Weighted Random Sample
        rng = random.Random(seed) if seed else random
        result = []
        
        # Optimization: If requesting all or more than available, just shuffle and return
        if limit >= len(weighted_pool):
            result = [p[0] for p in weighted_pool]
            rng.shuffle(result)
            return result

        # Weighted selection logic
        pool = weighted_pool[:]
        while pool and len(result) < limit:
            total_weight = sum(w for _, w in pool)
            if total_weight <= 0:
                break
            
            pick = rng.random() * total_weight
            current = 0
            for i, (path, weight) in enumerate(pool):
                current += weight
                if current >= pick:
                    result.append(path)
                    pool.pop(i)
                    break
        
        return result
