import os
from urllib.parse import quote

import pytest

from tiklocal.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    (media_root / "clip.mp4").write_bytes(b"video")
    (media_root / "cover.jpg").write_bytes(b"image")
    (media_root / "odd & hash#.jpg").write_bytes(b"image")

    data_root = tmp_path / "tiklocal-data"
    monkeypatch.setenv("MEDIA_ROOT", str(media_root))
    monkeypatch.setenv("TIKLOCAL_INSTANCE", str(data_root))

    app = create_app({"TESTING": True, "MEDIA_ROOT": media_root})
    return app.test_client()


def test_collection_create_and_list(client):
    created = client.post(
        "/api/collections",
        json={"name": "灵感片段", "description": "测试集合"},
    )
    assert created.status_code == 200
    payload = created.get_json()["data"]["item"]
    assert payload["name"] == "灵感片段"
    assert payload["item_count"] == 0
    assert payload["id"].startswith("col_")

    listed = client.get("/api/collections")
    assert listed.status_code == 200
    items = listed.get_json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["id"] == payload["id"]


def test_collection_add_remove_and_by_media(client):
    created = client.post("/api/collections", json={"name": "收藏一"}).get_json()["data"]["item"]
    collection_id = created["id"]

    added = client.post(
        f"/api/collections/{quote(collection_id, safe='')}/items",
        json={"uris": ["clip.mp4", "odd & hash#.jpg"]},
    )
    assert added.status_code == 200
    assert added.get_json()["data"]["item"]["item_count"] == 2

    by_media = client.get(f"/api/collections/by-media?uri={quote('odd & hash#.jpg', safe='')}")
    assert by_media.status_code == 200
    items = by_media.get_json()["data"]["items"]
    assert any(item["id"] == collection_id for item in items)

    removed = client.delete(
        f"/api/collections/{quote(collection_id, safe='')}/items",
        json={"uris": ["clip.mp4"]},
    )
    assert removed.status_code == 200
    assert removed.get_json()["data"]["item"]["item_count"] == 1

    by_media_after = client.get(f"/api/collections/by-media?uri={quote('clip.mp4', safe='')}")
    assert by_media_after.status_code == 200
    items_after = by_media_after.get_json()["data"]["items"]
    assert all(item["id"] != collection_id for item in items_after)


def test_collection_scope_library_items_and_page(client):
    created = client.post("/api/collections", json={"name": "媒体集"}).get_json()["data"]["item"]
    collection_id = created["id"]
    client.post(
        f"/api/collections/{quote(collection_id, safe='')}/items",
        json={"uris": ["clip.mp4", "cover.jpg"]},
    )

    page = client.get(f"/collection/{quote(collection_id, safe='')}")
    assert page.status_code == 200
    body = page.data.decode("utf-8")
    assert 'const scope = "collection";' in body
    assert f'const collectionId = "{collection_id}";' in body
    assert 'id="quick-set-cover"' in body
    assert 'id="quick-collection-count"' in body
    assert "toggleCollectionMembership(" in body

    api_res = client.get(
        f"/api/library/items?scope=collection&collection_id={quote(collection_id, safe='')}&offset=0&limit=20"
    )
    assert api_res.status_code == 200
    payload = api_res.get_json()["data"]
    names = {item["name"] for item in payload["items"]}
    assert "clip.mp4" in names
    assert "cover.jpg" in names

    bad = client.get("/api/library/items?scope=collection&offset=0&limit=20")
    assert bad.status_code == 400
    assert bad.get_json()["success"] is False


def test_collection_patch_cover_and_delete(client):
    created = client.post("/api/collections", json={"name": "可编辑集合"}).get_json()["data"]["item"]
    collection_id = created["id"]
    client.post(
        f"/api/collections/{quote(collection_id, safe='')}/items",
        json={"uris": ["cover.jpg"]},
    )

    renamed = client.patch(
        f"/api/collections/{quote(collection_id, safe='')}",
        json={"name": "新名字", "cover_uri": "cover.jpg"},
    )
    assert renamed.status_code == 200
    item = renamed.get_json()["data"]["item"]
    assert item["name"] == "新名字"
    assert item["cover_uri"] == "cover.jpg"

    detail = client.get(f"/api/collections/{quote(collection_id, safe='')}")
    assert detail.status_code == 200
    assert detail.get_json()["data"]["item"]["cover_uri"] == "cover.jpg"

    deleted = client.delete(f"/api/collections/{quote(collection_id, safe='')}")
    assert deleted.status_code == 200
    assert deleted.get_json()["data"]["deleted"] is True

    missing = client.get(f"/api/collections/{quote(collection_id, safe='')}")
    assert missing.status_code == 404
