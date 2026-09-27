"""Media details, file delivery, deletion and thumbnail selection."""

import datetime
import io
import math
from pathlib import Path
from urllib.parse import quote, unquote

from flask import redirect, render_template, request, send_file

from tiklocal.services.embedded_metadata import read_embedded_generation
from tiklocal.services.library import IMAGE_EXTENSIONS
from tiklocal.web.media_payloads import media_urls


def register_media_routes(app, library_service, media_index, thumbnail_service, download_manager, trash_service, library_indexer,
                          activity_store):
    def neighbors(media_type, name):
        """Previous and next items in library order (newest first)."""
        names = [str(record['name']) for record in media_index.records(media_type=media_type)]
        try:
            index = names.index(name)
        except ValueError:
            return None, None
        return (names[index - 1] if index > 0 else None,
                names[index + 1] if index < len(names) - 1 else None)

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

        prev_item, next_item = neighbors('video', name)
        prev_item_path_encoded = quote(prev_item, safe='/') if prev_item else None
        next_item_path_encoded = quote(next_item, safe='/') if next_item else None

        canonical = library_service.canonicalize_uri(name)
        stat = target.stat()
        return render_template(
            'detail.html',
            file=name,
            resume=activity_store.positions_for([canonical]).get(canonical),
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

    @app.route('/api/playback', methods=['POST'])
    def api_playback():
        payload = request.get_json(silent=True, force=True) or {}
        uri = library_service.canonicalize_uri(str(payload.get('uri') or ''))
        try:
            position, duration = float(payload.get('position')), float(payload.get('duration'))
        except (TypeError, ValueError):
            return {'error': 'position and duration must be numbers'}, 400
        if not (math.isfinite(position) and math.isfinite(duration)):
            return {'error': 'position and duration must be finite'}, 400
        if not uri or not library_service.resolve_path(uri):
            return {'error': 'Unknown media'}, 404
        return {'saved': activity_store.save_position(uri, position, duration)}

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
        prev_item, next_item = neighbors('image', uri)
        return render_template(
            'image_detail.html',
            previous_url=f"/image?uri={quote(prev_item, safe='')}" if prev_item else None,
            next_url=f"/image?uri={quote(next_item, safe='')}" if next_item else None,
            image=target,
            uri=uri,
            uri_path_encoded=uri_path_encoded,
            uri_query_encoded=uri_query_encoded,
            stat=target.stat(),
            source_meta=source_meta,
        )

    def detail_url(uri):
        if Path(uri).suffix.lower() in IMAGE_EXTENSIONS:
            return f"/image?uri={quote(uri, safe='')}"
        return f"/detail/{quote(uri, safe='/')}"

    def purge(entry_id):
        uri = trash_service.purge(entry_id)
        for candidate in library_service.legacy_candidates(uri):
            download_manager.delete_source_for_file(candidate)
        thumbnail_service.delete_thumbnail(uri)

    def purge_expired():
        for entry_id in trash_service.expired():
            try:
                purge(entry_id)
            except (KeyError, OSError):
                continue

    purge_expired()

    @app.route("/delete/<path:name>", methods=['POST', 'GET'])
    def delete_view(name):
        name = library_service.find_existing_uri(name)
        if request.method == 'GET':
            return render_template('delete_confirm.html', file=name)
        wants_json = request.accept_mimetypes.best == 'application/json'
        try:
            entry = trash_service.move(name)
        except FileNotFoundError:
            media_index.delete(library_service.canonicalize_uri(name))
            return ({'error': 'File not found'}, 404) if wants_json else redirect('/library')
        except OSError as e:
            return ({'error': str(e)}, 500) if wants_json else (f"Error deleting file: {e}", 500)
        media_index.delete(entry['uri'])
        return {'id': entry['id'], 'name': entry['name']} if wants_json else redirect('/library')

    @app.route('/api/trash')
    def api_trash():
        purge_expired()
        return {'items': trash_service.entries(), 'retention_days': trash_service.retention.days}

    @app.route('/api/trash/<entry_id>/restore', methods=['POST'])
    def api_trash_restore(entry_id):
        try:
            uri = trash_service.restore(entry_id)
        except KeyError:
            return {'error': 'Not in trash'}, 404
        except FileExistsError:
            return {'error': 'A file already exists at the original location'}, 409
        library_indexer.register_uris([uri])
        return {'uri': uri, 'url': detail_url(uri)}

    @app.route('/api/trash/<entry_id>', methods=['DELETE'])
    def api_trash_purge(entry_id):
        try:
            purge(entry_id)
        except KeyError:
            return {'error': 'Not in trash'}, 404
        return {'ok': True}

    @app.route('/api/trash', methods=['DELETE'])
    def api_trash_empty():
        items = trash_service.entries()
        for item in items:
            purge(item['id'])
        return {'purged': len(items)}

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
