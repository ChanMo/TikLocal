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


def test_dimensions_are_probed_in_background_and_refreshed_after_change(tmp_path):
    media = tmp_path / 'media'
    media.mkdir()
    photo = media / 'photo.jpg'
    Image.new('RGB', (120, 80)).save(photo)
    (media / 'broken.jpg').write_bytes(b'not an image')
    app = create_app({'TESTING': True, 'MEDIA_ROOT': media})
    client = app.test_client()
    probe = app.extensions['media_probe']

    def sizes():
        items = client.get('/api/library/items').get_json()['data']['items']
        return {item['name']: (item['width'], item['height']) for item in items}

    assert sizes()['@default/photo.jpg'] == (None, None)
    assert probe.run_once() == 2
    assert sizes() == {'@default/photo.jpg': (120, 80), '@default/broken.jpg': (None, None)}
    assert probe.run_once() == 0

    Image.new('RGB', (60, 90)).save(photo)
    os.utime(photo, (1, 1))
    client.post('/api/library/sync')
    assert probe.run_once() == 1
    assert sizes()['@default/photo.jpg'] == (60, 90)

