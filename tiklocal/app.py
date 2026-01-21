import os
import json
import random
import datetime
from urllib.parse import quote, unquote
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path

from flask import Flask, render_template, send_from_directory, request, redirect, send_file

# Service Imports
from tiklocal.services import LibraryService, FavoriteService, RecommendService
from tiklocal.services.thumbnail import ThumbnailService

try:
    app_version = version("tiklocal")
except PackageNotFoundError:
    app_version = '1.0.0'

def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_prefixed_env()
    app.config.from_mapping(
        SECRET_KEY = 'dev',
        MEDIA_ROOT = Path(os.environ.get('MEDIA_ROOT', '.'))
    )
    app.config.from_pyfile('config.py', silent=True)
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


    # --- Web Routes ---
    @app.route('/')
    def tiktok():
        """Immersive Video Feed"""
        return render_template('tiktok.html', menu='index')

    @app.route('/gallery')
    def gallery():
        """Immersive Image Discovery"""
        return render_template('gallery.html', menu='gallery')

    @app.route('/browse')
    def browse():
        """Video Library List"""
        # Using scan_videos instead of recursive get_files
        videos = library_service.scan_videos()
        
        # Filter Logic
        size_mode = request.args.get('size', 'all')
        min_mb = int(request.args.get('min_mb', 50))
        
        if size_mode == 'big':
            threshold = min_mb * 1024 * 1024
            videos = [v for v in videos if v.stat().st_size >= threshold]

        # Pagination
        count = len(videos)
        page = int(request.args.get('page', 1))
        length = 20
        offset = length * (page - 1)
        
        # Convert to relative strings for template
        sliced_videos = [library_service.get_relative_path(v) for v in videos[offset:offset+length]]
        
        return render_template(
            'browse.html',
            page=page,
            count=count,
            length=length,
            files=sliced_videos,
            menu='browse',
            size_mode=size_mode,
            min_mb=min_mb,
            has_min_mb=request.args.get('min_mb') is not None,
            has_previous=page > 1,
            has_next=len(videos) > offset + length
        )

    @app.route('/settings/')
    def settings_view():
        video_count = len(library_service.scan_videos())
        return render_template('settings.html', menu='settings', version=app_version, videos=video_count)

    @app.route('/library')
    def library_redirect():
        return redirect('/browse')


    # --- Detail & Action Routes ---
    
    @app.route('/detail/<path:name>')
    def detail_view(name):
        target = library_service.resolve_path(name)
        if not target or not target.exists():
            return "File not found", 404
        
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

        return render_template(
            'detail.html',
            file=name,
            mtime=datetime.datetime.fromtimestamp(target.stat().st_mtime).strftime('%Y-%m-%d %H:%M'),
            size=target.stat().st_size,
            previous_item=prev_item,
            next_item=next_item
        )
    
    @app.route('/image')
    def image_view():
        uri = request.args.get('uri')
        if not uri: return "Missing uri", 400
        
        target = library_service.resolve_path(uri)
        if not target or not target.exists(): return "File not found", 404
        
        return render_template('image_detail.html', image=target, uri=uri, stat=target.stat())

    @app.route("/delete/<path:name>", methods=['POST', 'GET'])
    def delete_view(name):
        target = library_service.resolve_path(name)
        if request.method == 'POST':
            if target and target.exists():
                try:
                    target.unlink()
                    # Thumbnails are handled by OS or periodic cleanup, but ideally Service should handle it
                except Exception as e:
                    return f"Error deleting file: {e}", 500
            return redirect('/browse')

        return render_template('delete_confirm.html', file=name)
        
    @app.route("/delete", methods=['POST', 'GET'])
    def delete_confirm_legacy():
        # Legacy support for query param style
        uri = request.args.get('uri')
        if not uri: return redirect('/browse')
        return redirect(f"/delete/{quote(uri)}")

    @app.route('/favorite')
    def favorite_view():
        return render_template('favorite.html', files=list(favorite_service.load()))


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
        return redirect(f"/media/{uri}")

    @app.route('/thumb')
    def thumb_view():
        uri = request.args.get('uri')
        if not uri: return send_file(io.BytesIO(thumbnail_service.placeholder), mimetype='image/png')
        
        path, mimetype = thumbnail_service.get_thumbnail(unquote(uri))
        if isinstance(path, bytes):
            return send_file(io.BytesIO(path), mimetype=mimetype)
        return send_file(path, mimetype=mimetype)


    # --- API Routes ---

    @app.route('/api/videos')
    def api_videos():
        # Clean JSON API
        selected = recommend_service.get_weighted_selection(file_type='video', limit=20)
        return json.dumps(selected)

    @app.route('/api/random-images')
    def api_random_images():
        page = int(request.args.get('page', 1))
        size = int(request.args.get('size', 30))
        seed = request.args.get('seed') or str(random.randint(1, 999999))
        
        # Get recommended images (all of them, weighted)
        # Note: RecommendService currently returns a list. For true scale, we'd paginate inside Service.
        # For now, consistent with previous behavior, we get all and slice.
        all_images = recommend_service.get_weighted_selection(file_type='image', limit=99999, seed=seed)
        
        total = len(all_images)
        start = (page - 1) * size
        end = start + size
        page_images = all_images[start:end]
        
        return {
            'images': page_images,
            'page': page,
            'total': total,
            'has_more': end < total,
            'seed': seed
        }

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

    return app