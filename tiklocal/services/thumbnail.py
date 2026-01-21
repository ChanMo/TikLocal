import os
import sys
import json
import hashlib
import subprocess as sp
from pathlib import Path
from tiklocal.paths import get_thumbnails_dir, get_thumbs_map_path

class ThumbnailService:
    def __init__(self, media_root: Path):
        self.media_root = media_root
        self.thumb_dir = get_thumbnails_dir()
        self.thumb_map_file = get_thumbs_map_path()
        self.placeholder = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0cIDAT\x08\x99c\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\x93\x8a\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
        )

    def _get_thumb_path(self, rel_path: str) -> Path:
        key = hashlib.sha1(rel_path.encode('utf-8', errors='ignore')).hexdigest() + '.jpg'
        return self.thumb_dir / key

    def get_thumbnail(self, rel_path: str) -> tuple[Path | bytes, str]:
        """Returns (file_path_or_bytes, mimetype)"""
        thumb_path = self._get_thumb_path(rel_path)
        
        # Return existing
        if thumb_path.exists():
            return thumb_path, 'image/jpeg'

        # Generate new
        full_path = self.media_root / rel_path
        if full_path.exists():
            if self._generate(full_path, thumb_path):
                return thumb_path, 'image/jpeg'
        
        return self.placeholder, 'image/png'

    def _generate(self, video_path: Path, output_path: Path, timestamp: float = None) -> bool:
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
