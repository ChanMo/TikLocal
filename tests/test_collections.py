from urllib.parse import quote

import pytest

from tiklocal.app import create_app


@pytest.fixture
def client(tmp_path):
    media_root = tmp_path / 'media'
    media_root.mkdir()
    for name in ['clip.mp4', 'cover.jpg', 'odd & hash#.jpg', 'extra-a.jpg', 'extra-b.jpg']:
        (media_root / name).write_bytes(b'media')
    return create_app({'TESTING': True, 'MEDIA_ROOT': media_root}).test_client()


def test_collection_edit_cover_persists_and_delete_removes_collection(client):
    created = client.post('/api/collections', json={'name': '灵感', 'description': '片段'})
    assert created.status_code == 200
    item = created.get_json()['data']['item']
    url = f"/api/collections/{item['id']}"
    assert item['item_count'] == 0
    assert client.get('/api/collections').get_json()['data']['items'] == [item]
    client.post(f'{url}/items', json={
        'uris': ['cover.jpg', 'clip.mp4', 'odd & hash#.jpg', 'extra-a.jpg', 'extra-b.jpg'],
    })

    updated = client.patch(url, json={'name': '新名字', 'cover_uri': 'cover.jpg'})
    assert updated.status_code == 200
    saved = client.get(url).get_json()['data']['item']
    assert saved == updated.get_json()['data']['item']
    assert (saved['name'], saved['description']) == ('新名字', '片段')
    assert saved['cover_uri'] == saved['preview_items'][0]['uri'] == '@default/cover.jpg'
    assert len(saved['preview_items']) == 4
    assert client.patch(url, json={'cover_uri': 'not-a-member.jpg'}).status_code == 400
    assert client.get(url).get_json()['data']['item'] == saved

    deleted = client.delete(url)
    assert deleted.status_code == 200 and deleted.get_json()['data']['deleted'] is True
    assert client.get(url).status_code == 404
    assert client.get('/api/collections').get_json()['data']['items'] == []


def test_collection_membership_deduplicates_aliases_and_removal_updates_lookup(client):
    collection_id = client.post('/api/collections', json={'name': '收藏'}).get_json()['data']['item']['id']
    url = f'/api/collections/{collection_id}/items'
    added = client.post(url, json={
        'uris': ['./clip.mp4', '@default/clip.mp4', 'odd & hash#.jpg', '', 'odd & hash#.jpg'],
    })
    assert added.status_code == 200
    item = added.get_json()['data']['item']
    assert item['item_count'] == 2
    assert [entry['uri'] for entry in item['preview_items']] == [
        '@default/odd & hash#.jpg', '@default/clip.mp4',
    ]
    assert item['preview_items'][0]['thumb_url'] == '/thumb?uri=' + quote('@default/odd & hash#.jpg')
    lookup = client.get('/api/collections/by-media', query_string={'uri': 'odd & hash#.jpg'})
    assert [entry['id'] for entry in lookup.get_json()['data']['items']] == [collection_id]

    removed = client.delete(url, json={'uris': ['clip.mp4']})
    assert removed.status_code == 200
    assert removed.get_json()['data']['item']['item_count'] == 1
    assert client.get('/api/collections/by-media?uri=clip.mp4').get_json()['data']['items'] == []
    assert client.post(url, json={'uris': 'clip.mp4'}).status_code == 400
    assert client.get('/api/library/items?scope=collection').status_code == 400


@pytest.mark.parametrize('endpoint', ['library', 'collection'])
def test_collection_pages_keep_member_order_without_gaps(client, endpoint):
    names = [f'page-{i:02d}.jpg' for i in range(25)]
    for name in names:
        (client.application.config['MEDIA_ROOT'] / name).write_bytes(b'image')
    client.post('/api/library/sync')
    collection_id = client.post('/api/collections', json={'name': '媒体集'}).get_json()['data']['item']['id']
    client.post(f'/api/collections/{collection_id}/items', json={'uris': names})
    assert client.get(f'/collection/{collection_id}').status_code == 200
    url = (
        f'/api/library/items?scope=collection&collection_id={collection_id}'
        if endpoint == 'library' else f'/api/collections/{collection_id}/items?'
    )
    collected = []
    for offset in (0, 12, 24):
        response = client.get(f'{url}&offset={offset}&limit=12')
        assert response.status_code == 200
        page = response.get_json()['data']
        assert page['total'] == 25
        assert page['next_offset'] == offset + 12
        assert page['has_more'] == (offset < 24)
        collected.extend(item['name'] for item in page['items'])
    assert collected == [f'@default/{name}' for name in reversed(names)]
