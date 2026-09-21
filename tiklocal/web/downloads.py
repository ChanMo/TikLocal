from flask import render_template, request

from tiklocal.services.downloader import (
    DEFAULT_DOWNLOAD_CONFIG, validate_download_config, validate_download_url,
)


def register_download_routes(app, download_manager, library_service):
    def build_download_config_payload():
        config = download_manager.get_config()
        effective = {key: config.get(key) for key in DEFAULT_DOWNLOAD_CONFIG.keys()}
        payload = {
            'config': config,
            'defaults': dict(DEFAULT_DOWNLOAD_CONFIG),
            'effective': effective,
        }
        return payload

    @app.route('/download')
    def download_view():
        """URL Download Center"""
        return render_template('download.html', menu='download')

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
            return {'success': False, 'error': 'No upload file was provided.'}, 400

        filename = str(file.filename or '').strip()
        if not filename:
            return {'success': False, 'error': 'The filename cannot be empty.'}, 400

        content = file.read()
        try:
            # Uploading consistently replaces a file with the same name.
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
            return {'success': False, 'error': 'file cannot be empty.'}, 400
        file_rel = library_service.find_existing_uri(file_rel)
        source = download_manager.resolve_source_for_file(file_rel)
        return {'success': True, 'data': {'file': file_rel, 'source': source}}

    @app.route('/api/source/batch', methods=['POST'])
    def api_source_batch():
        payload = request.get_json(silent=True) or {}
        files = payload.get('files')
        if not isinstance(files, list):
            return {'success': False, 'error': 'files must be an array.'}, 400

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
