import os
import io
import random
import datetime
from urllib.parse import quote, unquote
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path

from flask import Flask, render_template, request, redirect, send_file
from PIL import Image, ImageDraw

# Service Imports
from tiklocal.services import LibraryService, FavoriteService, RecommendService, IMAGE_EXTENSIONS, AUDIO_EXTENSIONS, build_media_sources
from tiklocal.services.thumbnail import ThumbnailService
from tiklocal.services.metadata import (
    ImageMetadataStore,
    PromptConfigStore,
    LLMConfigStore,
    CaptionService,
    get_default_prompt_config,
    get_default_llm_config,
    get_default_vision_config,
    merge_prompt_config,
    merge_llm_config,
    merge_vision_config,
    validate_prompt_config,
    validate_llm_config,
    validate_vision_config,
    has_required_prompt_text,
    compute_prompt_hash,
)
from tiklocal.services.embedding import (
    EmbeddingConfigStore,
    ImageVectorService,
    OpenAICompatibleImageEmbeddingClient,
    SQLiteImageVectorStore,
    get_default_embedding_config,
    merge_embedding_config,
    validate_embedding_config,
)
from tiklocal.services.similarity import SQLiteSimilarityGroupStore
from tiklocal.services.database import AppDatabase, MediaActivityStore
from tiklocal.services.library_index import LibraryIndexer, MediaIndexStore
from tiklocal.services.downloader import (
    DEFAULT_DOWNLOAD_CONFIG,
    DownloadConfigStore,
    DownloadHistoryStore,
    DownloadSourceStore,
    DownloadManager,
    validate_download_config,
    validate_download_url,
)
from tiklocal.services.collections import CollectionStore
from tiklocal.services.embedded_metadata import read_embedded_generation
from tiklocal.services.radio import RadioCandidate, RadioProfileStore, RadioService
from tiklocal.services.auth import AuthStore
from tiklocal.auth import configure_auth
from tiklocal.paths import (
    get_metadata_path,
    get_favorites_path,
    get_prompt_config_path,
    get_llm_config_path,
    get_embedding_config_path,
    get_database_path,
    get_download_config_path,
    get_download_jobs_path,
    get_download_sources_path,
    get_collections_path,
    get_radio_profile_path,
    get_auth_path,
)
from tiklocal import view_builders


def get_app_version():
    """获取应用版本号，开发模式下从 pyproject.toml 读取"""
    # 开发模式：优先从 pyproject.toml 读取
    pyproject_path = Path(__file__).parent.parent / 'pyproject.toml'
    if pyproject_path.exists():
        try:
            import tomllib
        except ImportError:
            try:
                import tomli as tomllib
            except ImportError:
                tomllib = None

        if tomllib:
            try:
                with open(pyproject_path, 'rb') as f:
                    data = tomllib.load(f)
                    return data.get('tool', {}).get('poetry', {}).get('version', '1.0.0')
            except Exception:
                pass

    # 生产模式：从已安装的包元数据获取
    try:
        return version("tiklocal")
    except PackageNotFoundError:
        return '1.0.0'


app_version = get_app_version()

def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY = None,
        MEDIA_ROOT = Path(os.environ.get('MEDIA_ROOT', '.')),
        MEDIA_SOURCES = None,
        DOWNLOAD_SOURCE = 'default',
        VISION_CONFIG = None,
        EMBEDDING_CONFIG = None,
        VECTOR_INDEX = None,
        AUTH_ENABLED = None,
        AUTH_COOKIE_SECURE = False,
    )
    app.config.from_pyfile('config.py', silent=True)
    app.config.from_prefixed_env()
    if test_config is not None:
        app.config.update(test_config)
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    configured_auth = app.config.get('AUTH_ENABLED')
    auth_enabled = not bool(app.config.get('TESTING')) if configured_auth is None else bool(configured_auth)
    auth_store = AuthStore(app.config.get('AUTH_PATH') or get_auth_path())
    bootstrap = None
    if auth_enabled:
        bootstrap = auth_store.ensure(os.environ.get('TIKLOCAL_AUTH_PASSWORD'))
    configure_auth(app, auth_store, enabled=auth_enabled)
    app.extensions['auth_bootstrap'] = bootstrap

    # Initialize Services
    media_sources = build_media_sources(app.config['MEDIA_ROOT'], app.config.get('MEDIA_SOURCES'))
    library_service = LibraryService(app.config['MEDIA_ROOT'], media_sources=media_sources)
    default_media_root = library_service.media_root
    media_root_str = str(default_media_root)
    app.config['MEDIA_ROOT'] = default_media_root
    favorite_service = FavoriteService(media_root_str, db_path=get_favorites_path(), library_service=library_service)
    thumbnail_service = ThumbnailService(Path(media_root_str), library_service=library_service)
    metadata_store = ImageMetadataStore(get_metadata_path())
    prompt_config_store = PromptConfigStore(get_prompt_config_path())
    llm_config_store = LLMConfigStore(get_llm_config_path())
    embedding_config_store = EmbeddingConfigStore(get_embedding_config_path())
    app_database = app.config.get('APP_DATABASE') or AppDatabase(get_database_path())
    app_database.migrate()
    media_index = MediaIndexStore(app_database)
    library_indexer = LibraryIndexer(library_service, media_index)
    index_sync_result = library_indexer.sync()
    app.extensions["media_index_sync"] = index_sync_result
    if index_sync_result["unavailable_sources"]:
        app.logger.warning(
            "媒体源不可用，已保留其现有索引: %s",
            ", ".join(index_sync_result["unavailable_sources"]),
        )
    activity_store = MediaActivityStore(app_database)
    recommend_service = RecommendService(
        library_service,
        favorite_service,
        activity_store,
        media_index=media_index,
    )
    radio_profile_store = RadioProfileStore(get_radio_profile_path())
    radio_service = RadioService(
        library_service,
        favorite_service,
        radio_profile_store,
        activity_store=activity_store,
    )
    vector_index = app.config.get('VECTOR_INDEX') or SQLiteImageVectorStore(app_database)
    image_vector_service = ImageVectorService(library_service, vector_index)
    similarity_group_store = app.config.get('SIMILARITY_GROUP_STORE') or SQLiteSimilarityGroupStore(app_database)
    download_config_store = DownloadConfigStore(get_download_config_path())
    download_history_store = DownloadHistoryStore(get_download_jobs_path())
    download_source_store = DownloadSourceStore(get_download_sources_path())
    collection_store = CollectionStore(get_collections_path())
    download_source_id = str(app.config.get('DOWNLOAD_SOURCE') or library_service.default_source_id).strip() or library_service.default_source_id
    download_source = library_service.sources_by_id.get(download_source_id) or library_service.sources_by_id[library_service.default_source_id]
    download_manager = DownloadManager(
        download_source.path,
        download_config_store,
        download_history_store,
        source_store=download_source_store,
        output_source_id=download_source.id,
        on_outputs=library_indexer.register_uris,
    )

    def build_prompt_config_payload(custom_config=None):
        default_config = get_default_prompt_config()
        default_config.pop('enabled', None)

        custom = custom_config if custom_config is not None else prompt_config_store.get()
        active_profile = 'custom' if custom and custom.get('enabled', True) else 'default'
        return {
            'active_profile': active_profile,
            'custom': custom,
            'default': default_config,
        }

    def build_llm_config_payload(custom_config=None):
        default_config = get_default_llm_config()
        default_config['base_url'] = str(os.environ.get('TIKLOCAL_LLM_BASE_URL', '')).strip()
        default_config['model_name'] = str(os.environ.get('TIKLOCAL_LLM_MODEL', '')).strip()

        custom = custom_config if custom_config is not None else llm_config_store.get()
        has_override = bool(
            custom and (str(custom.get('base_url', '')).strip() or str(custom.get('model_name', '')).strip())
        )
        effective = merge_llm_config(default_config, custom)
        active_profile = 'custom' if has_override else 'default'
        return {
            'active_profile': active_profile,
            'custom': custom,
            'default': default_config,
            'effective': effective,
            'has_api_key': bool(os.environ.get('OPENAI_API_KEY')),
        }

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

    def build_vision_config_payload():
        default_config = get_default_vision_config()
        default_config['base_url'] = str(os.environ.get('TIKLOCAL_VISION_BASE_URL') or '').strip()
        default_config['model_name'] = str(os.environ.get('TIKLOCAL_VISION_MODEL') or '').strip()

        file_config, file_error = validate_vision_config(app.config.get('VISION_CONFIG') or {}, partial=True)
        if file_error:
            file_config = {}
        effective = merge_vision_config(default_config, file_config)
        return {
            'active_profile': 'config' if file_config else 'default',
            'default': default_config,
            'config': file_config,
            'effective': effective,
            'has_api_key': bool(
                os.environ.get('TIKLOCAL_VISION_API_KEY')
                or os.environ.get('TIKLOCAL_AI_API_KEY')
                or os.environ.get('OPENAI_API_KEY')
                or os.environ.get('OPENROUTER_API_KEY')
            ),
        }

    def resolve_effective_embedding_config():
        return build_embedding_config_payload().get('effective') or get_default_embedding_config()

    def resolve_effective_prompt_config(override_config=None):
        vision_payload = build_vision_config_payload()
        vision_config = vision_payload.get('effective') or {}
        effective = {
            'system_prompt': str(vision_config.get('system_prompt') or ''),
            'user_prompt': str(vision_config.get('user_prompt') or ''),
            'temperature': float(vision_config.get('temperature', 0.6)),
            'tags_limit': int(vision_config.get('tags_limit', 5)),
        }
        source = 'config' if vision_payload.get('active_profile') == 'config' else 'default'

        custom = prompt_config_store.get()
        if vision_payload.get('active_profile') != 'config' and custom and custom.get('enabled', True):
            effective = merge_prompt_config(effective, custom)
            source = 'custom'

        if override_config:
            effective = merge_prompt_config(effective, override_config)
            source = 'override'

        effective.pop('enabled', None)
        effective.pop('updated_at', None)
        return effective, source

    def resolve_effective_llm_config():
        vision_payload = build_vision_config_payload()
        vision_config = vision_payload.get('effective') or {}
        vision_model = str(vision_config.get('model_name') or '').strip()
        vision_base_url = str(vision_config.get('base_url') or '').strip()
        if vision_model or vision_base_url:
            return {
                'model_name': vision_model,
                'base_url': vision_base_url,
            }, 'config'

        default_config = get_default_llm_config()
        default_config['base_url'] = str(os.environ.get('TIKLOCAL_LLM_BASE_URL', '')).strip()
        default_config['model_name'] = str(os.environ.get('TIKLOCAL_LLM_MODEL', '')).strip()

        custom = llm_config_store.get()
        effective = merge_llm_config(default_config, custom)
        has_override = bool(
            custom and (str(custom.get('base_url', '')).strip() or str(custom.get('model_name', '')).strip())
        )
        source = 'custom' if has_override else 'default'
        return effective, source

    def build_download_config_payload():
        config = download_manager.get_config()
        effective = {key: config.get(key) for key in DEFAULT_DOWNLOAD_CONFIG.keys()}
        payload = {
            'config': config,
            'defaults': dict(DEFAULT_DOWNLOAD_CONFIG),
            'effective': effective,
        }
        return payload

    # --- Template Filters ---
    @app.template_filter('timestamp_to_date')
    def timestamp_to_date(timestamp):
        try:
            return datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
        except (ValueError, OSError):
            return '未知时间'

    @app.template_filter('filesizeformat')
    def filesizeformat(num_bytes):
        if num_bytes is None: return '0 B'
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if num_bytes < 1024.0:
                return f"{int(num_bytes) if unit == 'B' else f'{num_bytes:.1f}'} {unit}"
            num_bytes /= 1024.0
        return f"{num_bytes:.1f} PB"

    def _read_int_arg(name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
        raw = request.args.get(name, default)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = default

        if minimum is not None:
            value = max(minimum, value)
        if maximum is not None:
            value = min(maximum, value)
        return value

    def _read_choice_arg(name: str, default: str, allowed: set[str]) -> str:
        value = str(request.args.get(name, default)).strip()
        return value if value in allowed else default

    def _positive_ratio(value) -> float | None:
        try:
            ratio = float(value)
        except (TypeError, ValueError):
            return None
        return max(0.0, min(ratio, 1.0))

    def _read_exclude_arg(name: str = 'exclude') -> set[str]:
        values: list[str] = []
        for raw in request.args.getlist(name):
            values.extend(str(raw or '').split(','))
        return {
            library_service.canonicalize_uri(value)
            for value in values
            if str(value or '').strip()
        }

    _build_feed_media_item = view_builders.build_feed_media_item

    def _collect_source_media_groups(records: list[dict]) -> list[dict]:
        return view_builders.collect_source_media_groups(records, download_source_store)

    def _collect_library_records(*, favorites_only: bool = False, search: str = '') -> list[dict]:
        favorites = favorite_service.load()
        records = media_index.records(search=search)
        for record in records:
            record['is_favorite'] = library_service.is_uri_in_set(record['name'], favorites)
        return [record for record in records if record['is_favorite']] if favorites_only else records

    def _build_theme_strip_candidates(records: list[dict]) -> list[dict]:
        return view_builders.build_theme_strip_candidates(records, download_history_store)

    def _serialize_library_item(record: dict) -> dict:
        return view_builders.serialize_library_item(record, metadata_store, library_service)

    def _serialize_similar_group(group: dict) -> dict:
        items = []
        for member in group.get('items') or []:
            uri = library_service.find_existing_uri(str(member.get('uri') or ''))
            target = library_service.resolve_path(uri)
            if not target or not target.exists():
                continue
            encoded = quote(uri, safe='')
            items.append({
                'type': 'image',
                'name': uri,
                'media_url': f"/media?uri={encoded}",
                'thumb_url': f"/media?uri={encoded}",
                'detail_url': f"/image?uri={encoded}",
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
        threshold: float = 0.88,
        min_group_size: int = 3,
        max_group_size: int = 8,
        scan_limit: int = 1000,
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

    def _collect_collection_records(collection_id: str) -> tuple[dict | None, list[dict]]:
        collection = collection_store.get(collection_id)
        if not collection:
            return None, []
        favorites = favorite_service.load()
        records = media_index.records_for_uris(collection_store.list_item_uris(collection_id, newest_first=True))
        for record in records:
            record['is_favorite'] = library_service.is_uri_in_set(record['name'], favorites)
        return collection, records

    def _serialize_collection_summary(collection: dict) -> dict:
        return view_builders.serialize_collection_summary(
            collection,
            collection_store,
            library_service,
            IMAGE_EXTENSIONS,
        )

    def _build_library_page(
        *,
        favorites_only: bool = False,
        mode: str = 'all',
        offset: int = 0,
        limit: int = 48,
        min_mb: int = 50,
        seed: str = '',
        collection_id: str = '',
        search: str = '',
    ) -> dict:
        if not favorites_only and not collection_id and mode != 'image_random':
            indexed_page = media_index.page(
                search=search,
                media_type='video' if mode in {'video_latest', 'big_files'} else '',
                min_size=min_mb * 1024 * 1024 if mode == 'big_files' else 0,
                offset=offset,
                limit=limit,
            )
            favorites = favorite_service.load()
            for record in indexed_page['records']:
                record['is_favorite'] = library_service.is_uri_in_set(record['name'], favorites)
            return {
                'items': [_serialize_library_item(record) for record in indexed_page.pop('records')],
                **indexed_page,
                'seed': seed,
            }
        return view_builders.build_library_page(
            favorites_only=favorites_only,
            mode=mode,
            offset=offset,
            limit=limit,
            min_mb=min_mb,
            seed=seed,
            collection_id=collection_id,
            search=search,
            collect_collection_records_fn=_collect_collection_records,
            collect_library_records_fn=_collect_library_records,
            serialize_library_item_fn=_serialize_library_item,
        )
    _normalize_collection_mutation_uris = view_builders.normalize_collection_mutation_uris
    _build_library_template_context = view_builders.build_library_template_context

    def _canonicalize_collection_uris(raw: object) -> list[str]:
        return [
            library_service.canonicalize_uri(uri)
            for uri in _normalize_collection_mutation_uris(raw)
            if uri
        ]


    # --- Web Routes ---
    @app.route('/')
    def home_view():
        """Quiet launchpad for the local media library."""
        return render_template('home.html', menu='home')

    @app.route('/flow')
    def flow_view():
        """Immersive Mixed Media Feed"""
        return render_template('tiktok.html', menu='flow')

    @app.route('/radio')
    def radio_view():
        """Audio Radio Player"""
        return render_template('radio.html', menu='radio')

    @app.route('/download')
    def download_view():
        """URL Download Center"""
        return render_template('download.html', menu='download')

    @app.route('/settings/')
    def settings_view():
        from tiklocal.paths import get_thumbnails_dir

        # 获取各类统计
        index_stats = media_index.stats()
        video_count = index_stats['videos']
        image_count = index_stats['images']
        favorite_count = len(favorite_service.load())

        # 缩略图缓存信息
        thumb_dir = get_thumbnails_dir()
        thumb_files = list(thumb_dir.glob('*.jpg'))
        cache_count = len(thumb_files)
        cache_size_mb = round(sum(f.stat().st_size for f in thumb_files if f.exists()) / (1024 * 1024), 2)

        return render_template(
            'settings.html',
            menu='settings',
            version=app_version,
            videos=video_count,
            images=image_count,
            favorites=favorite_count,
            cache_count=cache_count,
            cache_size_mb=cache_size_mb
        )

    @app.route('/library')
    def library_view():
        allowed_modes = {'all', 'image_random', 'similar_images', 'video_latest', 'big_files'}
        mode = _read_choice_arg('mode', 'all', allowed_modes)
        min_mb = _read_int_arg('min_mb', 50, minimum=1, maximum=10240)
        limit = _read_int_arg('limit', 24, minimum=12, maximum=96)
        seed = str(request.args.get('seed', '')).strip()
        search = str(request.args.get('q', '')).strip()[:200]
        if search:
            mode = 'all'
        if mode == 'image_random' and not seed:
            seed = str(random.randint(1, 999999))

        if mode == 'similar_images':
            initial_page = _build_similar_groups_page(offset=0, limit=min(limit, 24))
        else:
            initial_page = _build_library_page(
                favorites_only=False,
                mode=mode,
                offset=0,
                limit=limit,
                min_mb=min_mb,
                seed=seed,
                search=search,
            )
        return render_template(
            'library.html',
            **_build_library_template_context(
                menu='library',
                scope='all',
                collection_id='',
                collection_name='',
                active_mode=mode,
                min_mb=min_mb,
                empty_message='暂无可展示媒体。' if mode != 'similar_images' else '运行 tiklocal analyze-similar 后查看相似图片组。',
                initial_page=initial_page,
            ),
        )


    # --- Detail & Action Routes ---
    
    @app.route('/detail/<path:name>')
    def detail_view(name):
        name = library_service.find_existing_uri(name)
        target = library_service.resolve_path(name)
        if not target or not target.exists():
            return "File not found", 404

        if target.suffix.lower() in IMAGE_EXTENSIONS:
            return redirect(f"/image?uri={quote(name)}")
        source_meta = download_manager.resolve_source_for_file(name)
        file_path_encoded = quote(name, safe='/')
        file_query_encoded = quote(name, safe='')
        
        video_names = [
            str(record['name'])
            for record in media_index.records(media_type='video')
        ]
        
        try:
            index = video_names.index(name)
            prev_item = video_names[index-1] if index > 0 else None
            next_item = video_names[index+1] if index < len(video_names)-1 else None
        except ValueError:
            prev_item = next_item = None
        prev_item_path_encoded = quote(prev_item, safe='/') if prev_item else None
        next_item_path_encoded = quote(next_item, safe='/') if next_item else None

        return render_template(
            'detail.html',
            file=name,
            file_path_encoded=file_path_encoded,
            file_query_encoded=file_query_encoded,
            mtime=datetime.datetime.fromtimestamp(target.stat().st_mtime).strftime('%Y-%m-%d %H:%M'),
            size=target.stat().st_size,
            previous_item=prev_item,
            next_item=next_item,
            previous_item_path_encoded=prev_item_path_encoded,
            next_item_path_encoded=next_item_path_encoded,
            source_meta=source_meta,
        )
    
    @app.route('/image')
    def image_view():
        uri = request.args.get('uri')
        if not uri: return "Missing uri", 400
        uri = library_service.find_existing_uri(uri)
        
        target = library_service.resolve_path(uri)
        if not target or not target.exists(): return "File not found", 404
        source_meta = download_manager.resolve_source_for_file(uri)
        uri_path_encoded = quote(uri, safe='/')
        uri_query_encoded = quote(uri, safe='')
        return render_template(
            'image_detail.html',
            image=target,
            uri=uri,
            uri_path_encoded=uri_path_encoded,
            uri_query_encoded=uri_query_encoded,
            stat=target.stat(),
            source_meta=source_meta,
        )

    @app.route("/delete/<path:name>", methods=['POST', 'GET'])
    def delete_view(name):
        name = library_service.find_existing_uri(name)
        target = library_service.resolve_path(name)
        if request.method == 'POST':
            if target and target.exists():
                try:
                    target.unlink()
                    download_manager.delete_source_for_file(name)
                    media_index.delete(name)
                    thumbnail_service.delete_thumbnail(name)
                except Exception as e:
                    return f"Error deleting file: {e}", 500
            else:
                media_index.delete(name)
                thumbnail_service.delete_thumbnail(name)
            return redirect('/library')

        return render_template('delete_confirm.html', file=name)
        
    @app.route("/delete", methods=['POST', 'GET'])
    def delete_confirm_legacy():
        # Legacy support for query param style
        uri = request.args.get('uri')
        if not uri: return redirect('/library')
        return redirect(f"/delete/{quote(uri)}")

    @app.route('/favorite')
    def favorite_view():
        limit = _read_int_arg('limit', 24, minimum=12, maximum=96)
        initial_page = _build_library_page(
            favorites_only=True,
            mode='all',
            offset=0,
            limit=limit,
            min_mb=50,
            seed='',
        )
        return render_template(
            'library.html',
            **_build_library_template_context(
                menu='favorite',
                scope='favorite',
                collection_id='',
                collection_name='',
                active_mode='all',
                min_mb=50,
                empty_message='你还没有收藏媒体。',
                initial_page=initial_page,
            ),
        )

    @app.route('/collections')
    def collections_view():
        return render_template('collections.html', menu='favorite')

    @app.route('/collection/<collection_id>')
    def collection_detail_view(collection_id):
        collection = collection_store.get(collection_id)
        if not collection:
            return "Collection not found", 404
        collection_summary = _serialize_collection_summary(collection)
        limit = _read_int_arg('limit', 24, minimum=12, maximum=96)
        initial_page = _build_library_page(
            favorites_only=False,
            mode='all',
            offset=0,
            limit=limit,
            min_mb=50,
            seed='',
            collection_id=collection_id,
        )
        return render_template(
            'library.html',
            **_build_library_template_context(
                menu='favorite',
                scope='collection',
                collection_id=collection_id,
                collection_name=str(collection.get('name') or '集合'),
                active_mode='all',
                min_mb=50,
                empty_message='该集合暂无可展示媒体。',
                initial_page=initial_page,
                collection_description=str(collection_summary.get('description') or ''),
                collection_count=int(collection_summary.get('item_count') or 0),
                collection_cover_uri=str(collection_summary.get('cover_uri') or ''),
                collection_preview_items=collection_summary.get('preview_items') or [],
            ),
        )


    # --- Media Serving Routes ---

    @app.route("/media/<path:filename>")
    def serve_media(filename):
        target = library_service.resolve_path(filename)
        if not target or not target.exists() or not target.is_file():
            return "File not found", 404
        return send_file(target)

    @app.route("/media")
    def serve_media_legacy():
        # Legacy support for /media?uri=...
        uri = request.args.get('uri')
        if not uri: return "Missing uri", 400
        return redirect(f"/media/{quote(library_service.find_existing_uri(uri), safe='/')}")

    @app.route('/thumb')
    def thumb_view():
        uri = request.args.get('uri')
        if not uri: return send_file(io.BytesIO(thumbnail_service.placeholder), mimetype='image/png')
        
        path, mimetype = thumbnail_service.get_thumbnail(library_service.find_existing_uri(unquote(uri)))
        if isinstance(path, bytes):
            return send_file(io.BytesIO(path), mimetype=mimetype)
        return send_file(path, mimetype=mimetype)

    def _radio_artwork_bytes(uri: str) -> bytes:
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
            idx = (radius // 8) % 2
            color = palette[idx]
            alpha = 18 if idx else 26
            inset = size // 2 - radius
            draw.ellipse((inset, inset, size - inset, size - inset), fill=color + f"{alpha:02x}")

        draw.ellipse((42, 42, size - 42, size - 42), outline=(36, 36, 31, 38), width=2)
        draw.ellipse((112, 112, size - 112, size - 112), outline=(70, 107, 97, 34), width=2)
        draw.ellipse((182, 182, size - 182, size - 182), fill=palette[0], outline=(255, 255, 255, 56), width=2)
        draw.ellipse((220, 220, size - 220, size - 220), fill=palette[2], outline=(36, 36, 31, 30), width=1)

        output = io.BytesIO()
        image.save(output, format="PNG", optimize=True)
        return output.getvalue()

    @app.route('/api/radio/artwork')
    def api_radio_artwork():
        uri = library_service.find_existing_uri(unquote(request.args.get('uri') or ''))
        if uri:
            path, mimetype = thumbnail_service.get_thumbnail(uri)
            if not isinstance(path, bytes):
                return send_file(path, mimetype=mimetype)
        return send_file(io.BytesIO(_radio_artwork_bytes(uri or "radio")), mimetype='image/png')


    # --- API Routes ---
    @app.route('/api/radio/items')
    def api_radio_items():
        offset = _read_int_arg('offset', 0, minimum=0)
        limit = _read_int_arg('limit', 200, minimum=1, maximum=500)
        audios = library_service.scan_audios()
        favorites = favorite_service.load()
        total = len(audios)
        page = audios[offset:offset + limit]
        items = []
        for p in page:
            name = library_service.get_relative_path(p)
            metadata = radio_service.metadata_for(p)
            items.append({
                'name': name,
                'media_url': f'/media/{quote(name, safe="/")}',
                'thumb_url': f'/thumb?uri={quote(name, safe="")}',
                'artwork_url': f'/api/radio/artwork?uri={quote(name, safe="")}',
                'title': metadata.title or p.stem,
                'artist': metadata.artist,
                'album': metadata.album,
                'duration': metadata.duration,
                'is_favorite': name in favorites,
            })
        return {'success': True, 'data': {
            'items': items,
            'total': total,
            'has_more': offset + limit < total,
        }}

    def _serialize_radio_track(item: RadioCandidate) -> dict:
        return {
            'name': item.name,
            'media_url': f'/media/{quote(item.name, safe="/")}',
            'thumb_url': f'/thumb?uri={quote(item.name, safe="")}',
            'artwork_url': f'/api/radio/artwork?uri={quote(item.name, safe="")}',
            'title': item.title,
            'artist': item.artist,
            'album': item.album,
            'duration': item.duration,
            'is_favorite': item.is_favorite,
        }

    @app.route('/api/radio/stations')
    def api_radio_stations():
        return {'success': True, 'data': {'stations': radio_service.list_stations()}}

    @app.route('/api/radio/tune')
    def api_radio_tune():
        limit = _read_int_arg('limit', 12, minimum=1, maximum=30)
        payload = radio_service.tune(
            station=str(request.args.get('station', 'default')).strip(),
            limit=limit,
            exclude=_read_exclude_arg(),
            seed=str(request.args.get('seed', '')).strip() or None,
            serialize_track=_serialize_radio_track,
        )
        return {'success': True, 'data': payload}

    @app.route('/api/radio/metadata')
    def api_radio_metadata():
        uri = library_service.find_existing_uri(unquote(request.args.get('uri') or ''))
        path = library_service.resolve_path(uri)
        if not uri or not path or not path.exists() or not path.is_file():
            return {'success': False, 'error': 'Audio not found'}, 404
        metadata = radio_service.metadata_for(path)
        return {'success': True, 'data': {
            'name': library_service.get_relative_path(path),
            'title': metadata.title or path.stem,
            'artist': metadata.artist,
            'album': metadata.album,
            'duration': metadata.duration,
        }}

    @app.route('/api/radio/feedback', methods=['POST'])
    def api_radio_feedback():
        payload = request.get_json(silent=True) or {}
        event = str(payload.get('event') or '').strip()
        uri = str(payload.get('name') or payload.get('uri') or '').strip()
        if event not in {'play', 'complete', 'skip', 'favorite', 'error'}:
            return {'success': False, 'error': 'Invalid feedback event'}, 400
        ratio = _positive_ratio(payload.get('ratio'))
        entry = radio_service.record_feedback(uri, event, ratio=ratio)
        return {'success': True, 'data': {'profile': entry}}

    @app.route('/api/activity', methods=['POST', 'DELETE'])
    def api_activity():
        if request.method == 'DELETE':
            activity_store.clear()
            return {'success': True}

        payload = request.get_json(silent=True) or {}
        events = payload.get('events') if isinstance(payload.get('events'), list) else [payload]
        accepted = activity_store.record_many(events)
        return {'success': True, 'data': {'accepted': accepted}}

    @app.route('/api/feed/mix')
    def api_feed_mix():
        page = _read_int_arg('page', 1, minimum=1)
        size = _read_int_arg('size', 24, minimum=8, maximum=200)
        seed = request.args.get('seed') or str(random.randint(1, 999999))
        result = view_builders.build_mix_feed_page(
            page=page,
            size=size,
            seed=seed,
            recommend_service=recommend_service,
            collect_library_records_fn=_collect_library_records,
            build_theme_strip_candidates_fn=_build_theme_strip_candidates,
            collect_source_media_groups_fn=_collect_source_media_groups,
            build_feed_media_item_fn=_build_feed_media_item,
        )
        if request.args.get('snapshot') == '1':
            result['has_more'] = False
        return result

    @app.route('/api/download/probe', methods=['GET', 'POST'])
    def api_download_probe():
        return {'success': True, 'data': download_manager.probe_dependencies()}

    @app.route('/api/download/config', methods=['GET', 'POST'])
    def api_download_config():
        if request.method == 'GET':
            return {'success': True, 'data': build_download_config_payload()}

        payload = request.get_json(silent=True) or {}
        validated, error = validate_download_config(payload, partial=True)
        if error:
            return {'success': False, 'error': error}, 400

        try:
            download_manager.update_config(validated)
        except ValueError as exc:
            return {'success': False, 'error': str(exc)}, 400

        return {'success': True, 'data': build_download_config_payload()}

    @app.route('/api/download/cookies')
    def api_download_cookies():
        return {'success': True, 'data': download_manager.list_cookie_files()}

    @app.route('/api/download/cookies/upload', methods=['POST'])
    def api_download_cookies_upload():
        file = request.files.get('file')
        if not file:
            return {'success': False, 'error': '缺少上传文件。'}, 400

        filename = str(file.filename or '').strip()
        if not filename:
            return {'success': False, 'error': '文件名不能为空。'}, 400

        content = file.read()
        try:
            # 上传语义统一为“同名覆盖更新”，避免多按钮分叉。
            data = download_manager.upload_cookie_file(filename, content, replace=True)
        except ValueError as exc:
            return {'success': False, 'error': str(exc)}, 400
        return {'success': True, 'data': data}

    @app.route('/api/download/jobs', methods=['GET', 'POST'])
    def api_download_jobs():
        if request.method == 'GET':
            limit = request.args.get('limit', 50)
            try:
                limit_value = int(limit)
            except (TypeError, ValueError):
                limit_value = 50
            jobs = download_manager.list_jobs(limit=limit_value)
            return {'success': True, 'data': {'jobs': jobs}}

        payload = request.get_json(silent=True) or {}
        validated, error = validate_download_url(payload)
        if error:
            return {'success': False, 'error': error}, 400

        try:
            job = download_manager.enqueue(
                validated['url'],
                save_mode=validated['save_mode'],
                engine=validated.get('engine', 'yt-dlp'),
                cookie_mode=validated.get('cookie_mode', 'auto'),
                cookie_file=validated.get('cookie_file', ''),
            )
        except RuntimeError as exc:
            return {'success': False, 'error': str(exc)}, 400

        return {'success': True, 'data': {'job': job}}

    @app.route('/api/download/jobs/<job_id>')
    def api_download_job_detail(job_id):
        job = download_manager.get_job(job_id)
        if not job:
            return {'success': False, 'error': 'Job not found'}, 404
        return {'success': True, 'data': {'job': job}}

    @app.route('/api/download/jobs/<job_id>/cancel', methods=['POST'])
    def api_download_job_cancel(job_id):
        job = download_manager.cancel(job_id)
        if not job:
            return {'success': False, 'error': 'Job not found'}, 404
        return {'success': True, 'data': {'job': job}}

    @app.route('/api/download/jobs/<job_id>', methods=['DELETE'])
    def api_download_job_delete(job_id):
        ok, error = download_manager.delete_job(job_id)
        if not ok:
            status = 404 if error == 'Job not found' else 400
            return {'success': False, 'error': error}, status
        return {'success': True, 'data': {'deleted': True}}

    @app.route('/api/download/jobs/clear', methods=['POST'])
    def api_download_jobs_clear():
        deleted = download_manager.clear_history()
        return {'success': True, 'data': {'deleted': deleted}}

    @app.route('/api/download/jobs/<job_id>/retry', methods=['POST'])
    def api_download_job_retry(job_id):
        job, error = download_manager.retry_job(job_id)
        if error:
            status = 404 if error == 'Job not found' else 400
            return {'success': False, 'error': error}, status
        return {'success': True, 'data': {'job': job}}

    @app.route('/api/source')
    def api_source_single():
        file_rel = str(request.args.get('file', '')).strip()
        if not file_rel:
            return {'success': False, 'error': 'file 不能为空。'}, 400
        file_rel = library_service.find_existing_uri(file_rel)
        source = download_manager.resolve_source_for_file(file_rel)
        return {'success': True, 'data': {'file': file_rel, 'source': source}}

    @app.route('/api/source/batch', methods=['POST'])
    def api_source_batch():
        payload = request.get_json(silent=True) or {}
        files = payload.get('files')
        if not isinstance(files, list):
            return {'success': False, 'error': 'files 必须是数组。'}, 400

        normalized: list[str] = []
        response_keys: list[tuple[str, str]] = []
        for item in files:
            value = str(item or '').strip()
            if value:
                canonical = library_service.find_existing_uri(value)
                normalized.append(canonical)
                response_keys.append((value, canonical))
            if len(normalized) >= 200:
                break
        resolved_items = download_manager.resolve_sources_for_files(normalized)
        items = {original: resolved_items.get(canonical) for original, canonical in response_keys}
        return {'success': True, 'data': {'items': items}}

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
            return {'success': False, 'error': 'name 不能为空。'}, 400
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
            offset = _read_int_arg('offset', 0, minimum=0)
            limit = _read_int_arg('limit', 24, minimum=12, maximum=96)
            page = _build_library_page(
                favorites_only=False,
                mode='all',
                offset=offset,
                limit=limit,
                min_mb=50,
                seed='',
                collection_id=collection_id,
            )
            return {'success': True, 'data': page}

        payload = request.get_json(silent=True) or {}
        uris = _canonicalize_collection_uris(payload.get('uris'))
        if not uris:
            return {'success': False, 'error': 'uris 不能为空。'}, 400

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
            return {'success': False, 'error': 'uri 不能为空。'}, 400
        canonical_uri = library_service.canonicalize_uri(uri)
        items = collection_store.list_for_media(canonical_uri)
        if not items:
            for legacy_uri in library_service.legacy_candidates(canonical_uri)[1:]:
                items = collection_store.list_for_media(legacy_uri)
                if items:
                    break
        payload = [_serialize_collection_summary(item) for item in items]
        return {'success': True, 'data': {'items': payload}}

    @app.route('/api/ai/prompt-config', methods=['GET', 'POST'])
    def api_prompt_config():
        if request.method == 'GET':
            return {'success': True, 'data': build_prompt_config_payload()}

        payload = request.get_json(silent=True) or {}
        validated, error = validate_prompt_config(payload, partial=False, include_enabled=True)
        if error:
            return {'success': False, 'error': error}, 400

        saved = prompt_config_store.set(validated)
        return {'success': True, 'data': build_prompt_config_payload(saved)}

    @app.route('/api/ai/prompt-config/reset', methods=['POST'])
    def api_prompt_config_reset():
        prompt_config_store.reset()
        return {'success': True, 'data': build_prompt_config_payload()}

    @app.route('/api/ai/llm-config', methods=['GET', 'POST'])
    def api_llm_config():
        if request.method == 'GET':
            return {'success': True, 'data': build_llm_config_payload()}

        payload = request.get_json(silent=True) or {}
        validated, error = validate_llm_config(payload, partial=False)
        if error:
            return {'success': False, 'error': error}, 400

        saved = llm_config_store.set(validated)
        return {'success': True, 'data': build_llm_config_payload(saved)}

    @app.route('/api/ai/llm-config/reset', methods=['POST'])
    def api_llm_config_reset():
        llm_config_store.reset()
        return {'success': True, 'data': build_llm_config_payload()}

    @app.route('/api/ai/vision-config')
    def api_vision_config():
        return {'success': True, 'data': build_vision_config_payload()}

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
        config = resolve_effective_embedding_config()
        if not bool(config.get('enabled')):
            return {'success': False, 'error': '请先在配置文件中启用 embedding.enabled。'}, 400
        try:
            client = OpenAICompatibleImageEmbeddingClient(
                model=str(config.get('model_name') or ''),
                base_url=str(config.get('base_url') or ''),
                dimensions=int(config.get('dimensions') or 768),
                image_max_size=int(config.get('image_max_size') or 512),
                image_quality=int(config.get('image_quality') or 82),
                api_key=(
                    os.environ.get('TIKLOCAL_EMBEDDING_API_KEY')
                    or os.environ.get('TIKLOCAL_AI_API_KEY')
                    or os.environ.get('OPENAI_API_KEY')
                    or os.environ.get('OPENROUTER_API_KEY')
                    or None
                ),
            )
            result = image_vector_service.index_missing_or_stale(config=config, client=client)
            result['status'] = image_vector_service.status(config)
            return {'success': True, 'data': result}
        except Exception as e:
            return {'success': False, 'error': str(e)}, 500

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
                item = view_builders.build_feed_media_item(item_uri, 'image')
                item['distance'] = candidate.get('distance')
                items.append(item)
                if len(items) >= limit:
                    break
            return {'success': True, 'data': {'available': True, 'indexed': True, 'items': items}}
        except Exception as e:
            return {'success': False, 'error': str(e)}, 500

    @app.route('/api/image/metadata', methods=['GET', 'POST'])
    def api_image_metadata():
        if request.method == 'GET':
            uri = request.args.get('uri')
            if not uri:
                return {'success': False, 'error': 'Missing uri'}, 400
            canonical_uri = library_service.canonicalize_uri(uri)
            data = metadata_store.get(canonical_uri)
            if data is None:
                for legacy_uri in library_service.legacy_candidates(canonical_uri)[1:]:
                    data = metadata_store.get(legacy_uri)
                    if data is not None:
                        break
            return {'success': True, 'data': data}

        payload = request.get_json(silent=True) or {}
        uri = payload.get('uri')
        force = bool(payload.get('force'))
        prompt_override = payload.get('prompt_override')
        if not uri:
            return {'success': False, 'error': 'Missing uri'}, 400
        uri = library_service.canonicalize_uri(uri)

        override_config = None
        if prompt_override is not None:
            override_config, error = validate_prompt_config(prompt_override, partial=True, include_enabled=False)
            if error:
                return {'success': False, 'error': error}, 400
            if not override_config:
                override_config = None

        existing = metadata_store.get(uri)
        if existing is None:
            for legacy_uri in library_service.legacy_candidates(uri)[1:]:
                existing = metadata_store.get(legacy_uri)
                if existing is not None:
                    break
        if existing and not force:
            return {'success': True, 'data': existing, 'skipped': True}

        target = library_service.resolve_path(uri)
        if not target or not target.exists():
            return {'success': False, 'error': 'File not found'}, 404

        try:
            vision_config = build_vision_config_payload().get('effective') or {}
            if not bool(vision_config.get('enabled', True)):
                return {'success': False, 'error': '图片识别未启用，请在配置文件中设置 vision.enabled。'}, 400
            effective_prompt, prompt_source = resolve_effective_prompt_config(override_config)
            if not has_required_prompt_text(effective_prompt):
                return {
                    'success': False,
                    'error': '请在配置文件中设置 vision 默认 Prompt，或使用本次覆盖提示词。',
                }, 400
            effective_llm, llm_source = resolve_effective_llm_config()
            caption_service = CaptionService(
                model=effective_llm.get('model_name') or None,
                base_url=effective_llm.get('base_url') or None,
                api_key=(
                    os.environ.get('TIKLOCAL_VISION_API_KEY')
                    or os.environ.get('TIKLOCAL_AI_API_KEY')
                    or os.environ.get('OPENAI_API_KEY')
                    or os.environ.get('OPENROUTER_API_KEY')
                    or None
                ),
            )
            result = caption_service.generate(
                target,
                tags_limit=int(effective_prompt.get('tags_limit', 5)),
                prompt_config=effective_prompt,
            )
            result['prompt_source'] = prompt_source
            result['llm_source'] = llm_source
            result.setdefault('prompt_hash', compute_prompt_hash(effective_prompt))
            merged = dict(existing) if isinstance(existing, dict) else {}
            merged.update(result)
            metadata_store.set(uri, merged, overwrite=True)
            return {'success': True, 'data': merged}
        except Exception as e:
            return {'success': False, 'error': str(e)}, 500

    @app.route('/api/image/embedded-metadata')
    def api_image_embedded_metadata():
        uri = request.args.get('uri')
        if not uri:
            return {'success': False, 'error': 'Missing uri'}, 400
        canonical_uri = library_service.find_existing_uri(uri)
        target = library_service.resolve_path(canonical_uri)
        if not target or not target.exists():
            return {'success': False, 'error': 'File not found'}, 404
        return {'success': True, 'data': {'embedded_generation': read_embedded_generation(target)}}

    @app.route('/api/favorite/<path:name>', methods=['GET', 'POST'])
    def api_favorite(name):
        name = library_service.canonicalize_uri(name)
        if request.method == 'GET':
            return {'favorite': favorite_service.is_favorite(name)}
        
        new_state = favorite_service.toggle(name)
        return {'success': True, 'favorite': new_state}

    @app.route('/api/thumbnail/<path:name>', methods=['POST'])
    def api_set_thumbnail(name):
        name = library_service.find_existing_uri(name)
        target = library_service.resolve_path(name)
        if not target: return {'success': False, 'error': 'Invalid path'}, 400

        payload = request.get_json(silent=True) or {}
        ts = payload.get('time')

        # This logic is a bit specific to app.py still, ideally move to ThumbnailService
        # But for now, we just need to regen the thumb
        thumb_path = thumbnail_service._get_thumb_path(name)
        success = thumbnail_service._generate(target, thumb_path, timestamp=float(ts) if ts else None)

        if success:
             return {'success': True, 'url': f"/thumb?uri={quote(name)}&v={int(datetime.datetime.now().timestamp())}"}
        return {'success': False, 'error': 'Failed to generate'}, 500

    @app.route('/api/cache/clear', methods=['POST'])
    def api_clear_cache():
        """清理缩略图缓存"""
        from tiklocal.paths import get_thumbnails_dir

        thumb_dir = get_thumbnails_dir()
        deleted_count = 0
        freed_bytes = 0

        try:
            for thumb_file in thumb_dir.glob('*.jpg'):
                try:
                    freed_bytes += thumb_file.stat().st_size
                    thumb_file.unlink()
                    deleted_count += 1
                except Exception:
                    continue

            return {
                'success': True,
                'deleted_count': deleted_count,
                'freed_mb': round(freed_bytes / (1024 * 1024), 2)
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}, 500

    @app.route('/api/library/stats')
    def api_library_stats():
        """获取媒体库统计信息"""
        from tiklocal.paths import get_thumbnails_dir

        index_stats = media_index.stats()
        favorites = favorite_service.load()

        # 计算缩略图缓存信息
        thumb_dir = get_thumbnails_dir()
        thumb_files = list(thumb_dir.glob('*.jpg'))
        thumb_size = sum(f.stat().st_size for f in thumb_files if f.exists())

        return {
            'videos': index_stats['videos'],
            'images': index_stats['images'],
            'audios': index_stats['audios'],
            'indexed_total': index_stats['total'],
            'last_synced_at': index_stats['last_synced_at'],
            'favorites': len(favorites),
            'cache_count': len(thumb_files),
            'cache_mb': round(thumb_size / (1024 * 1024), 2)
        }

    @app.route('/api/library/sync', methods=['POST'])
    def api_library_sync():
        result = library_indexer.sync()
        return {'success': True, 'data': result}

    @app.route('/api/library/items')
    def api_library_items():
        scope = str(request.args.get('scope', 'all')).strip()
        favorites_only = scope == 'favorite'
        collection_id = ''
        if scope == 'collection':
            collection_id = str(request.args.get('collection_id', '')).strip()
            if not collection_id:
                return {'success': False, 'error': 'collection_id 不能为空。'}, 400
        allowed_modes = {'all', 'image_random', 'video_latest', 'big_files'}
        mode = _read_choice_arg('mode', 'all', allowed_modes)
        if scope != 'all':
            mode = 'all'
        offset = _read_int_arg('offset', 0, minimum=0)
        limit = _read_int_arg('limit', 24, minimum=12, maximum=96)
        min_mb = _read_int_arg('min_mb', 50, minimum=1, maximum=10240)
        seed = str(request.args.get('seed', '')).strip()
        search = str(request.args.get('q', '')).strip()[:200] if scope == 'all' else ''
        if search:
            mode = 'all'
        if mode == 'image_random' and not seed:
            seed = str(random.randint(1, 999999))

        payload = _build_library_page(
            favorites_only=favorites_only,
            mode=mode,
            offset=offset,
            limit=limit,
            min_mb=min_mb,
            seed=seed,
            collection_id=collection_id,
            search=search,
        )
        return {
            'success': True,
            'data': payload,
        }

    @app.route('/api/library/similar-groups')
    def api_library_similar_groups():
        offset = _read_int_arg('offset', 0, minimum=0)
        limit = _read_int_arg('limit', 24, minimum=4, maximum=48)
        threshold_raw = request.args.get('threshold', 0.88)
        try:
            threshold = float(threshold_raw)
        except (TypeError, ValueError):
            threshold = 0.88
        threshold = max(0.5, min(threshold, 0.99))
        min_group_size = _read_int_arg('min_group_size', 3, minimum=2, maximum=12)
        max_group_size = _read_int_arg('max_group_size', 8, minimum=2, maximum=16)
        scan_limit = _read_int_arg('scan_limit', 1000, minimum=50, maximum=5000)
        if max_group_size < min_group_size:
            max_group_size = min_group_size

        payload = _build_similar_groups_page(
            offset=offset,
            limit=limit,
            threshold=threshold,
            min_group_size=min_group_size,
            max_group_size=max_group_size,
            scan_limit=scan_limit,
        )
        return {
            'success': True,
            'data': payload,
        }

    return app
