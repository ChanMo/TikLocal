import os
import io
import json
import random
import datetime
import subprocess as sp
from urllib.parse import quote, unquote
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path

from flask import Flask, render_template, send_from_directory, request, redirect, send_file
from PIL import Image

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

    def _build_feed_media_item(name: str, media_type: str) -> dict[str, str]:
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

    def _collect_source_media_groups(records: list[dict]) -> list[dict]:
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
                    _build_feed_media_item(str(item['name']), str(item['media_type']))
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

    def _collect_library_records(*, favorites_only: bool = False) -> list[dict]:
        favorite_set = favorite_service.load()
        all_paths = library_service.scan_videos() + library_service.scan_images()

        # Deduplicate by both relative path and filesystem identity.
        # This avoids repeated items when media_root contains symlink/hardlink aliases.
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

                media_type = 'image' if path.suffix.lower() in IMAGE_EXTENSIONS else 'video'
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

                # Prefer a favorited alias when deduping the same file identity.
                if candidate['is_favorite'] and not existing['is_favorite']:
                    records_by_identity[identity] = candidate
                    continue

                # Keep deterministic winner for equal identities.
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

    def _build_theme_strip_candidates(records: list[dict]) -> list[dict]:
        records_by_name = {str(item.get('name') or ''): item for item in records if item.get('name')}
        candidates: list[dict] = []

        favorite_records = [
            item for item in records
            if item.get('is_favorite') and item.get('media_type') in {'video', 'image'}
        ]
        favorite_records.sort(key=lambda item: item.get('mtime_ts') or 0, reverse=True)
        favorite_items = [
            _build_feed_media_item(item['name'], item['media_type'])
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
            _build_feed_media_item(name, str(records_by_name[name]['media_type']))
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

    def _read_media_dims_from_metadata(name: str) -> tuple[int | None, int | None]:
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

    def _save_media_dims_to_metadata(name: str, media_type: str, width: int, height: int) -> None:
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

    def _probe_media_dims(name: str, media_type: str) -> tuple[int | None, int | None]:
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

    def _get_or_probe_media_dims(name: str, media_type: str) -> tuple[int | None, int | None]:
        width, height = _read_media_dims_from_metadata(name)
        if width and height:
            return width, height
        width, height = _probe_media_dims(name, media_type)
        if width and height:
            _save_media_dims_to_metadata(name, media_type, width, height)
        return width, height

    def _serialize_library_item(record: dict) -> dict:
        name = str(record.get('name') or '')
        media_type = str(record.get('media_type') or 'video')
        width, height = _get_or_probe_media_dims(name, media_type)
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

    def _collect_collection_records(collection_id: str) -> tuple[dict | None, list[dict]]:
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
            media_type = 'image' if target.suffix.lower() in IMAGE_EXTENSIONS else 'video'
            records.append({
                'name': uri,
                'media_type': media_type,
                'mtime_ts': float(stat.st_mtime),
                'size_bytes': int(stat.st_size),
                'is_favorite': uri in favorites,
            })
        return collection, records

    def _collection_cover_payload(collection: dict) -> tuple[str, str]:
        cover_uri = str(collection.get('cover_uri') or '').strip()
        if cover_uri:
            target = library_service.resolve_path(cover_uri)
            if target and target.exists():
                media_type = 'image' if target.suffix.lower() in IMAGE_EXTENSIONS else 'video'
                return cover_uri, media_type

        uris = collection_store.list_item_uris(str(collection.get('id') or ''), newest_first=True)
        for uri in uris:
            target = library_service.resolve_path(uri)
            if not target or not target.exists():
                continue
            media_type = 'image' if target.suffix.lower() in IMAGE_EXTENSIONS else 'video'
            return uri, media_type
        return '', ''

    def _serialize_collection_summary(collection: dict) -> dict:
        collection_id = str(collection.get('id') or '')
        cover_uri, cover_type = _collection_cover_payload(collection)
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

    def _apply_library_mode(records: list[dict], *, mode: str, min_mb: int, seed: str) -> list[dict]:
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
        records: list[dict] = []
        if collection_id:
            _, records = _collect_collection_records(collection_id)
        else:
            records = _collect_library_records(favorites_only=favorites_only)
            records = _apply_library_mode(records, mode=mode, min_mb=min_mb, seed=seed)
        total = len(records)
        start = max(0, int(offset))
        safe_limit = max(12, min(int(limit), 96))
        end = start + safe_limit
        items = [_serialize_library_item(record) for record in records[start:end]]
        return {
            'items': items,
            'total': total,
            'offset': start,
            'limit': safe_limit,
            'next_offset': end,
            'has_more': end < total,
            'seed': seed,
        }


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
            menu='library',
            scope='all',
            collection_id='',
            collection_name='',
            active_mode=mode,
            mode_seed=initial_page['seed'],
            min_mb=min_mb,
            empty_message='暂无可展示媒体。',
            initial_items=initial_page['items'],
            initial_has_more=initial_page['has_more'],
            initial_offset=initial_page['offset'],
            initial_next_offset=initial_page['next_offset'],
            page_size=initial_page['limit'],
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
            menu='favorite',
            scope='favorite',
            collection_id='',
            collection_name='',
            active_mode='all',
            mode_seed='',
            min_mb=50,
            empty_message='你还没有收藏媒体。',
            initial_items=initial_page['items'],
            initial_has_more=initial_page['has_more'],
            initial_offset=initial_page['offset'],
            initial_next_offset=initial_page['next_offset'],
            page_size=initial_page['limit'],
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
            menu='favorite',
            scope='collection',
            collection_id=collection_id,
            collection_name=str(collection.get('name') or '集合'),
            active_mode='all',
            mode_seed='',
            min_mb=50,
            empty_message='该集合暂无可展示媒体。',
            initial_items=initial_page['items'],
            initial_has_more=initial_page['has_more'],
            initial_offset=initial_page['offset'],
            initial_next_offset=initial_page['next_offset'],
            page_size=initial_page['limit'],
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
        # 首页混合流固定为视频主导密度，降低可预测性由随机混排完成。
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

        # 混排策略：目标比率 + 轻随机约束（避免固定 4V+1I 的可预测节奏）
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
            # 先应用连续上限约束，避免出现过长单一类型段落
            if video_streak >= max_video_streak and ii < len(images):
                want_type = 'image'
            elif image_streak >= max_image_streak and vi < len(videos):
                want_type = 'video'
            else:
                total_used = used_video + used_image
                current_image_ratio = (used_image / total_used) if total_used > 0 else target_image_prob
                # 动态修正：当前图片占比低于目标，则提高本次抽到图片概率
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

        records = _collect_library_records(favorites_only=False)
        theme_candidates = _build_theme_strip_candidates(records)
        source_groups = _collect_source_media_groups(records)
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
            items.append(_build_feed_media_item(name, item_type))

        return {
            'items': items,
            'page': page,
            'has_more': len(mixed_entries) > end,
            'seed': seed,
        }

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

    def _normalize_collection_mutation_uris(raw: object) -> list[str]:
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
