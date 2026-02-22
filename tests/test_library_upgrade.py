import os

import pytest

from tiklocal.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    for i in range(6):
        (media_root / f"v{i:02d}.mp4").write_bytes(b"00")
    for i in range(6):
        (media_root / f"i{i:02d}.jpg").write_bytes(b"00")

    # Create one large video for big_files mode.
    (media_root / "big.mp4").write_bytes(b"0" * (2 * 1024 * 1024))

    # Keep stable ordering for latest mode.
    for idx, p in enumerate(sorted(media_root.iterdir())):
        ts = 1_700_000_000 + idx
        os.utime(p, (ts, ts))

    data_root = tmp_path / "tiklocal-data"
    monkeypatch.setenv("MEDIA_ROOT", str(media_root))
    monkeypatch.setenv("TIKLOCAL_INSTANCE", str(data_root))

    app = create_app({"TESTING": True, "MEDIA_ROOT": media_root})
    return app.test_client()


def test_library_page_has_mode_tabs_and_no_masonry_label(client):
    res = client.get("/library")
    assert res.status_code == 200
    body = res.data.decode("utf-8")
    assert "data-mode=\"all\"" in body
    assert "data-mode=\"image_random\"" in body
    assert "data-mode=\"video_latest\"" in body
    assert "data-mode=\"big_files\"" in body
    assert "Masonry" not in body
    assert "id=\"quick-source\"" in body
    assert "id=\"quick-close-top\"" in body
    assert "id=\"quick-speed\"" in body
    assert "id=\"quick-caption\"" in body
    assert "id=\"quick-magnifier\"" in body
    assert "id=\"quick-play-status\"" in body
    assert "#quick-view.immersive .quick-caption-panel" in body
    assert "image-focus" not in body
    assert "flow_ui_shared.js" in body
    assert "flow_state_controller.js" in body
    assert "createFlowStateController(" in body
    assert "uiShared.updateMagnifierContent({" in body


def test_home_feed_uses_unified_immersive_model(client):
    res = client.get("/")
    assert res.status_code == 200
    body = res.data.decode("utf-8")
    assert "body.immersive-mode .caption-panel:not(.is-hidden)" in body
    assert "flow_ui_shared.js" in body
    assert "flow_state_controller.js" in body
    assert "createFlowStateController(" in body
    assert "flowState.toggleImmersive()" in body
    assert "flowState.setMagnifying(active)" in body
    assert "uiShared.updateMagnifierContent({" in body
    assert "image-focus-mode" not in body


def test_api_library_items_supports_modes_and_seed(client):
    all_res = client.get("/api/library/items?scope=all&mode=all&offset=0&limit=20")
    assert all_res.status_code == 200
    all_data = all_res.get_json()
    assert all_data["success"] is True
    all_items = all_data["data"]["items"]
    assert any(item["type"] == "video" for item in all_items)
    assert any(item["type"] == "image" for item in all_items)

    video_res = client.get("/api/library/items?scope=all&mode=video_latest&offset=0&limit=20")
    video_items = video_res.get_json()["data"]["items"]
    assert len(video_items) > 0
    assert all(item["type"] == "video" for item in video_items)

    image_res = client.get("/api/library/items?scope=all&mode=image_random&offset=0&limit=20&seed=fixed")
    image_items = image_res.get_json()["data"]["items"]
    assert len(image_items) > 0
    assert all(item["type"] == "image" for item in image_items)
    assert image_res.get_json()["data"]["seed"] == "fixed"

    big_res = client.get("/api/library/items?scope=all&mode=big_files&offset=0&limit=20&min_mb=1")
    big_items = big_res.get_json()["data"]["items"]
    assert len(big_items) >= 1
    assert all(item["type"] == "video" for item in big_items)
    assert any(item["name"] == "big.mp4" for item in big_items)


def test_api_library_items_no_duplicates_across_offsets(client):
    seen = set()
    offset = 0
    for _ in range(8):
        res = client.get(f"/api/library/items?scope=all&mode=all&offset={offset}&limit=4")
        assert res.status_code == 200
        data = res.get_json()["data"]
        names = [item["name"] for item in data["items"]]
        for name in names:
            assert name not in seen
            seen.add(name)
        if not data["has_more"]:
            break
        offset = int(data["next_offset"])


def test_api_library_items_dedupes_symlink_aliases(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    (media_root / "origin.mp4").write_bytes(b"abc")
    (media_root / "img.jpg").write_bytes(b"abc")

    alias = media_root / "alias.mp4"
    try:
        alias.symlink_to(media_root / "origin.mp4")
    except (OSError, NotImplementedError):
        pytest.skip("Symlink not supported in this environment")

    data_root = tmp_path / "tiklocal-data"
    monkeypatch.setenv("MEDIA_ROOT", str(media_root))
    monkeypatch.setenv("TIKLOCAL_INSTANCE", str(data_root))
    app = create_app({"TESTING": True, "MEDIA_ROOT": media_root})
    local_client = app.test_client()

    res = local_client.get("/api/library/items?scope=all&mode=all&offset=0&limit=50")
    assert res.status_code == 200
    items = res.get_json()["data"]["items"]
    video_items = [item for item in items if item["type"] == "video"]
    assert len(video_items) == 1
    assert video_items[0]["name"] in {"origin.mp4", "alias.mp4"}


def test_legacy_browse_and_gallery_redirects(client):
    browse = client.get("/browse", follow_redirects=False)
    assert browse.status_code in {301, 302, 308}
    assert browse.headers.get("Location", "").startswith("/library?mode=video_latest")

    browse_big = client.get("/browse?filter=big&min_mb=3", follow_redirects=False)
    assert browse_big.status_code in {301, 302, 308}
    assert "mode=big_files" in browse_big.headers.get("Location", "")
    assert "min_mb=3" in browse_big.headers.get("Location", "")

    gallery = client.get("/gallery", follow_redirects=False)
    assert gallery.status_code in {301, 302, 308}
    assert gallery.headers.get("Location", "").startswith("/library?mode=image_random")


def test_favorite_scope_and_detail_links(client):
    client.post("/api/favorite/v01.mp4")
    client.post("/api/favorite/i01.jpg")

    res = client.get("/api/library/items?scope=favorite&mode=all&offset=0&limit=20")
    assert res.status_code == 200
    data = res.get_json()["data"]
    names = {item["name"] for item in data["items"]}
    assert "v01.mp4" in names
    assert "i01.jpg" in names
    assert any(item["detail_url"] == "/detail/v01.mp4" for item in data["items"])
    assert any(item["detail_url"] == "/image?uri=i01.jpg" for item in data["items"])
