import hashlib
import io
import os
import tempfile
import subprocess as sp
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from tiklocal.paths import get_thumbnails_dir
from tiklocal.services.library import LibraryService, AUDIO_EXTENSIONS, IMAGE_EXTENSIONS


class ThumbnailService:
    def __init__(self, media_root: Path, library_service=None):
        self.media_root = media_root
        self.library = library_service or LibraryService(media_root)
        self.thumb_dir = get_thumbnails_dir()
        self.placeholder = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0cIDAT\x08\x99c\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\x93\x8a\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
        )

    def cache_path(self, uri: str) -> Path:
        canonical = self.library.canonicalize_uri(uri)
        return self._path_for_key(canonical)

    def _path_for_key(self, key: str) -> Path:
        return self.thumb_dir / (hashlib.sha1(key.encode('utf-8')).hexdigest() + '.jpg')

    def cached_thumbnail(self, uri: str) -> Path | None:
        """Reuse valid canonical caches and legacy caches belonging to the default source."""
        source_path = self.library.resolve_path(uri)
        if source_path is None:
            return None
        for key in self.library.legacy_candidates(self.library.canonicalize_uri(uri)):
            cached = self._path_for_key(key)
            try:
                if not cached.is_file() or cached.stat().st_size == 0:
                    continue
                if not source_path.exists():
                    # Offline sources may display an existing canonical preview.
                    return cached if key.startswith('@') else None
                if cached.stat().st_mtime_ns >= source_path.stat().st_mtime_ns:
                    return cached
            except OSError:
                continue
        return None

    def get_thumbnail(self, uri: str) -> tuple[Path | bytes, str]:
        """Return a cached or generated thumbnail, falling back to a placeholder."""
        thumbnail = self.cached_thumbnail(uri) or self.generate_thumbnail(uri)
        return (thumbnail, 'image/jpeg') if thumbnail else (self.placeholder, 'image/png')

    def get_radio_artwork(self, uri: str) -> tuple[Path | bytes, str]:
        if uri:
            path, mimetype = self.get_thumbnail(uri)
            if not isinstance(path, bytes):
                return path, mimetype
        return radio_artwork_bytes(uri or 'radio'), 'image/png'

    def cache_stats(self) -> dict:
        files = list(self.thumb_dir.glob('*.jpg'))
        size = sum(path.stat().st_size for path in files if path.exists())
        return {'count': len(files), 'size_mb': round(size / (1024 * 1024), 2)}

    def clear_cache(self) -> dict:
        deleted_count = 0
        freed_bytes = 0
        for path in self.thumb_dir.glob('*.jpg'):
            try:
                freed_bytes += path.stat().st_size
                path.unlink()
                deleted_count += 1
            except OSError:
                continue
        return {'deleted_count': deleted_count, 'freed_mb': round(freed_bytes / (1024 * 1024), 2)}

    def generate_thumbnail(
        self, uri: str, *, timestamp: float | None = None, auto_timestamp: bool = False,
    ) -> Path | None:
        source = self.library.resolve_path(uri)
        if source is None or not source.is_file():
            return None
        output = self.cache_path(uri)
        # A failed or concurrent generation must not publish a partial cache file.
        try:
            with tempfile.TemporaryDirectory(dir=self.thumb_dir) as directory:
                temporary = Path(directory) / 'thumbnail.jpg'
                if self._generate(source, temporary, timestamp, auto_timestamp=auto_timestamp):
                    os.replace(temporary, output)
                    return output
        except OSError:
            return None
        return None

    def delete_thumbnail(self, uri: str) -> bool:
        removed = False
        for key in self.library.legacy_candidates(self.library.canonicalize_uri(uri)):
            try:
                self._path_for_key(key).unlink()
                removed = True
            except OSError:
                continue
        return removed

    @staticmethod
    def _probe_duration(path: Path) -> float | None:
        try:
            output = sp.check_output([
                'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1', str(path),
            ], stderr=sp.DEVNULL, timeout=10)
            duration = float(output.decode().strip())
            return duration if duration > 0 else None
        except (OSError, sp.SubprocessError, ValueError):
            return None

    def _generate(self, video_path: Path, output_path: Path, timestamp: float | None, *, auto_timestamp: bool) -> bool:
        suffix = video_path.suffix.lower()

        if suffix in IMAGE_EXTENSIONS:
            return self._generate_image(video_path, output_path)

        # Audio: extract embedded cover art
        if suffix in AUDIO_EXTENSIONS:
            cmd = ['ffmpeg', '-i', str(video_path), '-an', '-vframes', '1', str(output_path), '-y']
            try:
                result = sp.run(cmd, stdout=sp.DEVNULL, stderr=sp.DEVNULL, timeout=30)
                if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
                    return True
            except (OSError, sp.SubprocessError):
                pass
            return False

        candidates = [5.0, 1.0, 0.1]
        if timestamp is not None:
            candidates = [timestamp]
        elif auto_timestamp:
            duration = self._probe_duration(video_path)
            if duration and duration > 1:
                candidates.insert(0, max(1.0, min(duration - 1.0, duration * 0.2)))

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
                result = sp.run(cmd, stdout=sp.DEVNULL, stderr=sp.DEVNULL, timeout=30)
                if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
                    return True
            except (OSError, sp.SubprocessError):
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


def radio_artwork_bytes(uri: str) -> bytes:
    palettes = [
        ("#466b61", "#a88756", "#d7d2c4"),
        ("#5c6750", "#b18462", "#d8d3c8"),
        ("#57707a", "#9b8257", "#d2d5ce"),
        ("#675f82", "#9b8b5b", "#d7d1c0"),
        ("#72634e", "#5f8174", "#d8d4c7"),
        ("#4f6f7e", "#a36f5d", "#d5d0c4"),
    ]
    palette = palettes[sum(uri.encode("utf-8", errors="ignore")) % len(palettes)]
    size = 512
    image = Image.new("RGB", (size, size), palette[2])
    draw = ImageDraw.Draw(image, "RGBA")

    for radius in range(size // 2, 24, -8):
        index = (radius // 8) % 2
        color = palette[index]
        alpha = 18 if index else 26
        inset = size // 2 - radius
        draw.ellipse(
            (inset, inset, size - inset, size - inset),
            fill=color + f"{alpha:02x}",
        )

    draw.ellipse((42, 42, size - 42, size - 42), outline=(36, 36, 31, 38), width=2)
    draw.ellipse((112, 112, size - 112, size - 112), outline=(70, 107, 97, 34), width=2)
    draw.ellipse(
        (182, 182, size - 182, size - 182),
        fill=palette[0],
        outline=(255, 255, 255, 56),
        width=2,
    )
    draw.ellipse(
        (220, 220, size - 220, size - 220),
        fill=palette[2],
        outline=(36, 36, 31, 30),
        width=1,
    )

    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
