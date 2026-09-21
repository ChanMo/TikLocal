import base64
import io
import json
import sys
import subprocess
from types import SimpleNamespace

import pytest
from PIL import Image
from requests import Response

from tiklocal.app import create_app
from tiklocal.experiments.similarity.embedding import (
    OpenAICompatibleImageEmbeddingClient,
    SQLiteImageVectorStore,
)
from tiklocal.paths import get_database_path
from tiklocal.run import main
from tiklocal.services.database import AppDatabase


@pytest.fixture
def similarity(tmp_path, monkeypatch):
    media = tmp_path / 'media'
    media.mkdir()
    for name in ('a.jpg', 'b.jpg', 'c.jpg'):
        Image.new('RGB', (640, 320), 'red').save(media / name)
    config = dict(enabled=True, base_url='https://embedding.example/v1',
                  model_name='fixture-embedding', dimensions=128,
                  image_max_size=512, image_quality=82)
    # Numerical protocol fixture: this does not evaluate model or retrieval quality.
    wire = SimpleNamespace(calls=[], status=200, body={'data': [{'embedding': [1.0] + [0.0] * 127}]})

    def post(url, **kwargs):
        wire.calls.append({'url': url, **kwargs})
        response = Response()
        response.status_code = wire.status
        response._content = json.dumps(wire.body).encode()
        return response

    monkeypatch.setattr('tiklocal.experiments.similarity.embedding.requests.post', post)
    monkeypatch.setenv('TIKLOCAL_EMBEDDING_API_KEY', 'test-key')
    monkeypatch.setenv('HOME', str(tmp_path))
    config_path = tmp_path / '.config/tiklocal/config.yaml'
    config_path.parent.mkdir(parents=True)
    config_path.write_text(json.dumps({'embedding': config}))
    app = create_app({'TESTING': True, 'MEDIA_ROOT': media, 'EMBEDDING_CONFIG': config})
    store = SQLiteImageVectorStore(AppDatabase(get_database_path()))
    def run_cli(*args):
        monkeypatch.setattr(sys, 'argv', ['tiklocal', args[0], str(media), *args[1:]])
        main()

    return SimpleNamespace(client=app.test_client(), store=store, media=media, config=config,
                           wire=wire, run_cli=run_cli)


def test_index_is_persistent_and_repeat_build_skips_current_images(similarity):
    client, wire = similarity.client, similarity.wire
    status = client.get('/api/ai/embedding-index/status').json['data']
    assert status['missing'] == 3
    assert wire.calls == []
    similarity.run_cli('vectorize', '--yes')
    similarity.run_cli('vectorize', '--yes')
    assert len(wire.calls) == 3
    assert len(similarity.store.get_all_metadata()) == 3

    data = client.get('/api/recommend/similar?uri=a.jpg&limit=4').json['data']
    assert data['indexed'] is True
    assert {item['name'] for item in data['items']} == {'@default/b.jpg', '@default/c.jpg'}
    (similarity.media / 'b.jpg').unlink()
    data = client.get('/api/recommend/similar?uri=a.jpg').json['data']
    assert [item['name'] for item in data['items']] == ['@default/c.jpg']


def test_embedding_request_encodes_real_image_with_default_resize(similarity):
    client = OpenAICompatibleImageEmbeddingClient(
        model='fixture-embedding', base_url=similarity.config['base_url'], dimensions=128,
    )
    assert len(client.embed_image(similarity.media / 'a.jpg')) == 128
    call = similarity.wire.calls[0]
    assert call['url'] == 'https://embedding.example/v1/embeddings'
    assert call['headers']['Authorization'] == 'Bearer test-key'
    assert call['json']['model'] == 'fixture-embedding'
    assert call['json']['dimensions'] == 128
    data_url = call['json']['input'][0]['content'][0]['image_url']['url']
    with Image.open(io.BytesIO(base64.b64decode(data_url.split(',', 1)[1]))) as image:
        assert image.format == 'JPEG'
        assert image.size == (512, 256)


@pytest.mark.parametrize('status,body', [(503, {'error': 'unavailable'}), (200, {'data': []})])
def test_failed_rebuild_preserves_old_vectors(similarity, status, body, capsys):
    client = similarity.client
    similarity.run_cli('vectorize', '--yes')
    before = similarity.store.list_vectors()
    updated = {**similarity.config, 'model_name': 'new-model'}
    assert client.post('/api/ai/embedding-config', json=updated).status_code == 200
    assert client.get('/api/ai/embedding-index/status').json['data']['stale'] == 3
    similarity.wire.status, similarity.wire.body = status, body
    capsys.readouterr()
    similarity.run_cli('vectorize', '--yes')
    assert 'failed: 3' in capsys.readouterr().out
    assert client.get('/api/ai/embedding-index/status').json['data']['stale_reasons'] == {'model': 3}
    assert similarity.store.list_vectors() == before


@pytest.mark.parametrize('field,value', [('base_url', 'ftp://example.com'),
                                       ('dimensions', 64), ('image_max_size', 64)])
def test_invalid_config_does_not_replace_saved_profile(similarity, field, value):
    client = similarity.client
    saved = {**similarity.config, 'model_name': 'saved-model'}
    assert client.post('/api/ai/embedding-config', json=saved).status_code == 200
    response = client.post('/api/ai/embedding-config', json={**saved, field: value})
    assert response.status_code == 400 and field in response.json['error']
    assert client.get('/api/ai/embedding-config').json['data']['effective']['model_name'] == 'saved-model'
    reset = client.post('/api/ai/embedding-config/reset').json['data']
    assert reset['effective']['model_name'] == similarity.config['model_name']


def test_sqlite_search_excludes_incompatible_models_and_dimensions(tmp_path):
    database = AppDatabase(tmp_path / 'vectors.sqlite3')
    database.migrate()
    store = SQLiteImageVectorStore(database)
    for name, vector, model in [('a', [1.0, 0.0], 'model'), ('b', [0.9, 0.1], 'model'),
                                ('c', [1.0, 0.0], 'other'), ('d', [1.0, 0.0, 0.0], 'model')]:
        store.upsert_image(uri=f'@default/{name}.jpg', embedding=vector, metadata={
            'source_id': 'default', 'rel_path': f'{name}.jpg', 'model': model,
            'dimensions': len(vector), 'image_max_size': 512, 'image_quality': 82,
            'mtime': 1, 'size_bytes': 100, 'indexed_at': '2026-06-07T00:00:00Z',
        })
    results = store.query_similar('@default/a.jpg')
    assert [item['uri'] for item in results] == ['@default/b.jpg']
    assert results[0]['distance'] == pytest.approx(0.006116, abs=1e-6)
    store.delete(['@default/b.jpg'])
    assert store.query_similar('@default/a.jpg') == []


def test_cli_dry_run_reports_limit_without_calling_provider(similarity, capsys):
    similarity.run_cli('vectorize', '--dry-run', '--limit', '1')
    assert 'selected this run: 1' in capsys.readouterr().out
    assert similarity.wire.calls == []
    assert similarity.store.get_all_metadata() == {}


def test_cli_groups_survive_disabling_and_reenabling_experiment(similarity):
    similarity.run_cli('vectorize', '--yes')
    similarity.run_cli('analyze-similar', '--yes')
    disabled = create_app({'TESTING': True, 'MEDIA_ROOT': similarity.media,
                           'EXPERIMENTS': {'similarity': {'enabled': False}}}).test_client()
    assert disabled.get('/api/library/similar-groups').status_code == 404
    assert disabled.get('/library?mode=similar_images').status_code == 404
    reopened = create_app({'TESTING': True, 'MEDIA_ROOT': similarity.media,
                          'EXPERIMENTS': {'similarity': {'enabled': True}}}).test_client()
    response = reopened.get('/api/library/similar-groups?min_group_size=3')
    assert response.status_code == 200
    groups = response.json['data']['items']
    assert len(groups) == 1 and groups[0]['count'] == 3
    assert {item['name'] for item in groups[0]['items']} == {'@default/a.jpg', '@default/b.jpg', '@default/c.jpg'}
    assert reopened.get('/library?mode=similar_images').location == '/experiments/similarity'
    assert reopened.get('/experiments/similarity').status_code == 200
    assert len(similarity.wire.calls) == 3  # Local grouping and result reads incur no model calls.


@pytest.mark.parametrize('explicit,legacy,expected', [
    (False, True, 404), (True, False, 200), (None, True, 200),
    (None, False, 404), (None, 'false', 404),
])
def test_startup_switch_overrides_legacy_build_flag(tmp_path, explicit, legacy, expected):
    experiments = {'similarity': {'enabled': explicit}} if explicit is not None else {}
    client = create_app({'TESTING': True, 'MEDIA_ROOT': tmp_path,
                         'EXPERIMENTS': experiments, 'EMBEDDING_CONFIG': {'enabled': legacy}}).test_client()
    assert client.get('/api/ai/embedding-index/status').status_code == expected
    assert client.get('/experiments/similarity').status_code == expected
    assert client.get('/library').status_code == 200


def test_web_build_is_retired_and_read_only_views_never_call_model(similarity):
    assert similarity.client.post('/api/ai/embedding-index/run').status_code == 410
    assert similarity.client.get('/experiments/similarity').status_code == 200
    assert similarity.client.get('/api/recommend/similar?uri=a.jpg').status_code == 200
    assert similarity.wire.calls == []
    assert similarity.store.get_all_metadata() == {}


def test_saved_legacy_config_enables_experiment_but_explicit_false_blocks_cli(similarity, monkeypatch):
    assert similarity.client.post('/api/ai/embedding-config', json=similarity.config).status_code == 200
    reopened = create_app({'TESTING': True, 'MEDIA_ROOT': similarity.media}).test_client()
    assert reopened.get('/experiments/similarity').status_code == 200
    monkeypatch.setattr('tiklocal.run.load_config', lambda: {'experiments': {'similarity': {'enabled': False}}})
    with pytest.raises(SystemExit) as error:
        similarity.run_cli('vectorize', '--yes')
    assert error.value.code == 2 and similarity.wire.calls == []


def test_default_core_startup_and_routes_do_not_load_vector_runtime(tmp_path):
    script = """
import sys
from tiklocal.app import create_app
app = create_app({'TESTING': True, 'MEDIA_ROOT': sys.argv[1]})
client = app.test_client()
for url in ('/', '/library', '/radio', '/saved', '/download'):
    assert client.get(url).status_code == 200, url
for part in ('embedding', 'groups', 'web', 'cli'):
    assert 'tiklocal.experiments.similarity.' + part not in sys.modules, part
for url in ('/experiments/similarity', '/api/ai/embedding-index/status', '/api/recommend/similar?uri=a.jpg'):
    assert client.get(url).status_code == 404, url
"""
    subprocess.run([sys.executable, '-c', script, str(tmp_path)], check=True, capture_output=True, text=True)
