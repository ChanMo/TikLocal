import datetime
import json
import subprocess as sp

from PIL import Image


def read_media_dims(payload) -> tuple[int | None, int | None]:
    if not isinstance(payload, dict):
        return None, None
    media_meta = payload.get('media_meta')
    if not isinstance(media_meta, dict):
        return None, None
    try:
        width = int(media_meta.get('width') or 0)
        height = int(media_meta.get('height') or 0)
    except (TypeError, ValueError):
        return None, None
    if width <= 0 or height <= 0:
        return None, None
    return width, height


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


def enrich_media_dimensions(records: list[dict], metadata_store, library_service) -> None:
    """Resolve dimensions for this page before serialization, with one metadata read/write batch."""
    if not records:
        return
    keys = {key for record in records for key in library_service.legacy_candidates(record['name'])}
    try:
        cached = metadata_store.get_many(keys)
    except (OSError, ValueError):
        return  # Optional dimensions must not prevent media browsing.
    updates, defaults = {}, {}
    for record in records:
        name, media_type = record['name'], record['media_type']
        width, height = read_media_dims(cached.get(name))
        if not (width and height):
            for key in library_service.legacy_candidates(name)[1:]:
                if isinstance(cached.get(key), dict):
                    defaults[name] = cached[key]
                width, height = read_media_dims(cached.get(key))
                if width and height:
                    break
            if not (width and height):
                width, height = probe_media_dims(library_service, name, media_type)
            if width and height:
                updates[name] = {'media_meta': {
                    'type': media_type, 'width': width, 'height': height,
                    'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }}
        record.update(width=width, height=height)
    if updates:
        try:
            metadata_store.update_many(updates, defaults=defaults)
        except (OSError, ValueError):
            pass  # Dimensions are usable for this response even if caching fails.
