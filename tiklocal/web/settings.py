"""Home, settings and shared library/cache statistics."""

from flask import render_template


def register_settings_routes(app, media_index, favorite_service, thumbnail_service, app_version):
    @app.route('/')
    def home_view():
        """Quiet launchpad for the local media library."""
        return render_template('home.html', menu='home')

    @app.route('/settings/')
    def settings_view():
        stats = library_stats()
        return render_template(
            'settings.html', menu='settings', version=app_version,
            videos=stats['videos'], images=stats['images'], favorites=stats['favorites'],
            cache_count=stats['cache_count'], cache_size_mb=stats['cache_mb'],
        )

    @app.route('/api/cache/clear', methods=['POST'])
    def api_clear_cache():
        try:
            return {'success': True, **thumbnail_service.clear_cache()}
        except Exception as exc:
            return {'success': False, 'error': str(exc)}, 500

    def library_stats() -> dict:
        index = media_index.stats()
        cache = thumbnail_service.cache_stats()
        return {
            'videos': index['videos'],
            'images': index['images'],
            'audios': index['audios'],
            'indexed_total': index['total'],
            'last_synced_at': index['last_synced_at'],
            'favorites': len(favorite_service.load()),
            'cache_count': cache['count'],
            'cache_mb': cache['size_mb'],
        }

    @app.route('/api/library/stats')
    def api_library_stats():
        return library_stats()
