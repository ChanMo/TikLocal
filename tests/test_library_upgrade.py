import os
from urllib.parse import quote

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
    assert "waterfall-col" in body
    assert "scheduleWaterfallRelayout" in body
    assert "flow_ui_shared.js" in body
    assert "flow_state_controller.js" in body
    assert "flow_session.js" in body
    assert "flow_actions_shared.js" in body
    assert "flow_media_actions_controller.js" in body
    assert "createFlowStateController(" in body
    assert "createFlowSession(" in body
    assert "createFlowMediaActionsController(" in body
    assert "uiShared.updateMagnifierContent({" in body
    assert "collectionModalOpenedAt" in body
    assert "quickCollectionList.addEventListener('change'" in body


def test_home_feed_uses_unified_immersive_model(client):
    res = client.get("/")
    assert res.status_code == 200
    body = res.data.decode("utf-8")
    assert "body.immersive-mode .caption-panel:not(.is-hidden)" in body
    assert "flow_ui_shared.js" in body
    assert "flow_state_controller.js" in body
    assert "flow_session.js" in body
    assert "flow_actions_shared.js" in body
    assert "flow_media_actions_controller.js" in body
    assert "createFlowStateController(" in body
    assert "createFlowSession(" in body
    assert "createFlowMediaActionsController(" in body
    assert "flowState.toggleImmersive()" in body
    assert "flowState.setMagnifying(active)" in body
    assert "uiShared.updateMagnifierContent({" in body
    assert 'id="collection-btn"' in body
    assert 'id="collection-count"' in body
    assert 'id="collection-modal"' in body
    assert "toggleCollectionMembership(" in body
    assert "collectionList.addEventListener('change'" in body
    assert "image-focus-mode" not in body


def test_api_library_items_supports_modes_and_seed(client):
    all_res = client.get("/api/library/items?scope=all&mode=all&offset=0&limit=20")
    assert all_res.status_code == 200
    all_data = all_res.get_json()
    assert all_data["success"] is True
    all_items = all_data["data"]["items"]
    assert all("width" in item and "height" in item for item in all_items)
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


def test_removed_legacy_routes_and_apis_return_404(client):
    browse = client.get("/browse")
    assert browse.status_code == 404

    gallery = client.get("/gallery")
    assert gallery.status_code == 404

    api_videos = client.get("/api/videos")
    assert api_videos.status_code == 404

    api_random_images = client.get("/api/random-images?page=1&size=10")
    assert api_random_images.status_code == 404


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


def test_special_chars_in_media_urls_are_encoded(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    video_name = "v#1+.mp4"
    image_name = "a&b.jpg"
    (media_root / video_name).write_bytes(b"video")
    (media_root / image_name).write_bytes(b"image")

    data_root = tmp_path / "tiklocal-data"
    monkeypatch.setenv("MEDIA_ROOT", str(media_root))
    monkeypatch.setenv("TIKLOCAL_INSTANCE", str(data_root))
    app = create_app({"TESTING": True, "MEDIA_ROOT": media_root})
    local_client = app.test_client()

    video_detail = local_client.get(f"/detail/{quote(video_name, safe='')}")
    assert video_detail.status_code == 200
    video_body = video_detail.data.decode("utf-8")
    assert 'src="/media/v%231%2B.mp4"' in video_body
    assert 'poster="/thumb?uri=v%231%2B.mp4"' in video_body
    assert "const fileName = \"v#1+.mp4\";" in video_body

    image_detail = local_client.get(f"/image?uri={quote(image_name, safe='')}")
    assert image_detail.status_code == 200
    image_body = image_detail.data.decode("utf-8")
    assert 'src="/media?uri=a%26b.jpg"' in image_body
    assert "const imageUri = \"a\\u0026b.jpg\";" in image_body
    assert "const imageUriEncoded = \"a%26b.jpg\";" in image_body
    assert "window.location.href = '/delete?uri=a%26b.jpg';" in image_body

    media_res = local_client.get(f"/media?uri={quote(video_name, safe='')}", follow_redirects=False)
    assert media_res.status_code in {301, 302, 308}
    assert media_res.headers.get("Location", "").endswith("/media/v%231%2B.mp4")
