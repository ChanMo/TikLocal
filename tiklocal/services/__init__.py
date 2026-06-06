import os
import mimetypes
import json
import math
import random
import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any

VIDEO_EXTENSIONS = {'.mp4', '.webm', '.mov', '.mkv', '.avi', '.m4v'}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
AUDIO_EXTENSIONS = {'.mp3', '.flac', '.aac', '.m4a', '.ogg', '.opus', '.wav'}
FAVORITE_FILENAME = 'favorite.json'


@dataclass(frozen=True)
class MediaSource:
    id: str
    name: str
    path: Path


@dataclass(frozen=True)
class MediaRef:
    source_id: str
    rel_path: str

    def to_uri(self) -> str:
        return f"@{self.source_id}/{self.rel_path}"


def normalize_source_id(value: Any) -> str:
    text = str(value or '').strip().lower()
    cleaned = ''.join(ch for ch in text if ch.isalnum() or ch in {'-', '_'})
    return cleaned or 'default'


def normalize_media_uri(value: Any) -> str:
    text = str(value or '').strip().replace('\\', '/')
    while text.startswith('./'):
        text = text[2:]
    return text


def build_media_sources(media_root: str | Path | None = None, raw_sources: Any = None) -> list[MediaSource]:
    sources: list[MediaSource] = []
    seen: set[str] = set()

    def add_source(source_id: Any, name: Any, path_value: Any) -> None:
        path_text = str(path_value or '').strip()
        if not path_text:
            return
        sid = normalize_source_id(source_id)
        if sid in seen:
            return
        seen.add(sid)
        sources.append(MediaSource(
            id=sid,
            name=str(name or sid).strip() or sid,
            path=Path(path_text).expanduser().resolve(),
        ))

    if raw_sources:
        if isinstance(raw_sources, dict):
            iterable = [{'id': key, 'name': key, 'path': value} for key, value in raw_sources.items()]
        else:
            iterable = raw_sources if isinstance(raw_sources, list) else []
        for item in iterable:
            if isinstance(item, dict):
                add_source(item.get('id') or item.get('name'), item.get('name') or item.get('id'), item.get('path'))

    if media_root and 'default' not in seen:
        add_source('default', 'Default', media_root)

    return sources


class LibraryService:
    def __init__(self, media_root: str | Path | None = None, media_sources: list[MediaSource] | None = None):
        self.sources = media_sources or build_media_sources(media_root)
        if not self.sources:
            self.sources = build_media_sources(media_root or '.')
        self.sources_by_id = {source.id: source for source in self.sources}
        self.default_source_id = 'default' if 'default' in self.sources_by_id else self.sources[0].id
        self.media_root = self.sources_by_id[self.default_source_id].path

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
        videos = []
        for source in self.sources:
            videos.extend(self._scan_source(source, VIDEO_EXTENSIONS, recursive=recursive))
        return sorted(videos, key=lambda p: p.stat().st_mtime, reverse=True)

    def scan_audios(self, recursive=True) -> list[Path]:
        """Scan for audio files."""
        audios = []
        for source in self.sources:
            audios.extend(self._scan_source(source, AUDIO_EXTENSIONS, recursive=recursive))
        return sorted(audios, key=lambda p: p.stat().st_mtime, reverse=True)

    def scan_images(self, recursive=True) -> list[Path]:
        """Scan for image files."""
        images = []
        for source in self.sources:
            images.extend(self._scan_source(source, IMAGE_EXTENSIONS, recursive=recursive, include_uppercase=True))
        return images

    def _scan_source(self, source: MediaSource, extensions: set[str], *, recursive: bool, include_uppercase: bool = False) -> list[Path]:
        pattern = '**/*' if recursive else '*'
        items: list[Path] = []
        if not source.path.exists() or not source.path.is_dir():
            return items
        try:
            for ext in extensions:
                items.extend(source.path.glob(f"{pattern}{ext}"))
                if include_uppercase:
                    items.extend(source.path.glob(f"{pattern}{ext.upper()}"))
        except Exception:
            return []
        return items
            
    def get_relative_path(self, path: Path) -> str:
        ref = self.ref_for_path(path)
        return ref.to_uri() if ref else str(path)

    def ref_for_path(self, path: Path) -> MediaRef | None:
        target = path.resolve()
        for source in self.sources:
            try:
                rel = str(target.relative_to(source.path.resolve())).replace('\\', '/')
                return MediaRef(source.id, rel)
            except ValueError:
                continue
        return None

    def parse_uri(self, uri: str) -> MediaRef | None:
        clean = normalize_media_uri(uri)
        if not clean:
            return None
        if clean.startswith('@'):
            source_text, sep, rel_path = clean[1:].partition('/')
            source_id = normalize_source_id(source_text)
            rel_path = normalize_media_uri(rel_path)
            if sep and source_id in self.sources_by_id and rel_path:
                return MediaRef(source_id, rel_path)
            return None
        return MediaRef(self.default_source_id, clean)

    def canonicalize_uri(self, uri: str) -> str:
        ref = self.parse_uri(uri)
        return ref.to_uri() if ref else normalize_media_uri(uri)

    def legacy_candidates(self, uri: str) -> list[str]:
        clean = normalize_media_uri(uri)
        ref = self.parse_uri(clean)
        if not ref:
            return [clean] if clean else []
        candidates = [ref.to_uri()]
        if ref.source_id == self.default_source_id:
            candidates.append(ref.rel_path)
        return list(dict.fromkeys([item for item in candidates if item]))

    def is_uri_in_set(self, uri: str, values: set[str]) -> bool:
        return any(candidate in values for candidate in self.legacy_candidates(uri))

    def canonicalize_many(self, values: set[str]) -> set[str]:
        return {self.canonicalize_uri(value) for value in values if normalize_media_uri(value)}

    def source_for_uri(self, uri: str) -> MediaSource | None:
        ref = self.parse_uri(uri)
        return self.sources_by_id.get(ref.source_id) if ref else None

    def relative_path_for_uri(self, uri: str) -> str:
        ref = self.parse_uri(uri)
        return ref.rel_path if ref else normalize_media_uri(uri)

    def canonicalize_outputs(self, rel_paths: list[str], *, source_id: str | None = None) -> list[str]:
        sid = source_id or self.default_source_id
        outputs: list[str] = []
        for rel_path in rel_paths:
            clean = normalize_media_uri(rel_path)
            if not clean:
                continue
            outputs.append(self.canonicalize_uri(clean) if clean.startswith('@') else MediaRef(sid, clean).to_uri())
        return outputs

    def resolve_source_relative_path(self, uri: str) -> tuple[MediaSource, str] | None:
        ref = self.parse_uri(uri)
        if not ref:
            return None
        source = self.sources_by_id.get(ref.source_id)
        if not source:
            return None
        return source, ref.rel_path

    def resolve_path(self, relative_path: str) -> Path | None:
        """Securely resolve a media URI to an absolute path within its media source."""
        resolved = self.resolve_source_relative_path(relative_path)
        if not resolved:
            return None
        source, rel_path = resolved
        try:
            target = (source.path / rel_path).resolve()
            target.relative_to(source.path.resolve())
            return target
        except Exception:
            return None

    def find_existing_uri(self, uri: str) -> str:
        for candidate in self.legacy_candidates(uri):
            target = self.resolve_path(candidate)
            if target and target.exists():
                return candidate
        return self.canonicalize_uri(uri)


class FavoriteService:
    def __init__(
        self,
        media_root: str | Path | None = None,
        *,
        db_path: Path | None = None,
        library_service: LibraryService | None = None,
    ):
        self.db_path = db_path or (Path(media_root) / FAVORITE_FILENAME)
        self.library_service = library_service
        self.legacy_db_path = Path(media_root) / FAVORITE_FILENAME if media_root else None
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._import_legacy_if_needed()

    def _normalize(self, filename: str) -> str:
        if self.library_service:
            return self.library_service.canonicalize_uri(filename)
        return normalize_media_uri(filename)

    def _read_raw(self, path: Path) -> set[str]:
        if not path.exists():
            return set()
        try:
            with path.open('r', encoding='utf-8') as f:
                data = json.load(f)
                return {normalize_media_uri(item) for item in data} if isinstance(data, list) else set()
        except:
            return set()

    def _import_legacy_if_needed(self) -> None:
        if not self.library_service or not self.legacy_db_path or not self.legacy_db_path.exists():
            return
        existing = self._read_raw(self.db_path)
        legacy = self._read_raw(self.legacy_db_path)
        merged = set(existing)
        for item in legacy:
            canonical = self.library_service.canonicalize_uri(item)
            if canonical:
                merged.add(canonical)
        if merged != existing:
            self.save(merged)

    def load(self) -> set[str]:
        values = self._read_raw(self.db_path)
        if self.library_service:
            return self.library_service.canonicalize_many(values)
        return values

    def save(self, favorites: set[str]):
        try:
            with self.db_path.open('w', encoding='utf-8') as f:
                json.dump(sorted(self._normalize(item) for item in favorites if normalize_media_uri(item)), f, ensure_ascii=False)
        except Exception as e:
            print(f"Failed to save favorites: {e}")

    def toggle(self, filename: str) -> bool:
        """Toggle favorite status, returns new state (True=fav, False=unfav)."""
        favs = self.load()
        key = self._normalize(filename)
        if key in favs:
            favs.remove(key)
            is_fav = False
        else:
            favs.add(key)
            is_fav = True
        self.save(favs)
        return is_fav

    def is_favorite(self, filename: str) -> bool:
        return self._normalize(filename) in self.load()


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

        for f in files:
            try:
                rel_path = self.library.get_relative_path(f)
                mtime = f.stat().st_mtime
                
                # Weight Algo: Favorites * Recency
                is_fav = self.library.is_uri_in_set(rel_path, favs)
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
