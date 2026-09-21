from flask import request

from tiklocal.services.captions import generate_caption, validate_prompt_config


def register_caption_routes(app, library, metadata, settings):
    def profile_response(kind, reset=False):
        store = settings.profiles[kind]
        try:
            if reset:
                store.reset()
            elif request.method == 'POST':
                value, error = store.validate(request.get_json(silent=True) or {})
                if error:
                    return {'success': False, 'error': error}, 400
                store.set(value)
            return {'success': True, 'data': settings.resolve()[kind]}
        except OSError:
            return {'success': False, 'error': 'The configuration could not be saved. Please try again later.'}, 503

    @app.route('/api/ai/prompt-config', methods=['GET', 'POST'])
    def api_prompt_config():
        return profile_response('prompt')

    @app.post('/api/ai/prompt-config/reset')
    def api_prompt_config_reset():
        return profile_response('prompt', reset=True)

    @app.route('/api/ai/llm-config', methods=['GET', 'POST'])
    def api_llm_config():
        return profile_response('llm')

    @app.post('/api/ai/llm-config/reset')
    def api_llm_config_reset():
        return profile_response('llm', reset=True)

    @app.get('/api/ai/vision-config')
    def api_vision_config():
        return {'success': True, 'data': settings.resolve()['vision']}

    @app.route('/api/image/metadata', methods=['GET', 'POST'])
    def api_image_metadata():
        payload = request.get_json(silent=True) or {}
        uri = request.args.get('uri') if request.method == 'GET' else payload.get('uri')
        if not uri:
            return {'success': False, 'error': 'Missing uri'}, 400
        uri = library.canonicalize_uri(uri)
        try:
            keys = library.legacy_candidates(uri)
            saved = metadata.get_many(keys)
            existing = next((saved[key] for key in keys if saved.get(key) is not None), None)
        except (OSError, ValueError):
            return {'success': False, 'error': 'Image information could not be read. Please try again later.'}, 503
        if request.method == 'GET':
            return {'success': True, 'data': existing}

        override = payload.get('prompt_override')
        if override is not None:
            override, error = validate_prompt_config(override, partial=True)
            if error:
                return {'success': False, 'error': error}, 400
        if existing and (existing.get('title') or existing.get('tags')) and not payload.get('force'):
            return {'success': True, 'data': existing, 'skipped': True}
        target = library.resolve_path(uri)
        if not target or not target.is_file():
            return {'success': False, 'error': 'File not found'}, 404

        resolved = settings.resolve(override)['vision']
        if not resolved['effective']['enabled']:
            return {'success': False, 'error': 'Image recognition is disabled. Set vision.enabled in the configuration file.'}, 400
        try:
            result = generate_caption(target, resolved)
            merged = metadata.update_many({uri: result}, defaults={uri: existing or {}})[uri]
            return {'success': True, 'data': merged}
        except Exception as error:
            return {'success': False, 'error': str(error)}, 500
