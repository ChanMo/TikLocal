import json
import os
import sqlite3

import pytest

from tiklocal.app import create_app
from tiklocal.services.radio import RadioProfileStore


@pytest.fixture
def client(tmp_path, monkeypatch):
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

    monkeypatch.setenv("MEDIA_ROOT", str(media_root))
    monkeypatch.setenv("TIKLOCAL_INSTANCE", str(data_root))
    app = create_app({"TESTING": True, "MEDIA_ROOT": media_root})
    return app.test_client()


def test_radio_stations_are_low_decision_modes(client):
    res = client.get("/api/radio/stations")
    assert res.status_code == 200
    stations = res.get_json()["data"]["stations"]
    ids = [station["id"] for station in stations]

    assert ids == ["default", "recent", "favorites"]
    assert all(station["name"] for station in stations)
    assert all(station["description"] for station in stations)


def test_radio_page_exposes_polished_player_states(client):
    res = client.get("/radio")
    body = res.get_data(as_text=True)

    assert res.status_code == 200
    assert 'radio.css' in body
    assert 'class="radio-atmosphere"' in body
    assert 'id="radio-atmosphere-video"' in body
    assert 'radio/rain-window.mp4' in body
    assert 'src="/static/radio/rain-window.mp4' in body
    assert 'preload="metadata"' in body
    assert 'muted' in body
    assert 'playsinline' in body
    assert 'class="radio-layout"' in body
    assert 'class="play-state"' in body
    assert 'id="station-name"' in body
    assert 'id="btn-encore"' in body
    assert 'id="encore-count"' in body
    assert 'id="btn-room"' in body
    assert 'id="room-menu"' in body
    assert 'data-room="rain"' in body
    assert 'data-room="off"' in body
    assert 'aria-pressed="false"' in body

    css = client.get("/static/radio.css")
    assert css.status_code == 200
    assert b"overflow-wrap: anywhere" in css.data
    assert b".radio-atmosphere-video" in css.data

    video = client.get("/static/radio/rain-window.mp4")
    assert video.status_code == 200
    assert video.content_type == "video/mp4"

    controller = client.get("/static/radio_controller.js")
    assert controller.status_code == 200
    assert b"prefers-reduced-motion: reduce" in controller.data
    assert b"navigator.connection.saveData" in controller.data
    assert b"radio_room" in controller.data


def test_radio_tune_returns_playable_tracks(client):
    res = client.get("/api/radio/tune?station=default&limit=4&seed=fixed")
    assert res.status_code == 200
    data = res.get_json()["data"]
    items = data["items"]

    assert data["station"]["id"] == "default"
    assert data["total"] == 6
    assert len(items) == 4
    for item in items:
        assert item["name"].startswith("@default/")
        assert item["media_url"].startswith("/media/")
        assert item["thumb_url"].startswith("/thumb?uri=")
        assert item["artwork_url"].startswith("/api/radio/artwork?uri=")
        assert item["title"]
        assert "artist" in item
        assert "album" in item
        assert "duration" in item
        assert "is_favorite" in item


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
    class FakeCompleted:
        returncode = 0
        stdout = json.dumps({
            "format": {
                "duration": "123.45",
                "tags": {
                    "title": "真实标题",
                    "artist": "真实艺人",
                    "album": "真实专辑",
                },
            },
        })

    def fake_run(*args, **kwargs):
        return FakeCompleted()

    monkeypatch.setattr("tiklocal.services.radio.sp.run", fake_run)

    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    (media_root / "song.mp3").write_bytes(b"audio")
    data_root = tmp_path / "tiklocal-data"
    data_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("MEDIA_ROOT", str(media_root))
    monkeypatch.setenv("TIKLOCAL_INSTANCE", str(data_root))
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


def test_radio_feedback_records_local_profile(client, tmp_path, monkeypatch):
    res = client.post(
        "/api/radio/feedback",
        json={"name": "@default/a01.mp3", "event": "complete", "ratio": 0.96},
    )

    assert res.status_code == 200
    profile_path = tmp_path / "tiklocal-data" / "radio_profile.json"
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    entry = payload["tracks"]["@default/a01.mp3"]
    assert entry["completes"] == 1
    assert entry["last_event"] == "complete"
    assert entry["score"] > 0


def test_radio_replay_feedback_updates_both_profiles(client, tmp_path):
    res = client.post(
        "/api/radio/feedback",
        json={"name": "@default/a01.mp3", "event": "replay", "ratio": 1},
    )

    assert res.status_code == 200
    profile_path = tmp_path / "tiklocal-data" / "radio_profile.json"
    entry = json.loads(profile_path.read_text(encoding="utf-8"))["tracks"]["@default/a01.mp3"]
    assert entry["replays"] == 1
    assert entry["last_event"] == "replay"
    assert entry["score"] > 0

    database_path = tmp_path / "tiklocal-data" / "tiklocal.sqlite3"
    with sqlite3.connect(database_path) as conn:
        event = conn.execute(
            "SELECT event_type FROM media_events WHERE uri = ? ORDER BY id DESC LIMIT 1",
            ("@default/a01.mp3",),
        ).fetchone()
        affinity = conn.execute(
            "SELECT replays FROM media_affinity WHERE uri = ?",
            ("@default/a01.mp3",),
        ).fetchone()
    assert event == ("replay",)
    assert affinity == (1,)


def test_radio_profile_scores_completion_above_skip(tmp_path):
    store = RadioProfileStore(tmp_path / "radio_profile.json")

    complete = store.record("@default/a01.mp3", "complete", ratio=0.98)
    skip = store.record("@default/a02.mp3", "skip", ratio=0.05)

    assert complete["score"] > 0
    assert skip["score"] < 0
    assert complete["score"] > skip["score"]


def test_radio_profile_counts_replays_as_strong_interest(tmp_path):
    store = RadioProfileStore(tmp_path / "radio_profile.json")

    complete = store.record("@default/a01.mp3", "complete", ratio=0)
    replay = store.record("@default/a01.mp3", "replay", ratio=1)
    favorite = store.record("@default/a02.mp3", "favorite", ratio=1)

    assert replay["replays"] == 1
    assert replay["last_event"] == "replay"
    assert replay["score"] - complete["score"] == pytest.approx(0.18)
    assert favorite["score"] > replay["score"] - complete["score"]
