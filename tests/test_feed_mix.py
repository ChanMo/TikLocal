import json

import pytest

from tiklocal.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    (media_root / "v1.mp4").write_bytes(b"00")
    (media_root / "v2.mp4").write_bytes(b"00")
    (media_root / "nested").mkdir(parents=True, exist_ok=True)
    (media_root / "nested" / "v 3.mp4").write_bytes(b"00")

    (media_root / "i1.jpg").write_bytes(b"00")
    (media_root / "i2.png").write_bytes(b"00")

    data_root = tmp_path / "tiklocal-data"
    monkeypatch.setenv("MEDIA_ROOT", str(media_root))
    monkeypatch.setenv("TIKLOCAL_INSTANCE", str(data_root))

    app = create_app({"TESTING": True, "MEDIA_ROOT": media_root})
    return app.test_client()


def test_mix_feed_returns_typed_items(client):
    res = client.get("/api/feed/mix?page=1&size=12&seed=fixed-seed")
    assert res.status_code == 200
    data = res.get_json()

    assert isinstance(data, dict)
    assert "items" in data
    assert "seed" in data
    assert "has_more" in data

    items = data["items"]
    assert isinstance(items, list)
    assert len(items) > 0

    types = {item.get("type") for item in items}
    assert "video" in types
    assert "image" in types

    for item in items:
        assert "name" in item
        assert "media_url" in item
        assert "detail_url" in item
        assert item["type"] in {"video", "image"}
        if item["type"] == "video":
            assert item["detail_url"].startswith("/detail/")
        else:
            assert item["detail_url"].startswith("/image?uri=")


def test_mix_feed_falls_back_to_videos_when_no_images(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    (media_root / "only-video.mp4").write_bytes(b"00")
    (media_root / "only-video-2.mp4").write_bytes(b"00")

    data_root = tmp_path / "tiklocal-data"
    monkeypatch.setenv("MEDIA_ROOT", str(media_root))
    monkeypatch.setenv("TIKLOCAL_INSTANCE", str(data_root))

    app = create_app({"TESTING": True, "MEDIA_ROOT": media_root})
    test_client = app.test_client()

    res = test_client.get("/api/feed/mix?page=1&size=8&seed=fixed-seed")
    assert res.status_code == 200
    data = res.get_json()

    items = data["items"]
    assert len(items) > 0
    assert all(item["type"] == "video" for item in items)


def test_mix_feed_can_insert_theme_strip_for_recent_downloads_and_favorites(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    for name in ("v1.mp4", "v2.mp4", "i1.jpg", "i2.png", "i3.jpg"):
        (media_root / name).write_bytes(b"00")

    (media_root / "favorite.json").write_text(
        json.dumps(["i1.jpg", "i2.png", "v1.mp4"]),
        encoding="utf-8",
    )

    data_root = tmp_path / "tiklocal-data"
    data_root.mkdir(parents=True, exist_ok=True)
    (data_root / "download_jobs.json").write_text(
        json.dumps([
            {
                "id": "job-1",
                "status": "success",
                "created_at": "2026-03-14T10:00:00Z",
                "output_files_rel": ["i3.jpg", "v2.mp4", "i2.png"],
            }
        ]),
        encoding="utf-8",
    )

    monkeypatch.setenv("MEDIA_ROOT", str(media_root))
    monkeypatch.setenv("TIKLOCAL_INSTANCE", str(data_root))

    app = create_app({"TESTING": True, "MEDIA_ROOT": media_root})
    test_client = app.test_client()

    res = test_client.get("/api/feed/mix?page=1&size=24&seed=theme-seed")
    assert res.status_code == 200
    data = res.get_json()

    items = data["items"]
    strip = next((item for item in items if item.get("type") == "theme_strip"), None)
    assert strip is not None
    assert strip["name"] in {"theme:recent-downloads", "theme:favorite-picks"}
    assert strip["title"]
    assert strip["target_url"] in {"/favorite", "/library"}
    assert strip["target_label"]
    assert len(strip["items"]) >= 3
    for child in strip["items"]:
        assert child["type"] in {"video", "image"}
        assert child["name"]
        assert child["media_url"]
        assert child["thumb_url"]
        assert child["detail_url"]
        assert child["focus_url"]


def test_mix_feed_prefers_original_post_group_when_source_has_multiple_media(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    for name in ("set-1.jpg", "set-2.jpg", "solo.mp4", "fallback.jpg"):
        (media_root / name).write_bytes(b"00")

    data_root = tmp_path / "tiklocal-data"
    data_root.mkdir(parents=True, exist_ok=True)
    (data_root / "download_sources.json").write_text(
        json.dumps(
            {
                "version": 1,
                "updated_at": "2026-03-14T10:30:00Z",
                "items": {
                    "set-1.jpg": {
                        "source_url_raw": "https://x.com/demo/status/100",
                        "source_url_display": "https://x.com/demo/status/100",
                        "source_domain": "x.com",
                        "job_id": "job-group",
                        "created_at": "2026-03-14T10:00:00Z",
                    },
                    "set-2.jpg": {
                        "source_url_raw": "https://x.com/demo/status/100",
                        "source_url_display": "https://x.com/demo/status/100",
                        "source_domain": "x.com",
                        "job_id": "job-group",
                        "created_at": "2026-03-14T10:00:00Z",
                    },
                    "solo.mp4": {
                        "source_url_raw": "https://x.com/demo/status/101",
                        "source_url_display": "https://x.com/demo/status/101",
                        "source_domain": "x.com",
                        "job_id": "job-solo",
                        "created_at": "2026-03-14T09:00:00Z",
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("MEDIA_ROOT", str(media_root))
    monkeypatch.setenv("TIKLOCAL_INSTANCE", str(data_root))

    app = create_app({"TESTING": True, "MEDIA_ROOT": media_root})
    test_client = app.test_client()

    res = test_client.get("/api/feed/mix?page=1&size=24&seed=group-seed")
    assert res.status_code == 200
    data = res.get_json()

    group = next((item for item in data["items"] if item.get("type") == "image_group"), None)
    assert group is not None
    assert group["title"] == "原始图集"
    names = [child["name"] for child in group["items"]]
    assert "set-1.jpg" in names
    assert "set-2.jpg" in names
    assert all(child["media_url"] for child in group["items"])
