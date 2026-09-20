import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from PIL import Image

from tiklocal.app import create_app
from tiklocal.services.metadata import ImageMetadataStore


def test_concurrent_favorites_keep_every_update(tmp_path):
    app = create_app({'TESTING': True, 'MEDIA_ROOT': tmp_path})
    names = [f'@default/photo-{i}.jpg' for i in range(32)]

    def favorite(name):
        with app.test_client() as client:
            return client.post(f'/api/favorite/{name}').get_json()['favorite']

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert all(pool.map(favorite, names))
    client = app.test_client()
    assert all(client.get(f'/api/favorite/{name}').get_json()['favorite'] for name in names)


@pytest.mark.parametrize('failure', ['replace', 'corrupt'])
def test_failed_favorite_write_preserves_file_and_reports_failure(tmp_path, monkeypatch, failure):
    client = create_app({'TESTING': True, 'MEDIA_ROOT': tmp_path}).test_client()
    assert client.post('/api/favorite/photo.jpg').get_json()['favorite']
    path = tmp_path / 'tiklocal-data' / 'favorites.json'
    if failure == 'corrupt':
        path.write_text('[broken', encoding='utf-8')
    else:
        def fail_replace(source, destination):
            raise PermissionError('read-only storage')
        monkeypatch.setattr(os, 'replace', fail_replace)
    before = path.read_bytes()

    response = client.post('/api/favorite/photo.jpg')

    assert response.status_code == 503
    assert response.get_json()['success'] is False
    assert path.read_bytes() == before


def test_caption_update_preserves_dimensions_written_after_old_snapshot(tmp_path):
    store = ImageMetadataStore(tmp_path / 'metadata.json')
    uri = '@default/photo.jpg'
    store.set(uri, {'title': 'old', 'media_meta': {'width': 10, 'height': 10}})
    old = store.get(uri)
    dimensions = {'width': 120, 'height': 80}
    store.update_many({uri: {'media_meta': dimensions}})
    store.update_many({uri: {'title': 'new'}}, defaults={uri: old})
    assert store.get(uri) == {'title': 'new', 'media_meta': dimensions}


def test_dimension_cache_preserves_legacy_caption_and_degrades_on_write_failure(tmp_path, monkeypatch):
    media = tmp_path / 'media'
    media.mkdir()
    Image.new('RGB', (120, 80)).save(media / 'photo.jpg')
    client = create_app({'TESTING': True, 'MEDIA_ROOT': media}).test_client()
    path = tmp_path / 'tiklocal-data' / 'metadata.json'
    store = ImageMetadataStore(path)
    store.set('photo.jpg', {'title': 'Existing title', 'tags': ['saved']})
    before = path.read_bytes()
    with monkeypatch.context() as fault:
        def fail_replace(source, destination):
            raise PermissionError('read-only storage')
        fault.setattr(os, 'replace', fail_replace)
        item = client.get('/api/library/items').get_json()['data']['items'][0]
        assert (item['width'], item['height']) == (120, 80)
        assert path.read_bytes() == before

    client.get('/api/library/items')
    metadata = client.get('/api/image/metadata?uri=@default/photo.jpg').get_json()['data']
    assert metadata['title'] == 'Existing title' and metadata['tags'] == ['saved']
    assert (metadata['media_meta']['width'], metadata['media_meta']['height']) == (120, 80)
