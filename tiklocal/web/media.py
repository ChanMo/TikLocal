"""Media details, file delivery, deletion and thumbnail selection."""

import datetime
import io
from urllib.parse import quote, unquote

from flask import redirect, render_template, request, send_file

from tiklocal.services.embedded_metadata import read_embedded_generation
from tiklocal.services.library import IMAGE_EXTENSIONS
from tiklocal.web.media_payloads import media_urls


def register_media_routes(app, library_service, media_index, thumbnail_service, download_manager):
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

        stat = target.stat()
        return render_template(
            'detail.html',
            file=name,
            file_path_encoded=file_path_encoded,
            file_query_encoded=file_query_encoded,
            mtime=datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
            size=stat.st_size,
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
        return send_file(io.BytesIO(path) if isinstance(path, bytes) else path, mimetype=mimetype)

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

    @app.route('/api/thumbnail/<path:name>', methods=['POST'])
    def api_set_thumbnail(name):
        name = library_service.find_existing_uri(name)
        target = library_service.resolve_path(name)
        if not target: return {'success': False, 'error': 'Invalid path'}, 400

        payload = request.get_json(silent=True) or {}
        ts = payload.get('time')

        success = thumbnail_service.generate_thumbnail(name, timestamp=float(ts) if ts is not None else None)

        if success:
             return {'success': True, 'url': f"{media_urls(name)['thumb_url']}&v={int(datetime.datetime.now().timestamp())}"}
        return {'success': False, 'error': 'Failed to generate'}, 500
