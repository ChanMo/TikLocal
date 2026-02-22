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
