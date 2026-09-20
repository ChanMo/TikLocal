import os
from io import BytesIO
from urllib.parse import quote

import pytest
from PIL import Image

import tiklocal.services.library_index as library_index_module
from tiklocal.app import create_app
from tiklocal.services.library import LibraryService
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

    monkeypatch.setenv("MEDIA_ROOT", str(media_root))

    app = create_app({"TESTING": True, "MEDIA_ROOT": media_root})
    return app.test_client()


@pytest.mark.parametrize('url', ['/', '/flow', '/library', '/library?view=explore', '/radio', '/download', '/settings/', '/favorite', '/collections'])
def test_web_pages_are_available(client, url):
    assert client.get(url).status_code == 200


def test_library_timeline_groups_months_and_month_detail_filters(client):
    timeline = client.get("/api/library/timeline?limit=12&preview_limit=9")
    assert timeline.status_code == 200
    data = timeline.get_json()["data"]
    assert data["months"]
    assert data["years"]
    month = data["months"][0]
    assert month["key"] == "2023-11"
    assert month["count"] == 13
    assert len(month["covers"]) == 9
    assert all(item["thumb_url"].startswith("/thumb?uri=") for item in month["covers"])

    month_page = client.get("/library?view=month&month=2023-11")
    assert month_page.status_code == 200
    items = client.get("/api/library/items?scope=all&month=2023-11&limit=20").get_json()["data"]
    assert items["total"] == 13


def test_timeline_prefers_embedded_and_filename_capture_dates(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    media_root.mkdir()
    photo = media_root / "old-memory.jpg"
    image = Image.new("RGB", (80, 60), (120, 80, 60))
    exif = Image.Exif()
    exif[36867] = "2019:04:08 10:20:30"
    image.save(photo, exif=exif)
    video = media_root / "VID_20210703_142233.mp4"
    video.write_bytes(b"video")
    recent_ts = 1_750_000_000
    os.utime(photo, (recent_ts, recent_ts))
    os.utime(video, (recent_ts, recent_ts))

    database = AppDatabase(tmp_path / "timeline.sqlite3")
    app = create_app({"TESTING": True, "MEDIA_ROOT": media_root, "APP_DATABASE": database})
    local_client = app.test_client()

    timeline = local_client.get("/api/library/timeline").get_json()["data"]
    keys = [month["key"] for month in timeline["months"]]
    assert keys == ["2021-07", "2019-04"]

    records = {item["name"]: item for item in MediaIndexStore(database).records()}
    assert records["@default/old-memory.jpg"]["time_source"] == "exif_original"
    assert records["@default/old-memory.jpg"]["time_confidence"] == "high"
    assert records["@default/VID_20210703_142233.mp4"]["time_source"] == "filename"

    # Simulate a pre-timeline index row. It must be enriched once, then reused.
    with database.connect() as conn:
        conn.execute(
            """
            UPDATE media_items
            SET captured_at = mtime,
                captured_local_date = '2025-06-15T15:06:40',
                capture_year = '2025',
                capture_month = '2025-06',
                time_source = 'filesystem_mtime',
                time_confidence = 'fallback',
                time_metadata_version = 0
            WHERE uri = '@default/old-memory.jpg'
            """
        )
    create_app({"TESTING": True, "MEDIA_ROOT": media_root, "APP_DATABASE": database})
    enriched = {item["name"]: item for item in MediaIndexStore(database).records()}
    assert enriched["@default/old-memory.jpg"]["time_source"] == "exif_original"

    def fail_reopen(_path):
        raise AssertionError("unchanged media metadata should be reused")

    monkeypatch.setattr(library_index_module, "_image_capture_time", fail_reopen)
    create_app({"TESTING": True, "MEDIA_ROOT": media_root, "APP_DATABASE": database})


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
    assert client.get(image_res.request.url).get_json()["data"]["items"] == image_items

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


def test_big_files_sort_by_size_across_pages(client, tmp_path):
    for size in range(3, 17):
        path = tmp_path / 'media' / f'large-{size:02}.mp4'
        with path.open('wb') as stream:
            stream.truncate(size * 1024 * 1024)
        os.utime(path, (1_700_000_000 - size, 1_700_000_000 - size))
    client.post('/api/library/sync')
    url = '/api/library/items?mode=big_files&min_mb=3&limit=12'
    first = client.get(url).get_json()['data']
    second = client.get(f"{url}&offset={first['next_offset']}").get_json()['data']
    assert first['total'] == 14 and first['has_more']
    assert not second['has_more']
    assert [item['name'] for item in first['items'] + second['items']] == [
        f'@default/large-{size:02}.mp4' for size in range(16, 2, -1)
    ]


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

    monkeypatch.setenv("MEDIA_ROOT", str(media_root))
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

    monkeypatch.setenv("MEDIA_ROOT", str(default_root))
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


@pytest.mark.parametrize('failure', ['offline', 'directory_read', 'file_stat'])
def test_startup_preserves_index_for_unavailable_media_source(tmp_path, monkeypatch, failure):
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
    if failure == 'offline':
        extra_root.rename(tmp_path / "extra-offline")
    elif failure == 'directory_read':
        original_scandir = os.scandir

        def failing_scandir(path):
            if str(path) == str(extra_root):
                raise PermissionError('source temporarily unreadable')
            return original_scandir(path)

        monkeypatch.setattr(os, 'scandir', failing_scandir)
    else:
        from pathlib import Path
        original_stat = Path.stat

        def failing_stat(path, *args, **kwargs):
            if path == extra_root / 'photo.jpg':
                raise PermissionError('file temporarily unreadable')
            return original_stat(path, *args, **kwargs)

        monkeypatch.setattr(Path, 'stat', failing_stat)
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
    app = create_app({"TESTING": True, "MEDIA_ROOT": media_root})
    local_client = app.test_client()

    payload = local_client.get("/api/library/items?scope=all").get_json()["data"]
    item = payload["items"][0]
    assert (item['width'], item['height']) == (1400, 900)
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

    monkeypatch.setenv("MEDIA_ROOT", str(media_root))
    app = create_app({"TESTING": True, "MEDIA_ROOT": media_root})
    local_client = app.test_client()

    items = local_client.get('/api/library/items').get_json()['data']['items']
    assert {item['name'] for item in items} == {
        f'@default/{video_name}', f'@default/{image_name}',
    }
    for item in items:
        expected = b'video' if item['type'] == 'video' else b'image'
        assert local_client.get(item['media_url']).data == expected
        assert local_client.get(item['detail_url']).status_code == 200
        legacy = local_client.get('/media', query_string={'uri': item['name']}, follow_redirects=True)
        assert legacy.data == expected

    deleted = local_client.post(f"/delete/{quote('@default/' + image_name, safe='')}")
    assert deleted.status_code == 302
    assert not (media_root / image_name).exists()
    assert (media_root / video_name).exists()
