"""Flow HTTP entry points and media/card composition."""

import datetime
import random

from flask import render_template, request

from tiklocal.services.recommendation import FORGOTTEN_DAYS, shown_within
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


def build_memory_card(records: list[dict], profiles: dict, rng: random.Random, now: datetime.datetime) -> dict | None:
    """Images from one past week that have not been shown for a while; callers pass year-old images."""
    weeks: dict[tuple[int, int], list[dict]] = {}
    for record in records:
        if shown_within(profiles.get(record['name']), FORGOTTEN_DAYS, now):
            continue
        week = datetime.date.fromtimestamp(record['mtime_ts']).isocalendar()[:2]
        weeks.setdefault(week, []).append(record)
    weeks = {week: items for week, items in weeks.items() if len(items) >= 3}
    if not weeks:
        return None
    # The same week in an earlier year reads as an anniversary; otherwise any week will do.
    same_week = sorted(week for week in weeks if week[1] == now.isocalendar()[1])
    items = weeks[rng.choice(same_week or sorted(weeks))]
    if len(items) > 8:
        items = rng.sample(items, 8)
    items.sort(key=lambda item: item['mtime_ts'])
    first = datetime.date.fromtimestamp(items[0]['mtime_ts'])
    return {
        'type': 'image_group',
        'name': f"memory:{items[0]['name']}",
        'caption': f"This week in {first.year}" if same_week else first.strftime('%B %Y'),
        'items': [build_feed_media_item(item['name'], 'image') for item in items],
    }


def build_mix_feed_page(
    *,
    page: int,
    size: int,
    seed: str,
    recommend_service,
    media_index,
    download_source_store,
    activity_store=None,
    mode: str = '',
) -> dict:
    video_ratio = 4
    image_ratio = 1

    ratio_total = video_ratio + image_ratio
    end = page * size
    start = max(0, end - size)
    # Either media type must be able to fill the page when the other runs out.
    request_window = end + 1

    forgotten = mode == 'forgotten'
    select = recommend_service.get_forgotten_selection if forgotten else recommend_service.get_weighted_selection
    videos = select(
        file_type='video',
        limit=request_window,
        seed=f"{seed}:video",
    )
    images = select(
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

    page_media = mixed[start:end]
    page_names = {name for _, name in page_media}
    # The forgotten feed stays plain media; cards belong to the everyday Flow.
    records = [] if forgotten else media_index.records()
    source_groups = collect_source_media_groups([
        record for record in records if record['name'] in page_names
    ], download_source_store) if records else []
    image_group_candidate = None
    image_group_names: set[str] = set()
    for group in source_groups:
        group_items = [item for item in (group.get('items') or []) if item.get('type') == 'image']
        if len(group_items) < 2:
            continue
        image_group_candidate = {
            'type': 'image_group',
            'name': f"group:{group_items[0]['name']}",
            'title': 'Original Gallery',
            'subtitle': 'Swipe sideways through images from the same post.',
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
    # A memory every other page keeps it a small surprise rather than a pattern.
    memory = None
    if records and page % 2 == 1:
        now = datetime.datetime.now()
        year_ago = now.timestamp() - 365 * 86400
        old_images = [
            record for record in records
            if record.get('media_type') == 'image' and 0 < float(record.get('mtime_ts') or 0) <= year_ago
        ]
        profiles = activity_store.profiles_for([record['name'] for record in old_images]) if activity_store else {}
        memory = build_memory_card(old_images, profiles, random.Random(f"{seed}:memory:{page}"), now)
    if memory and mixed_entries:
        memory_names = {child['name'] for child in memory['items']}
        mixed_entries = [entry for entry in mixed_entries if entry['name'] not in memory_names]
        memory_rng = random.Random(f"{seed}:memory-slot:{page}")
        insert_floor = min(8, len(mixed_entries))
        insert_ceil = min(max(insert_floor, 14), len(mixed_entries))
        insert_at = insert_floor if insert_ceil <= insert_floor else memory_rng.randint(insert_floor, insert_ceil)
        mixed_entries.insert(insert_at, memory)

    recommendation_reasons = recommend_service.reasons_for([
        str(entry.get('name') or '')
        for entry in mixed_entries
        if entry.get('type') in {'video', 'image'}
    ])
    items = []
    for entry in mixed_entries:
        item_type = str(entry.get('type') or '')
        if item_type == 'image_group':
            items.append({**entry, 'items': [dict(child) for child in entry['items']]})
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
    app, *, media_index, recommend_service,
    download_source_store, activity_store,
):
    @app.route('/flow')
    def flow_view():
        return render_template('flow.html', menu='flow')

    @app.route('/api/feed/mix')
    def api_feed_mix():
        result = build_mix_feed_page(
            page=read_int_arg('page', 1, minimum=1),
            size=read_int_arg('size', 24, minimum=8, maximum=200),
            seed=request.args.get('seed') or str(random.randint(1, 999999)),
            recommend_service=recommend_service,
            media_index=media_index,
            download_source_store=download_source_store,
            activity_store=activity_store,
            mode=request.args.get('mode', ''),
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
