import datetime
import json
import random
import subprocess as sp
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from PIL import Image


def build_feed_media_item(name: str, media_type: str) -> dict[str, str]:
    encoded = quote(name)
    detail_url = f"/detail/{encoded}" if media_type == 'video' else f"/image?uri={encoded}"
    media_url = f"/media?uri={encoded}"
    return {
        'type': media_type,
        'name': name,
        'media_url': media_url,
        'thumb_url': f"/thumb?uri={encoded}" if media_type == 'video' else media_url,
        'detail_url': detail_url,
    }


def collect_source_media_groups(
    records: list[dict],
    download_source_store,
    build_item: Callable[[str, str], dict[str, str]] = build_feed_media_item,
) -> list[dict]:
    records_by_name = {str(item.get('name') or ''): item for item in records if item.get('name')}
    source_map = download_source_store.get_many(list(records_by_name.keys()))
    groups_by_source: dict[str, dict] = {}
    groups_by_job: dict[str, dict] = {}

    for name, source_meta in source_map.items():
        if not isinstance(source_meta, dict):
            continue
        record = records_by_name.get(name)
        if not record:
            continue

        normalized_item = {
            'name': name,
            'media_type': str(record.get('media_type') or ''),
            'sort_ts': float(record.get('mtime_ts') or 0),
        }

        source_url = str(source_meta.get('source_url_display') or source_meta.get('source_url_raw') or '').strip()
        if source_url:
            group = groups_by_source.setdefault(source_url, {
                'key': source_url,
                'source_domain': str(source_meta.get('source_domain') or '').strip(),
                'created_at': str(source_meta.get('created_at') or '').strip(),
                'items': [],
            })
            group['items'].append(normalized_item)
            if str(source_meta.get('created_at') or '').strip() > str(group.get('created_at') or ''):
                group['created_at'] = str(source_meta.get('created_at') or '').strip()

        job_id = str(source_meta.get('job_id') or '').strip()
        if job_id:
            group = groups_by_job.setdefault(job_id, {
                'key': job_id,
                'source_domain': str(source_meta.get('source_domain') or '').strip(),
                'created_at': str(source_meta.get('created_at') or '').strip(),
                'items': [],
            })
            group['items'].append(normalized_item)
            if str(source_meta.get('created_at') or '').strip() > str(group.get('created_at') or ''):
                group['created_at'] = str(source_meta.get('created_at') or '').strip()

    results: list[dict] = []
    seen_group_signatures: set[tuple[str, ...]] = set()
    for group in list(groups_by_source.values()) + list(groups_by_job.values()):
        entries = group.get('items') or []
        unique_names = sorted({str(item.get('name') or '') for item in entries if item.get('name')})
        if len(unique_names) < 2:
            continue
        signature = tuple(unique_names)
        if signature in seen_group_signatures:
            continue
        seen_group_signatures.add(signature)

        sorted_items = sorted(
            [item for item in entries if item.get('name') in records_by_name],
            key=lambda item: (float(item.get('sort_ts') or 0), str(item.get('name') or '')),
            reverse=True,
        )
        domain = str(group.get('source_domain') or '').strip()
        results.append({
            'source_domain': domain,
            'created_at': str(group.get('created_at') or ''),
            'items': [
                build_item(str(item['name']), str(item['media_type']))
                for item in sorted_items[:8]
            ],
        })

    results.sort(
        key=lambda item: (
            str(item.get('created_at') or ''),
            len(item.get('items') or []),
        ),
        reverse=True,
    )
    return results


def collect_library_records(
    library_service,
    favorite_service,
    image_extensions: set[str],
    *,
    favorites_only: bool = False,
) -> list[dict]:
    favorite_set = favorite_service.load()
    all_paths = library_service.scan_videos() + library_service.scan_images()

    seen_rel: set[str] = set()
    records_by_identity: dict[tuple, dict] = {}

    for path in all_paths:
        try:
            rel = library_service.get_relative_path(path)
            if rel in seen_rel:
                continue
            seen_rel.add(rel)

            stat = path.stat()
            identity = (int(getattr(stat, 'st_dev', 0)), int(getattr(stat, 'st_ino', 0)))
            if identity == (0, 0):
                identity = ('resolved', str(path.resolve()))

            media_type = 'image' if path.suffix.lower() in image_extensions else 'video'
            candidate = {
                'name': rel,
                'media_type': media_type,
                'mtime_ts': float(stat.st_mtime),
                'size_bytes': int(stat.st_size),
                'is_favorite': rel in favorite_set,
            }

            existing = records_by_identity.get(identity)
            if existing is None:
                records_by_identity[identity] = candidate
                continue

            if candidate['is_favorite'] and not existing['is_favorite']:
                records_by_identity[identity] = candidate
                continue

            if (
                candidate['mtime_ts'] > existing['mtime_ts']
                or (
                    candidate['mtime_ts'] == existing['mtime_ts']
                    and candidate['name'] < existing['name']
                )
            ):
                records_by_identity[identity] = candidate
        except Exception:
            continue

    records = list(records_by_identity.values())
    if favorites_only:
        records = [item for item in records if item.get('is_favorite')]

    records.sort(key=lambda item: (item['mtime_ts'], item['name']), reverse=True)
    return records


def build_theme_strip_candidates(
    records: list[dict],
    download_history_store,
    build_item: Callable[[str, str], dict[str, str]] = build_feed_media_item,
) -> list[dict]:
    records_by_name = {str(item.get('name') or ''): item for item in records if item.get('name')}
    candidates: list[dict] = []

    favorite_records = [
        item for item in records
        if item.get('is_favorite') and item.get('media_type') in {'video', 'image'}
    ]
    favorite_records.sort(key=lambda item: item.get('mtime_ts') or 0, reverse=True)
    favorite_items = [
        build_item(item['name'], item['media_type'])
        for item in favorite_records[:8]
    ]
    if len(favorite_items) >= 3:
        candidates.append({
            'type': 'theme_strip',
            'name': 'theme:favorite-picks',
            'title': '收藏精选',
            'subtitle': '快速跳去收藏页继续看。',
            'target_url': '/favorite',
            'target_label': '打开收藏',
            'items': favorite_items,
        })

    history = download_history_store.get()
    recent_download_names: list[str] = []
    seen_names: set[str] = set()
    sorted_history = sorted(
        [item for item in history if isinstance(item, dict)],
        key=lambda item: str(item.get('created_at') or ''),
        reverse=True,
    )
    for job in sorted_history:
        if str(job.get('status') or '') != 'success':
            continue
        raw_files = job.get('output_files_rel')
        if not isinstance(raw_files, list):
            continue
        for value in raw_files:
            name = str(value or '').strip().replace('\\', '/')
            while name.startswith('./'):
                name = name[2:]
            if not name or name in seen_names or name not in records_by_name:
                continue
            seen_names.add(name)
            recent_download_names.append(name)
            if len(recent_download_names) >= 8:
                break
        if len(recent_download_names) >= 8:
            break

    download_items = [
        build_item(name, str(records_by_name[name]['media_type']))
        for name in recent_download_names
    ]
    if len(download_items) >= 3:
        candidates.append({
            'type': 'theme_strip',
            'name': 'theme:recent-downloads',
            'title': '最近下载',
            'subtitle': '快速跳去媒体库继续看。',
            'target_url': '/library',
            'target_label': '打开媒体库',
            'items': download_items,
        })

    return candidates


def read_media_dims_from_metadata(metadata_store, name: str) -> tuple[int | None, int | None]:
    payload = metadata_store.get(name)
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


def save_media_dims_to_metadata(metadata_store, name: str, media_type: str, width: int, height: int) -> None:
    if width <= 0 or height <= 0:
        return
    current = metadata_store.get(name)
    payload = dict(current) if isinstance(current, dict) else {}
    payload['media_meta'] = {
        'type': media_type,
        'width': int(width),
        'height': int(height),
        'updated_at': datetime.datetime.utcnow().isoformat() + 'Z',
    }
    metadata_store.set(name, payload, overwrite=True)


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


def get_or_probe_media_dims(metadata_store, library_service, name: str, media_type: str) -> tuple[int | None, int | None]:
    width, height = read_media_dims_from_metadata(metadata_store, name)
    if width and height:
        return width, height
    width, height = probe_media_dims(library_service, name, media_type)
    if width and height:
        save_media_dims_to_metadata(metadata_store, name, media_type, width, height)
    return width, height


def serialize_library_item(record: dict, metadata_store, library_service) -> dict:
    name = str(record.get('name') or '')
    media_type = str(record.get('media_type') or 'video')
    width, height = get_or_probe_media_dims(metadata_store, library_service, name, media_type)
    encoded = quote(name)
    media_url = f"/media?uri={encoded}"
    return {
        'name': name,
        'type': media_type,
        'media_url': media_url,
        'detail_url': f"/image?uri={encoded}" if media_type == 'image' else f"/detail/{encoded}",
        'thumb_url': media_url if media_type == 'image' else f"/thumb?uri={encoded}",
        'mtime_ts': float(record.get('mtime_ts') or 0),
        'size_bytes': int(record.get('size_bytes') or 0),
        'width': int(width) if width else None,
        'height': int(height) if height else None,
    }


def collect_collection_records(
    collection_id: str,
    collection_store,
    favorite_service,
    library_service,
    image_extensions: set[str],
) -> tuple[dict | None, list[dict]]:
    collection = collection_store.get(collection_id)
    if not collection:
        return None, []

    favorites = favorite_service.load()
    uris = collection_store.list_item_uris(collection_id, newest_first=True)
    records: list[dict] = []
    seen: set[str] = set()
    for uri in uris:
        if uri in seen:
            continue
        seen.add(uri)
        target = library_service.resolve_path(uri)
        if not target or not target.exists():
            continue
        try:
            stat = target.stat()
        except OSError:
            continue
        media_type = 'image' if target.suffix.lower() in image_extensions else 'video'
        records.append({
            'name': uri,
            'media_type': media_type,
            'mtime_ts': float(stat.st_mtime),
            'size_bytes': int(stat.st_size),
            'is_favorite': uri in favorites,
        })
    return collection, records


def collection_cover_payload(collection: dict, collection_store, library_service, image_extensions: set[str]) -> tuple[str, str]:
    cover_uri = str(collection.get('cover_uri') or '').strip()
    if cover_uri:
        target = library_service.resolve_path(cover_uri)
        if target and target.exists():
            media_type = 'image' if target.suffix.lower() in image_extensions else 'video'
            return cover_uri, media_type

    uris = collection_store.list_item_uris(str(collection.get('id') or ''), newest_first=True)
    for uri in uris:
        target = library_service.resolve_path(uri)
        if not target or not target.exists():
            continue
        media_type = 'image' if target.suffix.lower() in image_extensions else 'video'
        return uri, media_type
    return '', ''


def serialize_collection_summary(collection: dict, collection_store, library_service, image_extensions: set[str]) -> dict:
    collection_id = str(collection.get('id') or '')
    cover_uri, cover_type = collection_cover_payload(collection, collection_store, library_service, image_extensions)
    cover_encoded = quote(cover_uri, safe='') if cover_uri else ''
    cover_media_url = f"/media?uri={cover_encoded}" if cover_uri else ''
    return {
        'id': collection_id,
        'name': str(collection.get('name') or ''),
        'description': str(collection.get('description') or ''),
        'item_count': int(collection.get('item_count') or 0),
        'cover_uri': cover_uri,
        'cover_type': cover_type,
        'cover_media_url': cover_media_url,
        'detail_url': f"/collection/{quote(collection_id, safe='')}" if collection_id else '#',
        'created_at': str(collection.get('created_at') or ''),
        'updated_at': str(collection.get('updated_at') or ''),
    }


def apply_library_mode(records: list[dict], *, mode: str, min_mb: int, seed: str) -> list[dict]:
    if mode == 'image_random':
        image_records = [item for item in records if item.get('media_type') == 'image']
        rng = random.Random(seed)
        rng.shuffle(image_records)
        return image_records
    if mode == 'video_latest':
        return [item for item in records if item.get('media_type') == 'video']
    if mode == 'big_files':
        min_bytes = max(1, int(min_mb)) * 1024 * 1024
        video_records = [item for item in records if item.get('media_type') == 'video' and int(item.get('size_bytes') or 0) >= min_bytes]
        video_records.sort(key=lambda item: (item['size_bytes'], item['mtime_ts'], item['name']), reverse=True)
        return video_records
    return records


def build_library_page(
    *,
    favorites_only: bool = False,
    mode: str = 'all',
    offset: int = 0,
    limit: int = 48,
    min_mb: int = 50,
    seed: str = '',
    collection_id: str = '',
    collect_collection_records_fn: Callable[[str], tuple[dict | None, list[dict]]],
    collect_library_records_fn: Callable[..., list[dict]],
    apply_library_mode_fn: Callable[..., list[dict]] = apply_library_mode,
    serialize_library_item_fn: Callable[[dict], dict],
) -> dict:
    records: list[dict] = []
    if collection_id:
        _, records = collect_collection_records_fn(collection_id)
    else:
        records = collect_library_records_fn(favorites_only=favorites_only)
        records = apply_library_mode_fn(records, mode=mode, min_mb=min_mb, seed=seed)
    total = len(records)
    start = max(0, int(offset))
    safe_limit = max(12, min(int(limit), 96))
    end = start + safe_limit
    items = [serialize_library_item_fn(record) for record in records[start:end]]
    return {
        'items': items,
        'total': total,
        'offset': start,
        'limit': safe_limit,
        'next_offset': end,
        'has_more': end < total,
        'seed': seed,
    }


def build_mix_feed_page(
    *,
    page: int,
    size: int,
    seed: str,
    recommend_service,
    collect_library_records_fn: Callable[..., list[dict]],
    build_theme_strip_candidates_fn: Callable[[list[dict]], list[dict]],
    collect_source_media_groups_fn: Callable[[list[dict]], list[dict]],
    build_feed_media_item_fn: Callable[[str, str], dict[str, str]] = build_feed_media_item,
) -> dict:
    video_ratio = 4
    image_ratio = 1

    ratio_total = video_ratio + image_ratio
    end = page * size
    start = max(0, end - size)
    request_window = end + size
    video_need = max(size, int(request_window * (video_ratio / ratio_total)) + video_ratio * 2)
    image_need = max(size, int(request_window * (image_ratio / ratio_total)) + image_ratio * 2)

    videos = recommend_service.get_weighted_selection(
        file_type='video',
        limit=video_need,
        seed=f"{seed}:video",
    )
    images = recommend_service.get_weighted_selection(
        file_type='image',
        limit=image_need,
        seed=f"{seed}:image",
    )

    target_image_prob = image_ratio / max(1, ratio_total)
    max_video_streak = 6
    max_image_streak = 2
    rng = random.Random(f"{seed}:mix")

    mixed: list[tuple[str, str]] = []
    seen: set[str] = set()
    vi = 0
    ii = 0
    used_video = 0
    used_image = 0
    video_streak = 0
    image_streak = 0

    def pick_next_available(kind: str) -> tuple[str, str]:
        nonlocal vi, ii
        if kind == 'video':
            while vi < len(videos):
                name = videos[vi]
                vi += 1
                if name:
                    return 'video', name
            return '', ''
        while ii < len(images):
            name = images[ii]
            ii += 1
            if name:
                return 'image', name
        return '', ''

    while len(mixed) < request_window and (vi < len(videos) or ii < len(images)):
        if video_streak >= max_video_streak and ii < len(images):
            want_type = 'image'
        elif image_streak >= max_image_streak and vi < len(videos):
            want_type = 'video'
        else:
            total_used = used_video + used_image
            current_image_ratio = (used_image / total_used) if total_used > 0 else target_image_prob
            correction = (target_image_prob - current_image_ratio) * 0.65
            p_image = max(0.05, min(0.5, target_image_prob + correction))
            want_type = 'image' if rng.random() < p_image else 'video'

        chosen_type, chosen_name = pick_next_available(want_type)
        if not chosen_name:
            fallback = 'video' if want_type == 'image' else 'image'
            chosen_type, chosen_name = pick_next_available(fallback)

        if not chosen_name or chosen_name in seen:
            continue
        seen.add(chosen_name)
        mixed.append((chosen_type, chosen_name))
        if chosen_type == 'video':
            used_video += 1
            video_streak += 1
            image_streak = 0
        else:
            used_image += 1
            image_streak += 1
            video_streak = 0

    records = collect_library_records_fn(favorites_only=False)
    theme_candidates = build_theme_strip_candidates_fn(records)
    source_groups = collect_source_media_groups_fn(records)
    image_group_candidate = None
    image_group_names: set[str] = set()
    for group in source_groups:
        group_items = [item for item in (group.get('items') or []) if item.get('type') == 'image']
        if len(group_items) < 2:
            continue
        image_group_candidate = {
            'type': 'image_group',
            'name': f"group:{group_items[0]['name']}",
            'title': '原始图集',
            'subtitle': '左右切换查看同一帖子里的图片。',
            'items': group_items,
        }
        image_group_names = {str(item.get('name') or '') for item in group_items}
        break

    mixed_entries: list[dict] = [
        {'type': media_type, 'name': name}
        for media_type, name in mixed
    ]
    if image_group_candidate and mixed_entries:
        mixed_entries = [
            entry for entry in mixed_entries
            if not (entry.get('type') == 'image' and str(entry.get('name') or '') in image_group_names)
        ]
        group_rng = random.Random(f"{seed}:image-group")
        insert_floor = min(2, len(mixed_entries))
        insert_ceil = min(max(insert_floor, 6), len(mixed_entries))
        insert_at = insert_floor if insert_ceil <= insert_floor else group_rng.randint(insert_floor, insert_ceil)
        mixed_entries.insert(insert_at, image_group_candidate)
    if page == 1 and theme_candidates and mixed_entries:
        theme_rng = random.Random(f"{seed}:theme-strip")
        candidate = theme_rng.choice(theme_candidates)
        insert_floor = min(6, len(mixed_entries))
        insert_ceil = min(max(insert_floor, 10), len(mixed_entries))
        insert_at = insert_floor if insert_ceil <= insert_floor else theme_rng.randint(insert_floor, insert_ceil)
        mixed_entries.insert(insert_at, candidate)

    page_items = mixed_entries[start:end]
    items = []
    for entry in page_items:
        item_type = str(entry.get('type') or '')
        if item_type == 'theme_strip':
            target_url = str(entry.get('target_url') or '').strip()
            items.append({
                'type': 'theme_strip',
                'name': str(entry.get('name') or 'theme:strip'),
                'title': str(entry.get('title') or '').strip(),
                'subtitle': str(entry.get('subtitle') or '').strip(),
                'target_url': target_url,
                'target_label': str(entry.get('target_label') or '').strip(),
                'items': [
                    {
                        'type': child.get('type'),
                        'name': child.get('name'),
                        'media_url': child.get('media_url'),
                        'thumb_url': child.get('thumb_url'),
                        'detail_url': child.get('detail_url'),
                        'focus_url': f"{target_url}?focus={quote(str(child.get('name') or ''), safe='')}" if target_url and child.get('name') else target_url,
                    }
                    for child in (entry.get('items') or [])
                    if isinstance(child, dict) and child.get('name')
                ],
            })
            continue
        if item_type == 'image_group':
            items.append({
                'type': 'image_group',
                'name': str(entry.get('name') or 'group:image'),
                'title': str(entry.get('title') or '').strip(),
                'subtitle': str(entry.get('subtitle') or '').strip(),
                'items': [
                    {
                        'type': child.get('type'),
                        'name': child.get('name'),
                        'media_url': child.get('media_url'),
                        'thumb_url': child.get('thumb_url'),
                        'detail_url': child.get('detail_url'),
                    }
                    for child in (entry.get('items') or [])
                    if isinstance(child, dict) and child.get('name')
                ],
            })
            continue

        name = str(entry.get('name') or '')
        if not name or item_type not in {'video', 'image'}:
            continue
        items.append(build_feed_media_item_fn(name, item_type))

    return {
        'items': items,
        'page': page,
        'has_more': len(mixed_entries) > end,
        'seed': seed,
    }


def normalize_collection_mutation_uris(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw:
        value = str(item or '').strip().replace('\\', '/')
        while value.startswith('./'):
            value = value[2:]
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
        if len(normalized) >= 200:
            break
    return normalized


def build_library_template_context(
    *,
    menu: str,
    scope: str,
    collection_id: str,
    collection_name: str,
    active_mode: str,
    min_mb: int,
    empty_message: str,
    initial_page: dict,
) -> dict:
    return {
        'menu': menu,
        'scope': scope,
        'collection_id': collection_id,
        'collection_name': collection_name,
        'active_mode': active_mode,
        'mode_seed': initial_page['seed'],
        'min_mb': min_mb,
        'empty_message': empty_message,
        'initial_items': initial_page['items'],
        'initial_has_more': initial_page['has_more'],
        'initial_offset': initial_page['offset'],
        'initial_next_offset': initial_page['next_offset'],
        'page_size': initial_page['limit'],
    }
