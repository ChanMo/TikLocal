import datetime
import json
from urllib.parse import quote

import pytest

from tiklocal.app import create_app
from tiklocal.services.library import LibraryService
from tiklocal.services.trash import TRASH_DIR


@pytest.fixture
def client(tmp_path):
    media_root = tmp_path / 'media'
    (media_root / 'album').mkdir(parents=True)
    (media_root / 'album' / 'a b.jpg').write_bytes(b'image')
    (media_root / 'clip.mp4').write_bytes(b'video')
    return create_app({'TESTING': True, 'MEDIA_ROOT': media_root}).test_client()


def library_uris(client):
    return {item['name'] for item in client.get('/api/library/items').get_json()['data']['items']}


def trash_delete(client, uri):
    response = client.post(f'/delete/{quote(uri)}', headers={'Accept': 'application/json'})
    assert response.status_code == 200
    return response.get_json()['id']


def test_delete_moves_to_trash_and_restore_puts_it_back(client):
    media_root = client.application.config['MEDIA_ROOT']
    assert '@default/album/a b.jpg' in library_uris(client)
    entry_id = trash_delete(client, 'album/a b.jpg')

    assert '@default/album/a b.jpg' not in library_uris(client)
    assert not (media_root / 'album' / 'a b.jpg').exists()
    items = client.get('/api/trash').get_json()['items']
    assert [(item['id'], item['name'], item['uri']) for item in items] == [(entry_id, 'a b.jpg', '@default/album/a b.jpg')]
    assert client.get('/image?uri=' + quote('album/a b.jpg', safe='')).status_code == 404

    # A rescan must not pick the trashed file back up.
    client.post('/api/library/sync')
    assert '@default/album/a b.jpg' not in library_uris(client)

    restored = client.post(f'/api/trash/{entry_id}/restore')
    assert restored.status_code == 200
    assert restored.get_json() == {'uri': '@default/album/a b.jpg', 'url': '/image?uri=%40default%2Falbum%2Fa%20b.jpg'}
    assert (media_root / 'album' / 'a b.jpg').read_bytes() == b'image'
    assert client.get('/api/trash').get_json()['items'] == []
    assert '@default/album/a b.jpg' in library_uris(client)


def test_restore_refuses_to_overwrite(client):
    media_root = client.application.config['MEDIA_ROOT']
    entry_id = trash_delete(client, 'clip.mp4')
    (media_root / 'clip.mp4').write_bytes(b'new')
    assert client.post(f'/api/trash/{entry_id}/restore').status_code == 409
    assert (media_root / 'clip.mp4').read_bytes() == b'new'


def test_purge_and_expiry(client):
    media_root = client.application.config['MEDIA_ROOT']
    first = trash_delete(client, 'clip.mp4')
    second = trash_delete(client, 'album/a b.jpg')

    assert client.delete(f'/api/trash/{first}').get_json() == {'ok': True}
    assert client.delete(f'/api/trash/{first}').status_code == 404
    assert client.post('/api/trash/..%2F..%2Fetc/restore').status_code == 404

    folder = media_root / TRASH_DIR / second.partition('.')[2]
    entry = json.loads((folder / 'entry.json').read_text())
    entry['deleted_at'] = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=31)).isoformat()
    (folder / 'entry.json').write_text(json.dumps(entry))
    assert client.get('/api/trash').get_json()['items'] == []
    assert not folder.exists()


def test_library_scan_skips_trash(client):
    trash_delete(client, 'clip.mp4')
    service = LibraryService(client.application.config['MEDIA_ROOT'])
    assert [path.name for path in service.scan_source(service.sources[0])] == ['a b.jpg']
