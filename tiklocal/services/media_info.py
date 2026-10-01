import json
import subprocess as sp

from PIL import Image


def probe_media_dims(library_service, name: str, media_type: str) -> tuple[int | None, int | None]:
    target = library_service.resolve_path(name)
    if not target or not target.exists():
        return None, None

    if media_type == 'image':
        try:
            with Image.open(target) as img:
                width, height = img.size
            if int(width) > 0 and int(height) > 0:
                return int(width), int(height)
        except Exception:
            return None, None
        return None, None

    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height',
            '-of', 'json',
            str(target),
        ]
        proc = sp.run(cmd, capture_output=True, text=True, timeout=8)
        if proc.returncode != 0:
            return None, None
        payload = json.loads(proc.stdout or '{}')
        streams = payload.get('streams') or []
        if not streams:
            return None, None
        stream = streams[0] if isinstance(streams[0], dict) else {}
        width = int(stream.get('width') or 0)
        height = int(stream.get('height') or 0)
        if width > 0 and height > 0:
            return width, height
    except Exception:
        return None, None
    return None, None
