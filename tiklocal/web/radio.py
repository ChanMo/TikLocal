"""Browser Radio: stations, audio metadata, artwork and listening feedback."""

import io
from urllib.parse import quote, unquote

from flask import render_template, request, send_file

from tiklocal.services.radio import RadioCandidate
from tiklocal.web import read_int_arg
from tiklocal.web.media_payloads import media_urls


def register_radio_routes(app, library_service, radio_service, thumbnail_service):
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

    def _serialize_radio_track(item: RadioCandidate) -> dict:
        return {
            'name': item.name,
            **media_urls(item.name),
            'artwork_url': f'/api/radio/artwork?uri={quote(item.name, safe="")}',
            'title': item.title,
            'artist': item.artist,
            'album': item.album,
            'duration': item.duration,
            'is_favorite': item.is_favorite,
        }

    @app.route('/radio')
    def radio_view():
        """Audio Radio Player"""
        return render_template('radio.html', menu='radio')

    @app.route('/api/radio/artwork')
    def api_radio_artwork():
        uri = library_service.find_existing_uri(unquote(request.args.get('uri') or ''))
        path, mimetype = thumbnail_service.get_radio_artwork(uri)
        return send_file(io.BytesIO(path) if isinstance(path, bytes) else path, mimetype=mimetype)

    @app.route('/api/radio/items')
    def api_radio_items():
        offset = read_int_arg('offset', 0, minimum=0)
        limit = read_int_arg('limit', 200, minimum=1, maximum=500)
        audios = radio_service.collect_candidates()
        total = len(audios)
        page = audios[offset:offset + limit]
        items = []
        for track in page:
            metadata = radio_service.metadata_for(track.path)
            items.append({
                **_serialize_radio_track(track),
                'title': metadata.title or track.title,
                'artist': metadata.artist,
                'album': metadata.album,
                'duration': metadata.duration,
            })
        return {'success': True, 'data': {
            'items': items,
            'total': total,
            'has_more': offset + limit < total,
        }}

    @app.route('/api/radio/stations')
    def api_radio_stations():
        return {'success': True, 'data': {'stations': radio_service.list_stations()}}

    @app.route('/api/radio/tune')
    def api_radio_tune():
        limit = read_int_arg('limit', 12, minimum=1, maximum=30)
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
        if event not in {'play', 'complete', 'replay', 'skip', 'favorite', 'error'}:
            return {'success': False, 'error': 'Invalid feedback event'}, 400
        ratio = _positive_ratio(payload.get('ratio'))
        entry = radio_service.record_feedback(uri, event, ratio=ratio)
        return {'success': True, 'data': {'profile': entry}}
