import pytest

from tiklocal.app import create_app


@pytest.fixture
def client(tmp_path):
    media_root = tmp_path / 'media'
    media_root.mkdir()
    (media_root / 'movie.mp4').write_bytes(b'video')
    return create_app({'TESTING': True, 'MEDIA_ROOT': media_root}).test_client()


def save(client, position, duration=600, uri='movie.mp4'):
    return client.post('/api/playback', json={'uri': uri, 'position': position, 'duration': duration})


def library_item(client):
    return client.get('/api/library/items').get_json()['data']['items'][0]


def test_position_is_kept_only_where_resuming_makes_sense(client):
    assert save(client, 120).get_json() == {'saved': True}
    item = library_item(client)
    assert (item['resume'], item['progress']) == (120, 0.2)
    assert b'TikLocalResume.track(mainVideo, fileName, 120.0)' in client.get('/detail/movie.mp4').data

    # Near the end counts as finished, and clears the resume point.
    assert save(client, 590).get_json() == {'saved': False}
    assert 'resume' not in library_item(client)
    assert b'TikLocalResume.track(mainVideo, fileName, 0)' in client.get('/detail/movie.mp4').data

    assert save(client, 5).get_json() == {'saved': False}
    assert save(client, 30, duration=45).get_json() == {'saved': False}


def test_rejects_bad_input_and_reset_clears_positions(client):
    assert save(client, 'soon').status_code == 400
    assert save(client, float('inf')).status_code == 400
    assert save(client, 120, uri='../outside.mp4').status_code == 404

    save(client, 120)
    client.delete('/api/activity')
    assert 'resume' not in library_item(client)
