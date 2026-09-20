"""Shared media links and display fields; no IO or browsing policy."""

from urllib.parse import quote


def media_urls(uri: str) -> dict[str, str]:
    return {
        'media_url': f"/media/{quote(uri, safe='/')}",
        'thumb_url': f"/thumb?uri={quote(uri)}",
    }


def build_feed_media_item(name: str, media_type: str) -> dict[str, str]:
    encoded = quote(name)
    detail_url = f"/detail/{encoded}" if media_type == 'video' else f"/image?uri={encoded}"
    return {
        'type': media_type,
        'name': name,
        **media_urls(name),
        'detail_url': detail_url,
    }


def serialize_library_item(record: dict) -> dict:
    name = str(record.get('name') or '')
    media_type = str(record.get('media_type') or 'video')
    return {
        **build_feed_media_item(name, media_type),
        'mtime_ts': float(record.get('mtime_ts') or 0),
        'size_bytes': int(record.get('size_bytes') or 0),
        'width': record.get('width'),
        'height': record.get('height'),
    }
