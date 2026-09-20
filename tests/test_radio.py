import json
import os
import sqlite3
import subprocess

import pytest

from tiklocal.app import create_app
from tiklocal.services.radio import RadioProfileStore


@pytest.fixture
def client(tmp_path):
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    (media_root / "sleep").mkdir()
    (media_root / "talk").mkdir()

    names = [
        "a01.mp3",
        "a02.mp3",
        "a03.mp3",
        "sleep/s01.mp3",
        "sleep/s02.mp3",
        "talk/t01.m4a",
    ]
    for idx, name in enumerate(names):
        path = media_root / name
        path.write_bytes(b"audio")
        ts = 1_700_000_000 + idx
        os.utime(path, (ts, ts))

    data_root = tmp_path / "tiklocal-data"
    data_root.mkdir(parents=True, exist_ok=True)
    (data_root / "favorites.json").write_text(
        json.dumps(["@default/sleep/s01.mp3", "@default/talk/t01.m4a"]),
        encoding="utf-8",
    )

    app = create_app({"TESTING": True, "MEDIA_ROOT": media_root})
    return app.test_client()


def test_radio_stations_are_low_decision_modes(client):
    res = client.get("/api/radio/stations")
    assert res.status_code == 200
    stations = res.get_json()["data"]["stations"]
    ids = [station["id"] for station in stations]

    assert ids == ["default", "recent", "favorites"]


@pytest.mark.parametrize('endpoint', ['tune', 'items'])
def test_radio_returns_only_available_indexed_audio(client, tmp_path, endpoint):
    root = tmp_path / 'media'
    # A new file becomes available after sync; a vanished file is never offered.
    (root / 'new.mp3').write_bytes(b'audio')
    (root / 'a01.mp3').unlink()
    before = client.get(f'/api/radio/{endpoint}?limit=20').get_json()['data']
    assert before['total'] == 5
    assert '@default/new.mp3' not in {item['name'] for item in before['items']}
    assert '@default/a01.mp3' not in {item['name'] for item in before['items']}
    (root / 'picture.jpg').write_bytes(b'image')
    client.post('/api/library/sync')
    after = client.get(f'/api/radio/{endpoint}?limit=20').get_json()['data']
    assert after['total'] == 6
    assert '@default/new.mp3' in {item['name'] for item in after['items']}
    assert all(item['name'].endswith(('.mp3', '.m4a')) for item in after['items'])


def test_radio_tune_returns_playable_tracks(client):
    response = client.get('/api/radio/tune?station=default&limit=4&seed=fixed')
    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['station']['id'] == 'default' and data['total'] == 6
    assert len(data['items']) == 4
    for item in data['items']:
        assert client.get(item['media_url']).data == b'audio'
        assert item['artwork_url'].startswith('/api/radio/artwork?uri=')
        assert item['title']
        assert {'artist', 'album', 'duration', 'is_favorite', 'thumb_url'} <= item.keys()


def test_radio_tune_excludes_recently_played(client):
    excluded = "@default/a01.mp3,@default/sleep/s01.mp3"
    res = client.get(f"/api/radio/tune?station=default&limit=6&seed=fixed&exclude={excluded}")
    assert res.status_code == 200
    names = {item["name"] for item in res.get_json()["data"]["items"]}

    assert "@default/a01.mp3" not in names
    assert "@default/sleep/s01.mp3" not in names


def test_radio_favorites_station_prioritizes_favorites(client):
    res = client.get("/api/radio/tune?station=favorites&limit=2&seed=fixed")
    assert res.status_code == 200
    items = res.get_json()["data"]["items"]

    assert len(items) == 2
    assert any(item["is_favorite"] for item in items)


def test_radio_artwork_falls_back_to_generated_image(client):
    res = client.get("/api/radio/artwork?uri=@default/a01.mp3")

    assert res.status_code == 200
    assert res.mimetype == "image/png"
    assert len(res.data) > 1000
    assert res.data.startswith(b"\x89PNG")


def test_radio_uses_embedded_audio_metadata(tmp_path, monkeypatch):
    output = json.dumps({'format': {
        'duration': '123.45',
        'tags': {'title': '真实标题', 'artist': '真实艺人', 'album': '真实专辑'},
    }})
    monkeypatch.setattr('tiklocal.services.radio.sp.run', lambda *args, **kwargs:
                        subprocess.CompletedProcess(args, 0, stdout=output))

    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    (media_root / "song.mp3").write_bytes(b"audio")
    data_root = tmp_path / "tiklocal-data"
    data_root.mkdir(parents=True, exist_ok=True)

    app = create_app({"TESTING": True, "MEDIA_ROOT": media_root})
    res = app.test_client().get("/api/radio/metadata?uri=@default/song.mp3")

    assert res.status_code == 200
    item = res.get_json()["data"]
    assert item["title"] == "真实标题"
    assert item["artist"] == "真实艺人"
    assert item["album"] == "真实专辑"
    assert item["duration"] == 123.45


def test_radio_tune_does_not_probe_audio_metadata(client, monkeypatch):
    def fail_probe(*args, **kwargs):
        raise AssertionError("tune should not call ffprobe")

    monkeypatch.setattr("tiklocal.services.radio.sp.run", fail_probe)
    res = client.get("/api/radio/tune?station=default&limit=3&seed=fixed")

    assert res.status_code == 200
    items = res.get_json()["data"]["items"]
    assert len(items) == 3
    assert all(item["duration"] is None for item in items)


@pytest.mark.parametrize('event,counter', [('complete', 'completes'), ('replay', 'replays')])
def test_radio_feedback_updates_both_profiles(client, tmp_path, event, counter):
    response = client.post('/api/radio/feedback', json={
        'name': '@default/a01.mp3', 'event': event, 'ratio': 1,
    })
    assert response.status_code == 200
    data_root = tmp_path / 'tiklocal-data'
    entry = json.loads((data_root / 'radio_profile.json').read_text())['tracks']['@default/a01.mp3']
    assert entry[counter] == 1 and entry['last_event'] == event and entry['score'] > 0
    with sqlite3.connect(data_root / 'tiklocal.sqlite3') as connection:
        recorded = connection.execute(
            'SELECT event_type FROM media_events WHERE uri = ? ORDER BY id DESC LIMIT 1',
            ('@default/a01.mp3',),
        ).fetchone()
        affinity = connection.execute(
            f'SELECT {counter} FROM media_affinity WHERE uri = ?', ('@default/a01.mp3',),
        ).fetchone()
    assert recorded == (event,) and affinity == (1,)


def test_radio_profile_scores_completion_above_skip(tmp_path):
    store = RadioProfileStore(tmp_path / "radio_profile.json")

    complete = store.record("@default/a01.mp3", "complete", ratio=0.98)
    skip = store.record("@default/a02.mp3", "skip", ratio=0.05)

    assert complete["score"] > 0
    assert skip["score"] < 0
    assert complete["score"] > skip["score"]
