import os
from flask import request, render_template

from tiklocal.web.media_payloads import build_feed_media_item
from tiklocal.paths import get_embedding_config_path
from tiklocal.services.library import IMAGE_EXTENSIONS
from tiklocal.web import read_int_arg as _read_int_arg
from .config import EmbeddingConfigStore, get_default_embedding_config, merge_embedding_config, validate_embedding_config
from .embedding import ImageVectorService, SQLiteImageVectorStore
from .groups import SQLiteSimilarityGroupStore


def register_similarity_routes(app, library_service, app_database):
    embedding_config_store = EmbeddingConfigStore(get_embedding_config_path())
    vector_index = SQLiteImageVectorStore(app_database)
    image_vector_service = ImageVectorService(library_service, vector_index)
    similarity_group_store = SQLiteSimilarityGroupStore(app_database)

    def build_embedding_config_payload(custom_config=None):
        default_config = get_default_embedding_config()
        file_config, file_error = validate_embedding_config(app.config.get('EMBEDDING_CONFIG') or {}, partial=True)
        if file_error:
            file_config = {}
        default_config = merge_embedding_config(default_config, file_config)

        custom = custom_config if custom_config is not None else embedding_config_store.get()
        effective = merge_embedding_config(default_config, custom)
        active_profile = 'custom' if custom else ('config' if file_config else 'default')
        return {
            'active_profile': active_profile,
            'custom': custom,
            'default': default_config,
            'effective': effective,
            'has_api_key': bool(
                os.environ.get('TIKLOCAL_EMBEDDING_API_KEY')
                or os.environ.get('OPENAI_API_KEY')
                or os.environ.get('OPENROUTER_API_KEY')
            ),
        }

    def resolve_effective_embedding_config():
        return build_embedding_config_payload().get('effective') or get_default_embedding_config()

    def _serialize_similar_group(group: dict) -> dict:
        items = []
        for member in group.get('items') or []:
            uri = library_service.find_existing_uri(str(member.get('uri') or ''))
            target = library_service.resolve_path(uri)
            if not target or not target.exists():
                continue
            items.append({
                **build_feed_media_item(uri, 'image'),
                'score': float(member.get('score') or 0),
            })
        return {
            'type': 'similar_group',
            'name': str(group.get('name') or ''),
            'group_key': str(group.get('group_key') or ''),
            'seed_uri': str(group.get('seed_uri') or ''),
            'count': len(items),
            'score': float(group.get('score') or 0),
            'items': items,
        }

    def _build_similar_groups_page(
        *,
        offset: int = 0,
        limit: int = 24,
        min_group_size: int = 3,
    ) -> dict:
        payload = similarity_group_store.list_groups(
            offset=offset,
            limit=limit,
        )
        items = [_serialize_similar_group(group) for group in payload.get('items') or []]
        items = [item for item in items if len(item.get('items') or []) >= min_group_size]
        return {
            **payload,
            'items': items,
        }

    @app.route('/api/ai/embedding-config', methods=['GET', 'POST'])
    def api_embedding_config():
        if request.method == 'GET':
            return {'success': True, 'data': build_embedding_config_payload()}

        payload = request.get_json(silent=True) or {}
        validated, error = validate_embedding_config(payload, partial=False)
        if error:
            return {'success': False, 'error': error}, 400

        saved = embedding_config_store.set(validated)
        return {'success': True, 'data': build_embedding_config_payload(saved)}

    @app.route('/api/ai/embedding-config/reset', methods=['POST'])
    def api_embedding_config_reset():
        embedding_config_store.reset()
        return {'success': True, 'data': build_embedding_config_payload()}

    @app.route('/api/ai/embedding-index/status')
    def api_embedding_index_status():
        config = resolve_effective_embedding_config()
        try:
            return {'success': True, 'data': image_vector_service.status(config)}
        except Exception as e:
            return {'success': False, 'error': str(e)}, 500

    @app.route('/api/ai/embedding-index/run', methods=['POST'])
    def api_embedding_index_run():
        return {
            'success': False,
            'error': 'Web 批量构建已停用，请使用 tiklocal vectorize --dry-run 预览，再通过 CLI 执行。',
        }, 410

    @app.route('/api/ai/embedding-index/cleanup', methods=['POST'])
    def api_embedding_index_cleanup():
        try:
            result = image_vector_service.cleanup_missing()
            return {'success': True, 'data': result}
        except Exception as e:
            return {'success': False, 'error': str(e)}, 500

    @app.route('/api/recommend/similar')
    def api_similar_images():
        uri = request.args.get('uri')
        if not uri:
            return {'success': False, 'error': 'Missing uri'}, 400
        canonical_uri = library_service.find_existing_uri(uri)
        target = library_service.resolve_path(canonical_uri)
        if not target or not target.exists():
            return {'success': False, 'error': 'File not found'}, 404
        try:
            existing = vector_index.get_metadata(canonical_uri)
            if not existing:
                return {'success': True, 'data': {'available': True, 'indexed': False, 'items': []}}
            limit = _read_int_arg('limit', 12, minimum=1, maximum=48)
            candidates = vector_index.query_similar(canonical_uri, limit=limit * 2)
            items = []
            for candidate in candidates:
                item_uri = library_service.find_existing_uri(str(candidate.get('uri') or ''))
                item_path = library_service.resolve_path(item_uri)
                if not item_path or not item_path.exists() or item_path.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                item = build_feed_media_item(item_uri, 'image')
                item['distance'] = candidate.get('distance')
                items.append(item)
                if len(items) >= limit:
                    break
            return {'success': True, 'data': {'available': True, 'indexed': True, 'items': items}}
        except Exception as e:
            return {'success': False, 'error': str(e)}, 500

    @app.route('/api/library/similar-groups')
    def api_library_similar_groups():
        offset = _read_int_arg('offset', 0, minimum=0)
        limit = _read_int_arg('limit', 24, minimum=4, maximum=48)
        min_group_size = _read_int_arg('min_group_size', 3, minimum=2, maximum=12)

        payload = _build_similar_groups_page(
            offset=offset,
            limit=limit,
            min_group_size=min_group_size,
        )
        return {
            'success': True,
            'data': payload,
        }

    @app.route('/experiments/similarity')
    def similarity_view():
        offset = _read_int_arg('offset', 0, minimum=0)
        config = resolve_effective_embedding_config()
        return render_template(
            'experiments/similarity.html', menu='library',
            page=_build_similar_groups_page(offset=offset),
            status=image_vector_service.status(config), config=config,
        )
