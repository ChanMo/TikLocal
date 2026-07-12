import hashlib
import subprocess as sp
from pathlib import Path

from PIL import Image, ImageOps

from tiklocal.paths import get_thumbnails_dir

AUDIO_EXTENSIONS = {'.mp3', '.flac', '.aac', '.m4a', '.ogg', '.opus', '.wav'}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}

class ThumbnailService:
    def __init__(self, media_root: Path, library_service=None):
        self.media_root = media_root
        self.library_service = library_service
        self.thumb_dir = get_thumbnails_dir()
        self.placeholder = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0cIDAT\x08\x99c\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\x93\x8a\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
        )

    def _get_thumb_path(self, rel_path: str) -> Path:
        key = hashlib.sha1(rel_path.encode('utf-8', errors='ignore')).hexdigest() + '.jpg'
        return self.thumb_dir / key

    def get_thumbnail(self, rel_path: str) -> tuple[Path | bytes, str]:
        """Returns (file_path_or_bytes, mimetype)"""
        thumb_path = self._get_thumb_path(rel_path)
        full_path = self.library_service.resolve_path(rel_path) if self.library_service else self.media_root / rel_path
        if thumb_path.exists():
            if not full_path or not full_path.exists():
                return thumb_path, 'image/jpeg'
            try:
                if thumb_path.stat().st_mtime_ns >= full_path.stat().st_mtime_ns:
                    return thumb_path, 'image/jpeg'
            except OSError:
                return thumb_path, 'image/jpeg'

        if full_path and full_path.exists():
            if self._generate(full_path, thumb_path):
                return thumb_path, 'image/jpeg'

        return self.placeholder, 'image/png'

    def delete_thumbnail(self, rel_path: str) -> bool:
        try:
            self._get_thumb_path(rel_path).unlink()
            return True
        except FileNotFoundError:
            return False
        except OSError:
            return False

    def _generate(self, video_path: Path, output_path: Path, timestamp: float = None) -> bool:
        suffix = video_path.suffix.lower()

        if suffix in IMAGE_EXTENSIONS:
            return self._generate_image(video_path, output_path)

        # Audio: extract embedded cover art
        if suffix in AUDIO_EXTENSIONS:
            cmd = ['ffmpeg', '-i', str(video_path), '-an', '-vframes', '1', str(output_path), '-y']
            try:
                sp.run(cmd, stdout=sp.DEVNULL, stderr=sp.DEVNULL, timeout=30)
                if output_path.exists() and output_path.stat().st_size > 0:
                    return True
            except Exception:
                pass
            return False

        candidates = [timestamp] if timestamp is not None else [5.0, 1.0, 0.1]

        for t in candidates:
            cmd = [
                'ffmpeg', '-y',
                '-ss', str(max(0.0, float(t))),
                '-i', str(video_path),
                '-frames:v', '1',
                '-vf', 'scale=-1:360:force_original_aspect_ratio=decrease',
                '-q:v', '3',
                str(output_path)
            ]
            try:
                sp.run(cmd, stdout=sp.DEVNULL, stderr=sp.DEVNULL, timeout=30)
                if output_path.exists() and output_path.stat().st_size > 0:
                    return True
            except Exception:
                continue
        return False

    @staticmethod
    def _generate_image(image_path: Path, output_path: Path) -> bool:
        try:
            with Image.open(image_path) as source:
                image = ImageOps.exif_transpose(source)
                image.thumbnail((640, 640), Image.Resampling.LANCZOS)
                if 'A' in image.getbands():
                    rgba = image.convert('RGBA')
                    background = Image.new('RGB', rgba.size, (247, 246, 242))
                    background.paste(rgba, mask=rgba.getchannel('A'))
                    image = background
                else:
                    image = image.convert('RGB')
                image.save(output_path, 'JPEG', quality=84, optimize=True, progressive=True)
            return output_path.exists() and output_path.stat().st_size > 0
        except Exception:
            return False
