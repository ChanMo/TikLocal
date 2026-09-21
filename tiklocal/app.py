import os
import datetime
import socket
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path

from flask import Flask, request, send_file, url_for

# Service Imports
from tiklocal.services.library import LibraryService, build_media_sources
from tiklocal.services.favorites import FavoriteService
from tiklocal.services.recommendation import RecommendService
from tiklocal.services.thumbnail import ThumbnailService
from tiklocal.services.metadata import ImageMetadataStore
from tiklocal.services.captions import CaptionSettings
from tiklocal.web.captions import register_caption_routes
from tiklocal.web.downloads import register_download_routes
from tiklocal.web.library import register_library_routes
from tiklocal.services.database import AppDatabase, MediaActivityStore
from tiklocal.services.library_index import LibraryIndexer, MediaIndexStore
from tiklocal.services.downloader import (
    DownloadConfigStore,
    DownloadHistoryStore,
    DownloadSourceStore,
    DownloadManager,
)
from tiklocal.services.collections import CollectionStore
from tiklocal.services.radio import RadioProfileStore, RadioService
from tiklocal.services.auth import AuthStore
from tiklocal.services.device_auth import DeviceAuthStore
from tiklocal.services.pairing_grants import PairingGrantStore
from tiklocal.auth import configure_auth
from tiklocal.radio_client import register_radio_client_routes
from tiklocal.paths import (
    get_metadata_path,
    get_favorites_path,
    get_prompt_config_path,
    get_llm_config_path,
    get_database_path,
    get_download_config_path,
    get_download_jobs_path,
    get_download_sources_path,
    get_collections_path,
    get_radio_profile_path,
    get_auth_path,
    get_device_auth_path,
)
from tiklocal.web.flow import register_flow_routes
from tiklocal.web.radio import register_radio_routes
from tiklocal.web.media import register_media_routes
from tiklocal.web.settings import register_settings_routes
from tiklocal.config import similarity_enabled


def get_app_version():
    """Return the app version, reading pyproject.toml during development."""
    # Prefer pyproject.toml when running from a development checkout.
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

    # Installed builds read their package metadata.
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
        EXPERIMENTS = None,
        AUTH_ENABLED = None,
        AUTH_COOKIE_SECURE = False,
        DEVICE_AUTH_PATH = None,
        INSTANCE_NAME = None,
    )
    app.config.from_pyfile('config.py', silent=True)
    app.config.from_prefixed_env()
    if test_config is not None:
        app.config.update(test_config)

    similarity_active = similarity_enabled(app.config.get('EXPERIMENTS'), app.config.get('EMBEDDING_CONFIG'))

    instance_name = str(
        app.config.get('INSTANCE_NAME')
        or os.environ.get('TIKLOCAL_NAME')
        or socket.gethostname()
        or 'Local'
    ).strip()[:48] or 'Local'
    app.config['INSTANCE_NAME'] = instance_name
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    configured_auth = app.config.get('AUTH_ENABLED')
    auth_enabled = not bool(app.config.get('TESTING')) if configured_auth is None else bool(configured_auth)
    auth_store = AuthStore(app.config.get('AUTH_PATH') or get_auth_path())
    device_auth_store = DeviceAuthStore(
        app.config.get('DEVICE_AUTH_PATH') or get_device_auth_path()
    )
    pairing_grant_store = app.config.get('PAIRING_GRANT_STORE') or PairingGrantStore(
        ttl_seconds=int(app.config.get('RADIO_PAIRING_GRANT_TTL') or 120),
    )
    bootstrap = None
    if auth_enabled:
        bootstrap = auth_store.ensure(os.environ.get('TIKLOCAL_AUTH_PASSWORD'))
    configure_auth(
        app,
        auth_store,
        enabled=auth_enabled,
        device_auth_store=device_auth_store,
    )
    app.extensions['auth_bootstrap'] = bootstrap
    app.extensions['radio_pairing_grants'] = pairing_grant_store

    @app.template_global()
    def static_asset(filename: str) -> str:
        return url_for('static', filename=filename, v=app_version)

    @app.context_processor
    def app_identity_context():
        return {
            'app_version': app_version,
            'instance_name': instance_name,
            'similarity_enabled': similarity_active,
        }

    @app.after_request
    def apply_cache_policy(response):
        endpoint = request.endpoint or ''
        if endpoint == 'static':
            if request.args.get('v') == app_version:
                response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
            else:
                response.headers['Cache-Control'] = 'public, max-age=0, must-revalidate'
        elif endpoint == 'retired_service_worker':
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Service-Worker-Allowed'] = '/'
        elif request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'private, no-store'
        elif request.path.startswith('/media'):
            response.headers['Cache-Control'] = 'private, no-cache'
        elif request.path == '/thumb':
            response.headers['Cache-Control'] = 'private, max-age=3600, must-revalidate'
        elif response.mimetype == 'text/html':
            response.headers['Cache-Control'] = 'private, no-cache'
        return response

    # Initialize Services
    media_sources = build_media_sources(app.config['MEDIA_ROOT'], app.config.get('MEDIA_SOURCES'))
    library_service = LibraryService(app.config['MEDIA_ROOT'], media_sources=media_sources)
    default_media_root = library_service.media_root
    media_root_str = str(default_media_root)
    app.config['MEDIA_ROOT'] = default_media_root
    favorite_service = FavoriteService(media_root_str, db_path=get_favorites_path(), library_service=library_service)
    thumbnail_service = ThumbnailService(Path(media_root_str), library_service=library_service)
    metadata_store = ImageMetadataStore(get_metadata_path())
    caption_settings = CaptionSettings(app.config.get('VISION_CONFIG'), get_prompt_config_path(), get_llm_config_path())
    register_caption_routes(app, library_service, metadata_store, caption_settings)
    app_database = app.config.get('APP_DATABASE') or AppDatabase(get_database_path())
    app_database.migrate()
    media_index = MediaIndexStore(app_database)
    library_indexer = LibraryIndexer(library_service, media_index)
    index_sync_result = library_indexer.sync()
    app.extensions["media_index_sync"] = index_sync_result
    if index_sync_result["unavailable_sources"]:
        app.logger.warning(
            "Media source unavailable; preserving its existing index: %s",
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
        media_index,
        radio_profile_store,
        activity_store=activity_store,
    )
    register_radio_client_routes(
        app,
        app_version=app_version,
        instance_name=instance_name,
        auth_store=auth_store,
        device_auth_store=device_auth_store,
        pairing_grant_store=pairing_grant_store,
        library_service=library_service,
        favorite_service=favorite_service,
        radio_service=radio_service,
        thumbnail_service=thumbnail_service,
    )
    if similarity_active:
        from tiklocal.experiments.similarity.web import register_similarity_routes
        register_similarity_routes(app, library_service, app_database)
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

    app.extensions['download_manager'] = download_manager
    register_download_routes(app, download_manager, library_service)
    register_library_routes(
        app, library_service=library_service, media_index=media_index,
        library_indexer=library_indexer, favorite_service=favorite_service,
        collection_store=collection_store, metadata_store=metadata_store,
        similarity_active=similarity_active,
    )

    register_flow_routes(
        app, media_index=media_index, recommend_service=recommend_service,
        favorite_service=favorite_service, download_source_store=download_source_store,
        activity_store=activity_store,
    )

    register_radio_routes(app, library_service, radio_service, thumbnail_service)
    register_media_routes(app, library_service, media_index, thumbnail_service, download_manager)
    register_settings_routes(app, media_index, favorite_service, thumbnail_service, app_version)

    # --- Template Filters ---
    @app.template_filter('timestamp_to_date')
    def timestamp_to_date(timestamp):
        try:
            return datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
        except (ValueError, OSError):
            return 'Unknown time'

    @app.template_filter('filesizeformat')
    def filesizeformat(num_bytes):
        if num_bytes is None: return '0 B'
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if num_bytes < 1024.0:
                return f"{int(num_bytes) if unit == 'B' else f'{num_bytes:.1f}'} {unit}"
            num_bytes /= 1024.0
        return f"{num_bytes:.1f} PB"

    @app.get('/service-worker.js')
    def retired_service_worker():
        return send_file(
            Path(app.static_folder) / 'service_worker.js',
            mimetype='application/javascript',
        )

    return app
