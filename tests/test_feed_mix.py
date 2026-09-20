import json
import sqlite3

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

    monkeypatch.setenv("MEDIA_ROOT", str(media_root))

    app = create_app({"TESTING": True, "MEDIA_ROOT": media_root})
    return app.test_client()


def test_mix_feed_returns_typed_items(client):
    res = client.get("/api/feed/mix?page=1&size=12&seed=fixed-seed&snapshot=1")
    assert res.status_code == 200
    data = res.get_json()

    assert isinstance(data, dict)
    assert "items" in data
    assert "seed" in data
    assert "has_more" in data
    assert data["has_more"] is False

    items = data["items"]
    assert isinstance(items, list)
    assert len(items) > 0

    types = {item.get("type") for item in items}
    assert "video" in types
    assert "image" in types

    for item in items:
        assert "name" in item
        if item.get("type") == "theme_strip":
            assert item["items"]
            assert item["target_url"]
            continue
        assert "media_url" in item
        assert "detail_url" in item
        assert item["recommendation_reason"]
        assert item["type"] in {"video", "image"}
        if item["type"] == "video":
            assert item["detail_url"].startswith("/detail/")
        else:
            assert item["detail_url"].startswith("/image?uri=")


@pytest.mark.parametrize('extension,grouped,count', [
    ('mp4', False, 24), ('jpg', False, 24), ('jpg', True, 24),
    ('mixed', False, 24), ('jpg', False, 0),
])
def test_feed_cards_and_groups_preserve_all_media_across_pages(tmp_path, monkeypatch, extension, grouped, count):
    media_root = tmp_path / 'media'
    media_root.mkdir()
    names = [
        f'item-{index:02d}.{("mp4" if index < 6 else "jpg") if extension == "mixed" else extension}'
        for index in range(count)
    ]
    for name in names:
        (media_root / name).write_bytes(b'media')
    data_root = tmp_path / 'tiklocal-data'
    data_root.mkdir()
    if grouped:
        (data_root / 'download_sources.json').write_text(json.dumps({
            'version': 1,
            'items': {f'@default/{name}': {
                'source_url_raw': 'https://example.com/post/1',
                'source_url_display': 'https://example.com/post/1',
                'source_domain': 'example.com',
                'job_id': 'one-post',
            } for name in names},
        }))
    client = create_app({'TESTING': True, 'MEDIA_ROOT': media_root}).test_client()

    seen, theme_count, group_count = [], 0, 0
    pages = max(1, (count + 7) // 8)
    for page in range(1, pages + 1):
        response = client.get('/api/feed/mix', query_string={'page': page, 'size': 8, 'seed': 'fixed'})
        assert response.status_code == 200
        payload = response.get_json()
        page_names = []
        for item in payload['items']:
            if item['type'] == 'theme_strip':
                theme_count += 1
                assert page == 1
                assert client.get(item['target_url']).status_code == 200
            elif item['type'] == 'image_group':
                group_count += 1
                page_names.extend(child['name'] for child in item['items'])
                assert all(client.get(child['media_url']).data == b'media' for child in item['items'])
            else:
                page_names.append(item['name'])
        assert len(page_names) == min(8, count)
        assert not set(page_names).intersection(seen)
        assert payload['has_more'] is (page < pages)
        seen.extend(page_names)
    assert set(seen) == {f'@default/{name}' for name in names}
    assert theme_count == (1 if count else 0)
    assert group_count == (3 if grouped else 0)


def test_flow_activity_builds_and_clears_local_profile(client, tmp_path):
    events = [
        {
            "session_id": "session-1",
            "uri": "@default/nested/v 3.mp4",
            "media_type": "video",
            "surface": "flow",
            "event": "impression",
        },
        {
            "session_id": "session-1",
            "uri": "@default/nested/v 3.mp4",
            "media_type": "video",
            "surface": "flow",
            "event": "complete",
            "ratio": 0.94,
            "visible_ms": 12000,
        },
    ]
    res = client.post("/api/activity", json={"events": events})

    assert res.status_code == 200
    assert res.get_json()["data"]["accepted"] == 2
    db_path = tmp_path / "tiklocal-data" / "tiklocal.sqlite3"
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT impressions, completes, affinity_score FROM media_affinity WHERE uri = ?",
            ("@default/nested/v 3.mp4",),
        ).fetchone()
        dimensions = dict(conn.execute(
            """
            SELECT dimension_type, positive_score
            FROM preference_dimensions
            WHERE dimension_value IN ('video', 'default', 'default/nested')
            """
        ).fetchall())
    assert row[0:2] == (1, 1)
    assert row[2] > 0
    assert set(dimensions) == {"media_type", "source", "directory"}
    assert all(score > 0 for score in dimensions.values())

    assert client.delete("/api/activity").get_json()["success"] is True
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM media_affinity").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM preference_dimensions").fetchone()[0] == 0
