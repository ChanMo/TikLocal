"""Library, favorites and collections share one browsing/query boundary."""

import random
from urllib.parse import quote

from flask import redirect, render_template, request, url_for

from tiklocal.services.collections import normalize_collection_mutation_uris
from tiklocal.services.library import IMAGE_EXTENSIONS
from tiklocal.services.media_info import enrich_media_dimensions
from tiklocal.web.media_payloads import build_feed_media_item, media_urls, serialize_library_item
from tiklocal.web import read_int_arg


def register_library_routes(
    app, *, library_service, media_index, library_indexer, favorite_service,
    collection_store, metadata_store, similarity_active: bool,
):
    def _read_page_options(scope: str = 'all') -> dict:
        mode = str(request.args.get('mode', 'all')).strip()
        if scope != 'all' or mode not in {'all', 'image_random', 'video_latest', 'big_files'}:
            mode = 'all'
        search = str(request.args.get('q', '')).strip()[:200] if scope == 'all' else ''
        month = str(request.args.get('month', '')).strip() if scope == 'all' else ''
        if not media_index.is_month_key(month):
            month = ''
        if search:
            mode = 'all'
        seed = str(request.args.get('seed', '')).strip()
        if mode == 'image_random' and not seed:
            seed = str(random.randint(1, 999999))
        return {
            'mode': mode,
            'search': search,
            'month': month,
            'seed': seed,
            'offset': read_int_arg('offset', 0, minimum=0),
            'limit': read_int_arg('limit', 24, minimum=12, maximum=96),
            'min_mb': read_int_arg('min_mb', 50, minimum=1, maximum=10240),
        }

    def _render_library_page(
        page: dict, *, scope: str = 'all', mode: str = 'all',
        min_mb: int = 50, collection: dict | None = None, **context,
    ):
        collection = collection or {}
        return render_template(
            'library.html',
            menu='library' if scope == 'all' else 'favorite',
            scope=scope,
            collection_id=collection.get('id', ''),
            collection_name=collection.get('name', ''),
            collection_description=collection.get('description', ''),
            collection_count=collection.get('item_count', 0),
            collection_cover_uri=collection.get('cover_uri', ''),
            collection_preview_items=collection.get('preview_items', []),
            active_mode=mode,
            mode_seed=page['seed'],
            min_mb=min_mb,
            empty_message={
                'all': 'There is no media to display yet.',
                'favorite': 'You have no favorite media yet.',
                'collection': 'This collection has no media to display yet.',
            }[scope],
            initial_items=page['items'],
            initial_has_more=page['has_more'],
            initial_offset=page['offset'],
            initial_next_offset=page['next_offset'],
            page_size=page['limit'],
            **context,
        )

    def _serialize_collection_summary(collection: dict) -> dict:
        collection_id = str(collection.get('id') or '')
        cover_uri = str(collection.get('cover_uri') or '').strip()
        candidates = [cover_uri, *collection_store.list_item_uris(collection_id, newest_first=True)]
        previews = []
        seen = set()
        for candidate in candidates:
            if not candidate:
                continue
            uri = library_service.find_existing_uri(candidate)
            if not uri or uri in seen:
                continue
            target = library_service.resolve_path(uri)
            if not target or not target.exists() or not target.is_file():
                continue
            seen.add(uri)
            media_type = 'image' if target.suffix.lower() in IMAGE_EXTENSIONS else 'video'
            previews.append({
                'uri': uri,
                'type': media_type,
                'thumb_url': media_urls(uri)['thumb_url'],
            })
            if len(previews) == 4:
                break
        cover_uri = previews[0]['uri'] if previews else ''
        return {
            'id': collection_id,
            'name': str(collection.get('name') or ''),
            'description': str(collection.get('description') or ''),
            'item_count': int(collection.get('item_count') or 0),
            'cover_uri': cover_uri,
            'cover_type': previews[0]['type'] if previews else '',
            'cover_media_url': media_urls(cover_uri)['media_url'] if cover_uri else '',
            'preview_items': previews,
            'detail_url': f"/collection/{quote(collection_id, safe='')}" if collection_id else '#',
            'created_at': str(collection.get('created_at') or ''),
            'updated_at': str(collection.get('updated_at') or ''),
        }

    def _build_library_page(
        *,
        favorites_only: bool = False,
        mode: str = 'all',
        offset: int = 0,
        limit: int = 24,
        min_mb: int = 50,
        seed: str = '',
        collection_id: str = '',
        search: str = '',
        month: str = '',
    ) -> dict:
        uris = None
        if collection_id:
            uris = collection_store.list_item_uris(collection_id, newest_first=True)
        elif favorites_only:
            uris = favorite_service.load()
        page = media_index.page(
            mode=mode, seed=seed, search=search, month=month,
            min_size=min_mb * 1024 * 1024 if mode == 'big_files' else 0,
            offset=offset, limit=limit, uris=uris, preserve_order=bool(collection_id),
        )
        records = page.pop('records')
        enrich_media_dimensions(records, metadata_store, library_service)
        return {
            **page,
            'items': [serialize_library_item(record) for record in records],
            'seed': seed,
        }

    def _serialize_timeline_payload(payload: dict) -> dict:
        months = []
        for month in payload.get('months') or []:
            covers = []
            for record in month.get('records') or []:
                item = build_feed_media_item(
                    str(record.get('name') or ''),
                    str(record.get('media_type') or 'image'),
                )
                covers.append({
                    **item,
                    'mtime_ts': float(record.get('mtime_ts') or 0),
                })
            months.append({
                'key': str(month.get('key') or ''),
                'count': int(month.get('count') or 0),
                'image_count': int(month.get('image_count') or 0),
                'video_count': int(month.get('video_count') or 0),
                'covers': covers,
            })
        return {
            'months': months,
            'years': [
                {
                    'year': str(year.get('year') or ''),
                    'count': int(year.get('count') or 0),
                    'month_count': int(year.get('month_count') or 0),
                }
                for year in payload.get('years') or []
            ],
            'has_more': payload.get('has_more') is True,
            'next_before': str(payload.get('next_before') or ''),
        }

    @app.route('/library')
    def library_view():
        if request.args.get('mode') == 'similar_images':
            if similarity_active:
                return redirect(url_for('similarity_view'))
            return render_template('experiments/disabled.html', menu='library'), 404
        requested_view = str(request.args.get('view', '')).strip()
        if requested_view not in {'timeline', 'explore', 'month'}:
            requested_view = 'explore' if any(request.args.get(key) for key in ('mode', 'q', 'focus')) else 'timeline'
        options = _read_page_options()
        options['offset'] = 0
        if requested_view == 'month' and not options['month']:
            requested_view = 'timeline'
        timeline_payload = {'months': [], 'has_more': False, 'next_before': ''}
        if requested_view == 'timeline':
            timeline_payload = _serialize_timeline_payload(
                media_index.timeline_months(limit=8, preview_limit=18)
            )
            initial_page = {
                'items': [], 'total': 0, 'offset': 0, 'limit': options['limit'],
                'next_offset': 0, 'has_more': False, 'seed': '',
            }
        else:
            if requested_view == 'month':
                options['mode'] = 'all'
            initial_page = _build_library_page(**options)
        return _render_library_page(
            initial_page, mode=options['mode'], min_mb=options['min_mb'],
            library_view=requested_view, timeline_month=options['month'],
            timeline_payload=timeline_payload,
        )

    @app.route('/favorite')
    def favorite_view():
        page = _build_library_page(
            favorites_only=True,
            limit=read_int_arg('limit', 24, minimum=12, maximum=96),
        )
        return _render_library_page(page, scope='favorite')

    @app.route('/collections')
    def collections_view():
        return render_template('collections.html', menu='favorite')

    @app.route('/collection/<collection_id>')
    def collection_detail_view(collection_id):
        collection = collection_store.get(collection_id)
        if not collection:
            return "Collection not found", 404
        page = _build_library_page(
            collection_id=collection_id,
            limit=read_int_arg('limit', 24, minimum=12, maximum=96),
        )
        return _render_library_page(
            page, scope='collection', collection=_serialize_collection_summary(collection),
        )

    @app.route('/api/library/items')
    def api_library_items():
        scope = str(request.args.get('scope', 'all')).strip()
        collection_id = ''
        if scope == 'collection':
            collection_id = str(request.args.get('collection_id', '')).strip()
            if not collection_id:
                return {'success': False, 'error': 'collection_id cannot be empty.'}, 400
        page = _build_library_page(
            favorites_only=scope == 'favorite', collection_id=collection_id,
            **_read_page_options(scope),
        )
        return {'success': True, 'data': page}

    @app.route('/api/library/timeline')
    def api_library_timeline():
        before = str(request.args.get('before', '')).strip()
        limit = read_int_arg('limit', 18, minimum=1, maximum=36)
        preview_limit = read_int_arg('preview_limit', 18, minimum=1, maximum=18)
        payload = media_index.timeline_months(
            before=before,
            limit=limit,
            preview_limit=preview_limit,
        )
        return {
            'success': True,
            'data': _serialize_timeline_payload(payload),
        }

    @app.route('/api/library/sync', methods=['POST'])
    def api_library_sync():
        result = library_indexer.sync()
        return {'success': True, 'data': result}

    @app.route('/api/favorite/<path:name>', methods=['GET', 'POST'])
    def api_favorite(name):
        name = library_service.canonicalize_uri(name)
        try:
            if request.method == 'GET':
                return {'favorite': favorite_service.is_favorite(name)}
            return {'success': True, 'favorite': favorite_service.toggle(name)}
        except (OSError, ValueError):
            return {'success': False, 'error': 'Favorites could not be saved or read. Please try again later.'}, 503

    @app.route('/api/collections', methods=['GET', 'POST'])
    def api_collections():
        if request.method == 'GET':
            collections = collection_store.list()
            items = [_serialize_collection_summary(item) for item in collections]
            return {'success': True, 'data': {'items': items}}

        payload = request.get_json(silent=True) or {}
        name = str(payload.get('name', '')).strip()
        description = str(payload.get('description', '')).strip()
        if not name:
            return {'success': False, 'error': 'name cannot be empty.'}, 400
        try:
            created = collection_store.create(name=name, description=description)
        except ValueError as exc:
            return {'success': False, 'error': str(exc)}, 400
        return {'success': True, 'data': {'item': _serialize_collection_summary(created)}}

    @app.route('/api/collections/<collection_id>', methods=['GET', 'PATCH', 'DELETE'])
    def api_collection_detail(collection_id):
        if request.method == 'GET':
            found = collection_store.get(collection_id)
            if not found:
                return {'success': False, 'error': 'Collection not found'}, 404
            return {'success': True, 'data': {'item': _serialize_collection_summary(found)}}

        if request.method == 'DELETE':
            deleted = collection_store.delete(collection_id)
            if not deleted:
                return {'success': False, 'error': 'Collection not found'}, 404
            return {'success': True, 'data': {'deleted': True}}

        payload = request.get_json(silent=True) or {}
        name = payload['name'] if 'name' in payload else None
        description = payload['description'] if 'description' in payload else None
        cover_uri = library_service.canonicalize_uri(payload['cover_uri']) if 'cover_uri' in payload else None
        try:
            updated = collection_store.update(
                collection_id,
                name=name,
                description=description,
                cover_uri=cover_uri,
            )
        except ValueError as exc:
            return {'success': False, 'error': str(exc)}, 400
        if not updated:
            return {'success': False, 'error': 'Collection not found'}, 404
        return {'success': True, 'data': {'item': _serialize_collection_summary(updated)}}

    @app.route('/api/collections/<collection_id>/items', methods=['GET', 'POST', 'DELETE'])
    def api_collection_items(collection_id):
        if request.method == 'GET':
            found = collection_store.get(collection_id)
            if not found:
                return {'success': False, 'error': 'Collection not found'}, 404
            offset = read_int_arg('offset', 0, minimum=0)
            limit = read_int_arg('limit', 24, minimum=12, maximum=96)
            page = _build_library_page(
                offset=offset,
                limit=limit,
                collection_id=collection_id,
            )
            return {'success': True, 'data': page}

        payload = request.get_json(silent=True) or {}
        uris = [
            library_service.canonicalize_uri(uri)
            for uri in normalize_collection_mutation_uris(payload.get('uris'))
        ]
        if not uris:
            return {'success': False, 'error': 'uris cannot be empty.'}, 400

        if request.method == 'POST':
            updated = collection_store.add_items(collection_id, uris)
        else:
            updated = collection_store.remove_items(collection_id, uris)
        if not updated:
            return {'success': False, 'error': 'Collection not found'}, 404
        return {'success': True, 'data': {'item': _serialize_collection_summary(updated)}}

    @app.route('/api/collections/by-media')
    def api_collections_by_media():
        uri = str(request.args.get('uri', '')).strip()
        if not uri:
            return {'success': False, 'error': 'uri cannot be empty.'}, 400
        canonical_uri = library_service.canonicalize_uri(uri)
        items = collection_store.list_for_media(canonical_uri)
        if not items:
            for legacy_uri in library_service.legacy_candidates(canonical_uri)[1:]:
                items = collection_store.list_for_media(legacy_uri)
                if items:
                    break
        payload = [_serialize_collection_summary(item) for item in items]
        return {'success': True, 'data': {'items': payload}}
