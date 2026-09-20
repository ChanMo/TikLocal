"""Flow HTTP entry points and media/card composition."""

import random
from urllib.parse import quote

from flask import render_template, request

from tiklocal.web import read_int_arg
from tiklocal.web.media_payloads import build_feed_media_item


def legacy_media_key(uri: str) -> str:
    text = str(uri or '').strip().replace('\\', '/')
    if text.startswith('@'):
        _, sep, rel_path = text[1:].partition('/')
        if sep and rel_path:
            return rel_path
    return text


def collect_source_media_groups(
    records: list[dict],
    download_source_store,
) -> list[dict]:
    records_by_name = {str(item.get('name') or ''): item for item in records if item.get('name')}
    record_lookup = dict(records_by_name)
    for name, record in records_by_name.items():
        record_lookup.setdefault(legacy_media_key(name), record)
    source_map = download_source_store.get_many(list(record_lookup))
    groups_by_source: dict[str, dict] = {}
    groups_by_job: dict[str, dict] = {}

    for name, source_meta in source_map.items():
        if not isinstance(source_meta, dict):
            continue
        record = record_lookup.get(name)
        if not record:
            continue
        canonical_name = str(record.get('name') or name)

        normalized_item = {
            'name': canonical_name,
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
                build_feed_media_item(str(item['name']), str(item['media_type']))
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


def build_theme_strip_candidates(
    records: list[dict],
) -> list[dict]:
    candidates: list[dict] = []

    favorite_records = [
        item for item in records
        if item.get('is_favorite') and item.get('media_type') in {'video', 'image'}
    ]
    favorite_records.sort(key=lambda item: item.get('mtime_ts') or 0, reverse=True)
    favorite_items = [
        build_feed_media_item(item['name'], item['media_type'])
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

    recent_records = [
        item for item in records
        if item.get('name') and item.get('media_type') in {'video', 'image'}
    ]
    recent_records.sort(key=lambda item: (float(item.get('mtime_ts') or 0), str(item.get('name') or '')), reverse=True)
    recent_items = [
        build_feed_media_item(str(item['name']), str(item['media_type']))
        for item in recent_records[:8]
    ]
    if len(recent_items) >= 3:
        candidates.append({
            'type': 'theme_strip',
            'name': 'theme:recent-added',
            'title': '最近加入',
            'subtitle': '快速跳去媒体库继续看。',
            'target_url': '/library',
            'target_label': '打开媒体库',
            'items': recent_items,
        })

    return candidates


def build_mix_feed_page(
    *,
    page: int,
    size: int,
    seed: str,
    recommend_service,
    media_index,
    favorite_service,
    download_source_store,
) -> dict:
    video_ratio = 4
    image_ratio = 1

    ratio_total = video_ratio + image_ratio
    end = page * size
    start = max(0, end - size)
    # Either media type must be able to fill the page when the other runs out.
    request_window = end + 1

    videos = recommend_service.get_weighted_selection(
        file_type='video',
        limit=request_window,
        seed=f"{seed}:video",
    )
    images = recommend_service.get_weighted_selection(
        file_type='image',
        limit=request_window,
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

    records = media_index.records()
    favorites = favorite_service.load()
    for record in records:
        record['is_favorite'] = record['name'] in favorites
    theme_candidates = build_theme_strip_candidates(records) if page == 1 else []
    page_media = mixed[start:end]
    page_names = {name for _, name in page_media}
    source_groups = collect_source_media_groups([
        record for record in records if record['name'] in page_names
    ], download_source_store)
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
        for media_type, name in page_media
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

    recommendation_reasons = recommend_service.reasons_for([
        str(entry.get('name') or '')
        for entry in mixed_entries
        if entry.get('type') in {'video', 'image'}
    ])
    items = []
    for entry in mixed_entries:
        item_type = str(entry.get('type') or '')
        if item_type in {'theme_strip', 'image_group'}:
            item = {**entry, 'items': [dict(child) for child in entry['items']]}
            if item_type == 'theme_strip':
                for child in item['items']:
                    child['focus_url'] = f"{item['target_url']}?focus={quote(child['name'], safe='')}"
            items.append(item)
            continue

        name = str(entry.get('name') or '')
        if not name or item_type not in {'video', 'image'}:
            continue
        item = build_feed_media_item(name, item_type)
        item['recommendation_reason'] = recommendation_reasons.get(name, '')
        items.append(item)

    return {
        'items': items,
        'page': page,
        'has_more': len(mixed) > end,
        'seed': seed,
    }


def register_flow_routes(
    app, *, media_index, recommend_service, favorite_service,
    download_source_store, activity_store,
):
    @app.route('/flow')
    def flow_view():
        return render_template('tiktok.html', menu='flow')

    @app.route('/api/feed/mix')
    def api_feed_mix():
        result = build_mix_feed_page(
            page=read_int_arg('page', 1, minimum=1),
            size=read_int_arg('size', 24, minimum=8, maximum=200),
            seed=request.args.get('seed') or str(random.randint(1, 999999)),
            recommend_service=recommend_service,
            media_index=media_index,
            favorite_service=favorite_service,
            download_source_store=download_source_store,
        )
        if request.args.get('snapshot') == '1':
            result['has_more'] = False
        return result

    @app.route('/api/activity', methods=['POST', 'DELETE'])
    def api_activity():
        if request.method == 'DELETE':
            activity_store.clear()
            return {'success': True}
        payload = request.get_json(silent=True) or {}
        events = payload.get('events') if isinstance(payload.get('events'), list) else [payload]
        accepted = activity_store.record_many(events)
        return {'success': True, 'data': {'accepted': accepted}}
