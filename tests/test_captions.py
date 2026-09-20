import json
from types import SimpleNamespace

import pytest
import requests
from PIL import Image

from tiklocal.app import create_app
from tiklocal.services.metadata import ImageMetadataStore


KEYS = ['TIKLOCAL_VISION_API_KEY', 'TIKLOCAL_AI_API_KEY', 'OPENAI_API_KEY', 'OPENROUTER_API_KEY']
PROMPT = {'enabled': True, 'system_prompt': 'custom system', 'user_prompt': 'tags {tags_limit}',
          'tags_limit': 7, 'temperature': 0.4}
LLM = {'model_name': 'custom-model', 'base_url': 'https://custom.example/v1'}


@pytest.fixture
def caption_app(tmp_path, monkeypatch):
    for name in KEYS + ['TIKLOCAL_VISION_MODEL', 'TIKLOCAL_VISION_BASE_URL', 'TIKLOCAL_LLM_BASE_URL']:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('OPENAI_API_KEY', 'fixture-key')
    monkeypatch.setenv('TIKLOCAL_LLM_MODEL', 'env-model')
    media = tmp_path / 'media'
    media.mkdir()
    Image.new('RGB', (120, 80)).save(media / 'photo.jpg')
    # A protocol fixture exercises encoding/parsing/persistence, never caption quality.
    wire = {'calls': [], 'status': 200, 'error': None,
            'body': {'choices': [{'message': {'content': '{"title":"transport-fixture","tags":[]}'}}]}}

    def post(url, **kwargs):
        wire['calls'].append((url, kwargs))
        if wire['error']:
            raise wire['error']
        return SimpleNamespace(status_code=wire['status'], text=json.dumps(wire['body']), json=lambda: wire['body'])

    monkeypatch.setattr('tiklocal.services.captions.requests.post', post)
    return lambda vision=None: create_app({'TESTING': True, 'MEDIA_ROOT': media, 'VISION_CONFIG': vision}).test_client(), wire


@pytest.mark.parametrize('kind,value', [('prompt', PROMPT), ('llm', LLM)])
def test_editable_profile_roundtrip_and_reset(caption_app, kind, value):
    create, _ = caption_app
    client = create()
    url = f'/api/ai/{kind}-config'
    assert client.get(url).get_json()['data']['active_profile'] == 'default'
    assert client.post(url, json=value).status_code == 200
    saved = client.get(url).get_json()['data']
    assert saved['active_profile'] == 'custom'
    assert all(saved['custom'][key] == expected for key, expected in value.items())
    reset = client.post(url + '/reset').get_json()['data']
    assert reset['active_profile'] == 'default' and reset['custom'] is None


@pytest.mark.parametrize('kind,value', [
    ('prompt', {**PROMPT, 'temperature': 2.5}), ('prompt', {**PROMPT, 'tags_limit': 0}),
    ('prompt', {**PROMPT, 'system_prompt': ''}), ('llm', {**LLM, 'base_url': 'ftp://invalid'}),
])
def test_invalid_profile_is_rejected_without_replacing_saved_config(caption_app, kind, value):
    create, _ = caption_app
    client = create()
    url = f'/api/ai/{kind}-config'
    client.post(url, json=PROMPT if kind == 'prompt' else LLM)
    before = client.get(url).get_json()['data']
    assert client.post(url, json=value).status_code == 400
    assert client.get(url).get_json()['data'] == before


@pytest.mark.parametrize('vision,override,model,temperature,source', [
    (None, None, 'custom-model', 0.4, 'custom'),
    ({'model_name': 'vision-model'}, None, 'vision-model', 0.6, 'config'),
    ({'enabled': True}, None, 'custom-model', 0.6, 'config'),
    ({'base_url': 'https://vision.example/v1'}, None, 'env-model', 0.6, 'config'),
    ({'model_name': 'vision-model'}, {'temperature': 0.9}, 'vision-model', 0.9, 'override'),
])
def test_generation_respects_config_precedence_and_matches_display(caption_app, vision, override, model, temperature, source):
    create, wire = caption_app
    client = create(vision)
    client.post('/api/ai/prompt-config', json=PROMPT)
    client.post('/api/ai/llm-config', json=LLM)
    displayed = client.get('/api/ai/vision-config').get_json()['data']['effective']
    response = client.post('/api/image/metadata', json={'uri': 'photo.jpg', 'prompt_override': override})
    assert response.status_code == 200
    request = wire['calls'][-1][1]['json']
    assert request['model'] == model == displayed['model_name']
    assert request['temperature'] == temperature
    assert request['messages'][0]['content'] == displayed['system_prompt']
    assert request['messages'][1]['content'][1]['image_url']['url'].startswith('data:image/jpeg;base64,')
    assert response.get_json()['data']['prompt_source'] == source
    assert displayed['temperature'] == (0.6 if vision else 0.4)  # Overrides are request-local.


@pytest.mark.parametrize('winner', range(len(KEYS)))
def test_key_precedence_and_config_presence_match_actual_request(caption_app, monkeypatch, winner):
    create, wire = caption_app
    for index, name in enumerate(KEYS):
        if index < winner:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, f'fixture-secret-{index}')
    client = create()
    for kind in ('llm', 'vision'):
        response = client.get(f'/api/ai/{kind}-config')
        assert response.get_json()['data']['has_api_key'] is True
        assert 'fixture-secret' not in response.get_data(as_text=True)
    assert client.post('/api/image/metadata', json={'uri': 'photo.jpg'}).status_code == 200
    assert wire['calls'][-1][1]['headers']['Authorization'] == f'Bearer fixture-secret-{winner}'


@pytest.mark.parametrize('condition,status', [('disabled', 400), ('no_model', 500), ('no_key', 500)])
def test_unavailable_caption_configuration_never_calls_provider(caption_app, monkeypatch, condition, status):
    create, wire = caption_app
    if condition == 'no_model':
        monkeypatch.delenv('TIKLOCAL_LLM_MODEL')
    if condition == 'no_key':
        monkeypatch.delenv('OPENAI_API_KEY')
    client = create({'enabled': False} if condition == 'disabled' else None)
    response = client.post('/api/image/metadata', json={'uri': 'photo.jpg'})
    assert response.status_code == status and not response.get_json()['success']
    assert wire['calls'] == []


def test_dimension_only_metadata_allows_generation_and_saved_caption_skips_it(caption_app, tmp_path):
    create, wire = caption_app
    client = create()
    store = ImageMetadataStore(tmp_path / 'tiklocal-data' / 'metadata.json')
    dimensions = {'width': 120, 'height': 80}
    store.set('photo.jpg', {'media_meta': dimensions})
    response = client.post('/api/image/metadata', json={'uri': 'photo.jpg'})
    assert response.status_code == 200 and len(wire['calls']) == 1
    saved = client.get('/api/image/metadata?uri=@default/photo.jpg').get_json()['data']
    assert saved == response.get_json()['data'] and saved['media_meta'] == dimensions
    assert client.post('/api/image/metadata', json={'uri': 'photo.jpg'}).get_json()['skipped'] is True
    assert len(wire['calls']) == 1


@pytest.mark.parametrize('failure', ['timeout', 'http_error', 'empty', 'empty_object', 'html'])
def test_generation_failure_does_not_overwrite_existing_metadata(caption_app, tmp_path, failure):
    create, wire = caption_app
    client = create()
    if failure == 'timeout':
        wire['error'] = requests.Timeout('provider timed out')
    elif failure == 'http_error':
        wire.update(status=429, body={'error': {'message': 'rate limited'}})
    else:
        content = {'empty': '', 'empty_object': '{}', 'html': '<html>upstream error</html>'}[failure]
        wire['body'] = {'choices': [{'message': {'content': content}}]}
    path = tmp_path / 'tiklocal-data' / 'metadata.json'
    ImageMetadataStore(path).set('@default/photo.jpg', {'title': 'keep', 'tags': ['saved'], 'media_meta': {'width': 120}})
    before = path.read_bytes()
    response = client.post('/api/image/metadata', json={'uri': 'photo.jpg', 'force': True})
    assert response.status_code == 500 and not response.get_json()['success']
    assert path.read_bytes() == before
