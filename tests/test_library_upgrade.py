import os
from io import BytesIO
from urllib.parse import quote

import pytest
from PIL import Image

from tiklocal.app import create_app
from tiklocal.services import LibraryService
from tiklocal.services.database import AppDatabase
from tiklocal.services.library_index import MediaIndexStore


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
    assert "id=\"library-search-input\"" in body
    assert 'id="library-toolbar"' in body
    assert 'id="library-search-toggle"' in body
    assert 'id="library-search-clear"' in body
    assert 'role="search"' in body
    assert 'aria-label="媒体库浏览模式"' in body
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
    assert "library_page_controller.js" in body
    assert "flow_ui_shared.js" in body
    assert "flow_state_controller.js" in body
    assert "flow_session.js" in body
    assert "flow_actions_shared.js" in body
    assert "flow_media_actions_controller.js" in body
    assert "pageSize: 24" in body
    assert 'id="library-status-text"' in body
    assert 'id="library-retry"' in body
    assert 'id="library-clear-search"' in body

    controller = client.get("/static/library_page_controller.js").data.decode("utf-8")
    assert "syncSearchUI" in controller
    assert "aria-pressed" in controller
    assert "waterfall.gridWidth !== nextGridWidth" in controller
    assert "if (isSimilarMode() || !layoutChanged) return;" in controller


def test_flow_uses_unified_immersive_model(client):
    res = client.get("/flow")
    assert res.status_code == 200
    body = res.data.decode("utf-8")
    assert "body.immersive-mode .caption-panel:not(.is-hidden)" in body
    assert "flow_ui_shared.js" in body
    assert "flow_state_controller.js" in body
    assert "flow_session.js" in body
    assert "flow_actions_shared.js" in body
    assert "flow_media_actions_controller.js" in body
    assert "home_feed_controller.js" in body
    assert 'id="collection-btn"' in body
    assert 'id="collection-count"' in body
    assert 'id="collection-modal"' in body
    assert 'id="app-nav-menu-trigger"' in body
    assert 'id="app-nav-menu"' in body
    assert 'href="/static/app_navigation.css"' in body
    assert 'class="mobile-mode-link is-active"' in body
    assert '>Flow</a>' in body
    assert '>Radio</a>' in body
    assert 'class="rail-brand"' in body
    assert 'id="more-theme-toggle"' not in body
    assert '<span>设置</span>' in body
    assert 'id="flow-state"' in body
    assert 'id="flow-state-retry"' in body
    assert 'id="flow-state-next"' in body
    assert 'id="video-start-cover"' in body
    assert 'id="video-start-cover-image"' not in body
    assert ".video-start-cover.is-visible" in body
    assert "transition: none" in body
    assert "transform: scale(1.01)" not in body
    assert "filter: blur(2px)" not in body
    assert 'href="/favorite"' in body
    assert '<span>已保存</span>' in body
    assert 'href="/collections"' not in body


def test_home_is_a_media_launchpad(client):
    res = client.get("/")
    assert res.status_code == 200
    body = res.data.decode("utf-8")
    assert 'data-nav-context="home"' in body
    assert 'href="/static/home.css"' in body
    assert 'home_page_controller.js' in body
    assert 'id="home-title"' in body
    assert 'href="/flow"' in body
    assert 'href="/radio"' in body
    assert 'id="home-recent"' in body
    assert 'id="home-rediscover"' in body
    assert 'id="home-collections"' in body
    assert "home_feed_controller.js" not in body


def test_settings_focuses_on_useful_local_controls(client):
    res = client.get('/settings/')
    assert res.status_code == 200
    body = res.data.decode('utf-8')
    assert '<h1 class="settings-title">设置</h1>' in body
    assert 'data-theme-preference="system"' in body
    assert 'data-theme-preference="light"' in body
    assert 'data-theme-preference="dark"' in body
    assert 'id="refresh-library"' in body
    assert 'id="clear-cache"' in body
    assert 'id="reset-recommendations"' in body
    assert 'LLM Provider' not in body
    assert 'AI Prompt' not in body
    assert 'href="/download"' in body
    assert 'href="/settings"' in body
    assert 'id="quick-theme-toggle"' not in body
    assert "image-focus-mode" not in body

    controller = client.get("/static/home_feed_controller.js").data.decode("utf-8")
    assert "size: '24'" in controller
    assert "snapshot: '1'" not in controller
    assert "randomStartRatio" not in controller
    assert "_randomStart" not in controller
    assert "function prepareVideoStart(videoEl)" in controller
    assert "function isVideoStartReady(videoEl)" in controller
    assert "waitForPresentedVideoFrame" in controller
    assert "prepareVideoStart(v).catch" in controller
    assert "const needsVideoStartCover = item.type === 'video' && !isVideoStartReady(item.el)" in controller
    assert "updateControls(item);\n      preloadNextVideo();" in controller
    assert "videoStartCoverImage" not in controller
    assert "video.poster = item.thumb_url" not in controller
    assert "_activityPlayedSeconds" in controller


def test_api_library_items_supports_modes_search_and_sync(client, tmp_path):
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
    assert any(item["name"] == "@default/big.mp4" for item in big_items)

    new_image = tmp_path / "media" / "search-target.jpg"
    new_image.write_bytes(b"image")
    before_sync = client.get("/api/library/items?scope=all&q=search-target&offset=0&limit=20")
    assert before_sync.get_json()["data"]["items"] == []

    sync_res = client.post("/api/library/sync")
    assert sync_res.status_code == 200
    assert sync_res.get_json()["data"]["indexed"] == 14
    search_res = client.get("/api/library/items?scope=all&q=search-target&offset=0&limit=20")
    assert [item["name"] for item in search_res.get_json()["data"]["items"]] == [
        "@default/search-target.jpg"
    ]


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
    assert video_items[0]["name"] in {"@default/origin.mp4", "@default/alias.mp4"}


def test_api_library_items_merges_multiple_media_sources(tmp_path, monkeypatch):
    default_root = tmp_path / "default"
    extra_root = tmp_path / "extra"
    default_root.mkdir(parents=True, exist_ok=True)
    extra_root.mkdir(parents=True, exist_ok=True)
    (default_root / "main.mp4").write_bytes(b"video")
    (extra_root / "photo.jpg").write_bytes(b"image")

    data_root = tmp_path / "tiklocal-data"
    monkeypatch.setenv("MEDIA_ROOT", str(default_root))
    monkeypatch.setenv("TIKLOCAL_INSTANCE", str(data_root))
    app = create_app({
        "TESTING": True,
        "MEDIA_ROOT": default_root,
        "MEDIA_SOURCES": [
            {"id": "default", "name": "Default", "path": str(default_root)},
            {"id": "photos", "name": "Photos", "path": str(extra_root)},
        ],
    })
    local_client = app.test_client()

    res = local_client.get("/api/library/items?scope=all&mode=all&offset=0&limit=20")
    assert res.status_code == 200
    names = {item["name"] for item in res.get_json()["data"]["items"]}
    assert "@default/main.mp4" in names
    assert "@photos/photo.jpg" in names

    legacy_media = local_client.get("/media?uri=main.mp4", follow_redirects=False)
    assert legacy_media.status_code in {301, 302, 308}
    assert legacy_media.headers.get("Location", "").endswith("/media/%40default/main.mp4")

    extra_media = local_client.get("/media?uri=%40photos/photo.jpg", follow_redirects=True)
    assert extra_media.status_code == 200
    assert extra_media.data == b"image"


def test_startup_resyncs_existing_media_index(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    media_root.mkdir()
    kept = media_root / "kept.mp4"
    removed = media_root / "removed.jpg"
    kept.write_bytes(b"old")
    removed.write_bytes(b"removed")

    database = AppDatabase(tmp_path / "tiklocal.sqlite3")
    config = {"TESTING": True, "MEDIA_ROOT": media_root, "APP_DATABASE": database}
    create_app(config)

    kept.write_bytes(b"new-content")
    removed.unlink()
    (media_root / "added.jpg").write_bytes(b"added")
    app = create_app(config)

    records = {item["name"]: item for item in MediaIndexStore(database).records()}
    assert set(records) == {"@default/kept.mp4", "@default/added.jpg"}
    assert records["@default/kept.mp4"]["size_bytes"] == len(b"new-content")
    assert app.extensions["media_index_sync"]["deleted"] == 1


def test_startup_preserves_index_for_unavailable_media_source(tmp_path):
    default_root = tmp_path / "default"
    extra_root = tmp_path / "extra"
    default_root.mkdir()
    extra_root.mkdir()
    main = default_root / "main.mp4"
    main.write_bytes(b"video")
    (extra_root / "photo.jpg").write_bytes(b"image")

    database = AppDatabase(tmp_path / "tiklocal.sqlite3")
    config = {
        "TESTING": True,
        "MEDIA_ROOT": default_root,
        "APP_DATABASE": database,
        "MEDIA_SOURCES": [
            {"id": "default", "name": "Default", "path": str(default_root)},
            {"id": "photos", "name": "Photos", "path": str(extra_root)},
        ],
    }
    create_app(config)

    main.unlink()
    extra_root.rename(tmp_path / "extra-offline")
    app = create_app(config)

    names = {item["name"] for item in MediaIndexStore(database).records()}
    assert names == {"@photos/photo.jpg"}
    assert app.extensions["media_index_sync"]["unavailable_sources"] == ["photos"]


def test_library_images_use_bounded_cached_thumbnails(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    media_root.mkdir()
    image_path = media_root / "large image.png"
    Image.new("RGB", (1400, 900), (90, 130, 170)).save(image_path)

    data_root = tmp_path / "tiklocal-data"
    monkeypatch.setenv("MEDIA_ROOT", str(media_root))
    monkeypatch.setenv("TIKLOCAL_INSTANCE", str(data_root))
    app = create_app({"TESTING": True, "MEDIA_ROOT": media_root})
    local_client = app.test_client()

    payload = local_client.get("/api/library/items?scope=all").get_json()["data"]
    item = payload["items"][0]
    assert item["media_url"] == "/media/%40default/large%20image.png"
    assert item["thumb_url"] == "/thumb?uri=%40default/large%20image.png"

    first = local_client.get(item["thumb_url"])
    second = local_client.get(item["thumb_url"])
    assert first.status_code == 200
    assert first.mimetype == "image/jpeg"
    assert second.data == first.data
    with Image.open(BytesIO(first.data)) as thumbnail:
        assert max(thumbnail.size) == 640

    thumb_path = next((data_root / "thumbnails").glob("*.jpg"))
    Image.new("RGB", (900, 1400), (180, 80, 60)).save(image_path)
    newer = thumb_path.stat().st_mtime + 2
    os.utime(image_path, (newer, newer))
    refreshed = local_client.get(item["thumb_url"])
    assert refreshed.data != first.data
    with Image.open(BytesIO(refreshed.data)) as thumbnail:
        assert thumbnail.size == (411, 640)

    delete_res = local_client.post("/delete/%40default/large%20image.png")
    assert delete_res.status_code in {301, 302, 308}
    assert not thumb_path.exists()


def test_video_detail_navigation_uses_media_index(client, monkeypatch):
    def fail_scan(*args, **kwargs):
        raise AssertionError("video detail should not scan the filesystem")

    monkeypatch.setattr(LibraryService, "scan_videos", fail_scan)
    res = client.get("/detail/%40default/v03.mp4")
    assert res.status_code == 200


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
    assert "@default/v01.mp4" in names
    assert "@default/i01.jpg" in names
    assert any(item["detail_url"] == "/detail/%40default/v01.mp4" for item in data["items"])
    assert any(item["detail_url"] == "/image?uri=%40default/i01.jpg" for item in data["items"])


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
    assert 'src="/media/%40default/v%231%2B.mp4"' in video_body
    assert 'poster="/thumb?uri=%40default%2Fv%231%2B.mp4"' in video_body
    assert "const fileName = \"@default/v#1+.mp4\";" in video_body
    assert "fetch('/delete/%40default/v%231%2B.mp4', { method: 'POST' })" in video_body

    image_detail = local_client.get(f"/image?uri={quote(image_name, safe='')}")
    assert image_detail.status_code == 200
    image_body = image_detail.data.decode("utf-8")
    assert 'src="/media?uri=%40default%2Fa%26b.jpg"' in image_body
    assert "const imageUri = \"@default/a\\u0026b.jpg\";" in image_body
    assert "const imageUriEncoded = \"%40default%2Fa%26b.jpg\";" in image_body
    assert "image_viewer_controller.js" in image_body
    assert 'id="zoom-in-btn"' in image_body
    assert 'id="zoom-out-btn"' in image_body
    assert 'id="fullscreen-stage"' in image_body
    assert "fetch('/delete/%40default/a%26b.jpg', { method: 'POST' })" in image_body
    assert "window.location.href = '/library';" in image_body

    media_res = local_client.get(f"/media?uri={quote(video_name, safe='')}", follow_redirects=False)
    assert media_res.status_code in {301, 302, 308}
    assert media_res.headers.get("Location", "").endswith("/media/%40default/v%231%2B.mp4")
