import os
import io
import random
import datetime
from urllib.parse import quote, unquote
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path

from flask import Flask, render_template, send_from_directory, request, redirect, send_file

# Service Imports
from tiklocal.services import LibraryService, FavoriteService, RecommendService, IMAGE_EXTENSIONS
from tiklocal.services.thumbnail import ThumbnailService
from tiklocal.services.metadata import (
    ImageMetadataStore,
    PromptConfigStore,
    LLMConfigStore,
    CaptionService,
    get_default_prompt_config,
    get_default_llm_config,
    merge_prompt_config,
    merge_llm_config,
    validate_prompt_config,
    validate_llm_config,
    compute_prompt_hash,
)
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
from tiklocal.paths import (
    get_metadata_path,
    get_prompt_config_path,
    get_llm_config_path,
    get_download_config_path,
    get_download_jobs_path,
    get_download_sources_path,
    get_collections_path,
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
    app.config.from_prefixed_env()
    app.config.from_mapping(
        SECRET_KEY = 'dev',
        MEDIA_ROOT = Path(os.environ.get('MEDIA_ROOT', '.'))
    )
    app.config.from_pyfile('config.py', silent=True)
    if test_config is not None:
        app.config.update(test_config)
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Initialize Services
    media_root_str = str(app.config['MEDIA_ROOT'])
    library_service = LibraryService(media_root_str)
    favorite_service = FavoriteService(media_root_str)
    recommend_service = RecommendService(library_service, favorite_service)
    thumbnail_service = ThumbnailService(Path(media_root_str))
    metadata_store = ImageMetadataStore(get_metadata_path())
    prompt_config_store = PromptConfigStore(get_prompt_config_path())
    llm_config_store = LLMConfigStore(get_llm_config_path())
    download_config_store = DownloadConfigStore(get_download_config_path())
    download_history_store = DownloadHistoryStore(get_download_jobs_path())
    download_source_store = DownloadSourceStore(get_download_sources_path())
    collection_store = CollectionStore(get_collections_path())
    download_manager = DownloadManager(
        Path(media_root_str),
        download_config_store,
        download_history_store,
        source_store=download_source_store,
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

    def resolve_effective_prompt_config(override_config=None):
        effective = get_default_prompt_config()
        source = 'default'

        custom = prompt_config_store.get()
        if custom and custom.get('enabled', True):
            effective = merge_prompt_config(effective, custom)
            source = 'custom'

        if override_config:
            effective = merge_prompt_config(effective, override_config)
            source = 'override'

        effective.pop('enabled', None)
        effective.pop('updated_at', None)
        return effective, source

    def resolve_effective_llm_config():
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

    _build_feed_media_item = view_builders.build_feed_media_item

    def _collect_source_media_groups(records: list[dict]) -> list[dict]:
        return view_builders.collect_source_media_groups(records, download_source_store)

    def _collect_library_records(*, favorites_only: bool = False) -> list[dict]:
        return view_builders.collect_library_records(
            library_service,
            favorite_service,
            IMAGE_EXTENSIONS,
            favorites_only=favorites_only,
        )

    def _build_theme_strip_candidates(records: list[dict]) -> list[dict]:
        return view_builders.build_theme_strip_candidates(records, download_history_store)

    def _serialize_library_item(record: dict) -> dict:
        return view_builders.serialize_library_item(record, metadata_store, library_service)

    def _collect_collection_records(collection_id: str) -> tuple[dict | None, list[dict]]:
        return view_builders.collect_collection_records(
            collection_id,
            collection_store,
            favorite_service,
            library_service,
            IMAGE_EXTENSIONS,
        )

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
    ) -> dict:
        return view_builders.build_library_page(
            favorites_only=favorites_only,
            mode=mode,
            offset=offset,
            limit=limit,
            min_mb=min_mb,
            seed=seed,
            collection_id=collection_id,
            collect_collection_records_fn=_collect_collection_records,
            collect_library_records_fn=_collect_library_records,
            serialize_library_item_fn=_serialize_library_item,
        )
    _normalize_collection_mutation_uris = view_builders.normalize_collection_mutation_uris
    _build_library_template_context = view_builders.build_library_template_context


    # --- Web Routes ---
    @app.route('/')
    def tiktok():
        """Immersive Mixed Media Feed"""
        return render_template('tiktok.html', menu='index')

    @app.route('/download')
    def download_view():
        """URL Download Center"""
        return render_template('download.html', menu='download')

    @app.route('/settings/')
    def settings_view():
        from tiklocal.paths import get_thumbnails_dir

        # 获取各类统计
        video_count = len(library_service.scan_videos())
        image_count = len(library_service.scan_images())
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
        allowed_modes = {'all', 'image_random', 'video_latest', 'big_files'}
        mode = _read_choice_arg('mode', 'all', allowed_modes)
        min_mb = _read_int_arg('min_mb', 50, minimum=1, maximum=10240)
        limit = _read_int_arg('limit', 48, minimum=12, maximum=96)
        seed = str(request.args.get('seed', '')).strip()
        if mode == 'image_random' and not seed:
            seed = str(random.randint(1, 999999))

        initial_page = _build_library_page(
            favorites_only=False,
            mode=mode,
            offset=0,
            limit=limit,
            min_mb=min_mb,
            seed=seed,
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
                empty_message='暂无可展示媒体。',
                initial_page=initial_page,
            ),
        )


    # --- Detail & Action Routes ---
    
    @app.route('/detail/<path:name>')
    def detail_view(name):
        target = library_service.resolve_path(name)
        if not target or not target.exists():
            return "File not found", 404

        if target.suffix.lower() in IMAGE_EXTENSIONS:
            return redirect(f"/image?uri={quote(name)}")
        source_meta = download_manager.resolve_source_for_file(name)
        file_path_encoded = quote(name, safe='/')
        file_query_encoded = quote(name, safe='')
        
        # Context navigation (prev/next)
        # Note: Re-scanning every request is inefficient for large libraries, 
        # but keeps state stateless. Optimization: Cache this.
        videos = library_service.scan_videos()
        video_names = [library_service.get_relative_path(v) for v in videos]
        
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
        
        target = library_service.resolve_path(uri)
        if not target or not target.exists(): return "File not found", 404
        source_meta = download_manager.resolve_source_for_file(uri)
        uri_query_encoded = quote(uri, safe='')
        return render_template(
            'image_detail.html',
            image=target,
            uri=uri,
            uri_query_encoded=uri_query_encoded,
            stat=target.stat(),
            source_meta=source_meta,
        )

    @app.route("/delete/<path:name>", methods=['POST', 'GET'])
    def delete_view(name):
        target = library_service.resolve_path(name)
        if request.method == 'POST':
            if target and target.exists():
                try:
                    target.unlink()
                    download_manager.delete_source_for_file(name)
                    # Thumbnails are handled by OS or periodic cleanup, but ideally Service should handle it
                except Exception as e:
                    return f"Error deleting file: {e}", 500
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
        limit = _read_int_arg('limit', 48, minimum=12, maximum=96)
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
        limit = _read_int_arg('limit', 48, minimum=12, maximum=96)
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
            ),
        )


    # --- Media Serving Routes ---

    @app.route("/media/<path:filename>")
    def serve_media(filename):
        # Consolidated media serving
        try:
            return send_from_directory(app.config["MEDIA_ROOT"], filename)
        except Exception:
            return "File not found", 404

    @app.route("/media")
    def serve_media_legacy():
        # Legacy support for /media?uri=...
        uri = request.args.get('uri')
        if not uri: return "Missing uri", 400
        return redirect(f"/media/{quote(uri, safe='/')}")

    @app.route('/thumb')
    def thumb_view():
        uri = request.args.get('uri')
        if not uri: return send_file(io.BytesIO(thumbnail_service.placeholder), mimetype='image/png')
        
        path, mimetype = thumbnail_service.get_thumbnail(unquote(uri))
        if isinstance(path, bytes):
            return send_file(io.BytesIO(path), mimetype=mimetype)
        return send_file(path, mimetype=mimetype)


    # --- API Routes ---
    @app.route('/api/feed/mix')
    def api_feed_mix():
        page = _read_int_arg('page', 1, minimum=1)
        size = _read_int_arg('size', 24, minimum=8, maximum=60)
        seed = request.args.get('seed') or str(random.randint(1, 999999))
        return view_builders.build_mix_feed_page(
            page=page,
            size=size,
            seed=seed,
            recommend_service=recommend_service,
            collect_library_records_fn=_collect_library_records,
            build_theme_strip_candidates_fn=_build_theme_strip_candidates,
            collect_source_media_groups_fn=_collect_source_media_groups,
            build_feed_media_item_fn=_build_feed_media_item,
        )

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
        source = download_manager.resolve_source_for_file(file_rel)
        return {'success': True, 'data': {'file': file_rel, 'source': source}}

    @app.route('/api/source/batch', methods=['POST'])
    def api_source_batch():
        payload = request.get_json(silent=True) or {}
        files = payload.get('files')
        if not isinstance(files, list):
            return {'success': False, 'error': 'files 必须是数组。'}, 400

        normalized: list[str] = []
        for item in files:
            value = str(item or '').strip()
            if value:
                normalized.append(value)
            if len(normalized) >= 200:
                break
        items = download_manager.resolve_sources_for_files(normalized)
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
        cover_uri = payload['cover_uri'] if 'cover_uri' in payload else None
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
            limit = _read_int_arg('limit', 48, minimum=12, maximum=96)
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
        uris = _normalize_collection_mutation_uris(payload.get('uris'))
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
        items = collection_store.list_for_media(uri)
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

    @app.route('/api/image/metadata', methods=['GET', 'POST'])
    def api_image_metadata():
        if request.method == 'GET':
            uri = request.args.get('uri')
            if not uri:
                return {'success': False, 'error': 'Missing uri'}, 400
            return {'success': True, 'data': metadata_store.get(uri)}

        payload = request.get_json(silent=True) or {}
        uri = payload.get('uri')
        force = bool(payload.get('force'))
        prompt_override = payload.get('prompt_override')
        if not uri:
            return {'success': False, 'error': 'Missing uri'}, 400

        override_config = None
        if prompt_override is not None:
            override_config, error = validate_prompt_config(prompt_override, partial=True, include_enabled=False)
            if error:
                return {'success': False, 'error': error}, 400
            if not override_config:
                override_config = None

        existing = metadata_store.get(uri)
        if existing and not force:
            return {'success': True, 'data': existing, 'skipped': True}

        target = library_service.resolve_path(uri)
        if not target or not target.exists():
            return {'success': False, 'error': 'File not found'}, 404

        try:
            effective_prompt, prompt_source = resolve_effective_prompt_config(override_config)
            effective_llm, llm_source = resolve_effective_llm_config()
            caption_service = CaptionService(
                model=effective_llm.get('model_name') or None,
                base_url=effective_llm.get('base_url') or None,
                api_key=os.environ.get('OPENAI_API_KEY') or None,
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

    @app.route('/api/favorite/<path:name>', methods=['GET', 'POST'])
    def api_favorite(name):
        if request.method == 'GET':
            return {'favorite': favorite_service.is_favorite(name)}
        
        new_state = favorite_service.toggle(name)
        return {'success': True, 'favorite': new_state}

    @app.route('/api/thumbnail/<path:name>', methods=['POST'])
    def api_set_thumbnail(name):
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

        videos = library_service.scan_videos()
        images = library_service.scan_images()
        favorites = favorite_service.load()

        # 计算缩略图缓存信息
        thumb_dir = get_thumbnails_dir()
        thumb_files = list(thumb_dir.glob('*.jpg'))
        thumb_size = sum(f.stat().st_size for f in thumb_files if f.exists())

        return {
            'videos': len(videos),
            'images': len(images),
            'favorites': len(favorites),
            'cache_count': len(thumb_files),
            'cache_mb': round(thumb_size / (1024 * 1024), 2)
        }

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
        limit = _read_int_arg('limit', 48, minimum=12, maximum=96)
        min_mb = _read_int_arg('min_mb', 50, minimum=1, maximum=10240)
        seed = str(request.args.get('seed', '')).strip()
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
        )
        return {
            'success': True,
            'data': payload,
        }

    return app
