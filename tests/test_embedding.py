from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from tiklocal.app import create_app
from tiklocal.run import run_vectorize
from tiklocal.services.database import AppDatabase
from tiklocal.services.embedding import (
    EmbeddingConfigStore,
    OpenAICompatibleImageEmbeddingClient,
    SQLiteImageVectorStore,
    validate_embedding_config,
)


class FakeVectorIndex:
    def __init__(self):
        self.items = {}

    def is_available(self):
        return True

    def get_all_metadata(self):
        return {key: value["metadata"] for key, value in self.items.items()}

    def get_metadata(self, uri):
        item = self.items.get(uri)
        return item["metadata"] if item else None

    def upsert_image(self, *, uri, embedding, metadata):
        self.items[uri] = {"embedding": embedding, "metadata": metadata}

    def delete(self, ids):
        for item_id in ids:
            self.items.pop(item_id, None)

    def query_similar(self, uri, *, limit=12):
        results = []
        for item_id in self.items:
            if item_id == uri:
                continue
            results.append({"uri": item_id, "metadata": self.items[item_id]["metadata"], "distance": 0.25})
            if len(results) >= limit:
                break
        return results


def test_embedding_config_store_roundtrip(tmp_path):
    store = EmbeddingConfigStore(tmp_path / "embedding_config.json")
    assert store.get() is None

    payload = {
        "enabled": True,
        "base_url": "https://openrouter.ai/api/v1",
        "model_name": "google/gemini-embedding-2",
        "dimensions": 768,
        "image_max_size": 512,
        "image_quality": 82,
    }
    saved = store.set(payload)
    assert saved["enabled"] is True
    assert "updated_at" in saved

    loaded = store.get()
    assert loaded is not None
    assert loaded["model_name"] == "google/gemini-embedding-2"
    assert loaded["dimensions"] == 768
    assert loaded["image_max_size"] == 512
    assert loaded["image_quality"] == 82

    store.reset()
    assert store.get() is None


def test_embedding_config_validation():
    validated, error = validate_embedding_config(
        {
            "enabled": True,
            "base_url": "https://example.com/v1",
            "model_name": "demo-embedding",
            "dimensions": 128,
            "image_max_size": 512,
            "image_quality": 82,
        }
    )
    assert error is None
    assert validated["dimensions"] == 128
    assert validated["image_max_size"] == 512
    assert validated["image_quality"] == 82

    _, error = validate_embedding_config(
        {
            "enabled": True,
            "base_url": "ftp://example.com",
            "model_name": "demo-embedding",
            "dimensions": 768,
        }
    )
    assert "base_url" in error

    _, error = validate_embedding_config(
        {
            "enabled": True,
            "base_url": "https://example.com/v1",
            "model_name": "demo-embedding",
            "dimensions": 64,
        }
    )
    assert "dimensions" in error

    _, error = validate_embedding_config(
        {
            "enabled": True,
            "base_url": "https://example.com/v1",
            "model_name": "demo-embedding",
            "dimensions": 768,
            "image_max_size": 64,
        }
    )
    assert "image_max_size" in error


def test_openai_compatible_image_embedding_payload(tmp_path, monkeypatch):
    image_path = tmp_path / "photo.jpg"
    Image.new("RGB", (8, 8), (255, 0, 0)).save(image_path)
    calls = []

    class Response:
        status_code = 200
        text = '{"data":[{"embedding":[0.1,0.2]}]}'

        def json(self):
            return {"data": [{"embedding": [0.1, 0.2]}]}

    def fake_post(url, headers, json, timeout):  # noqa: A002
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return Response()

    monkeypatch.setattr("tiklocal.services.embedding.requests.post", fake_post)
    client = OpenAICompatibleImageEmbeddingClient(
        model="google/gemini-embedding-2",
        base_url="https://openrouter.ai/api/v1",
        dimensions=768,
        image_max_size=512,
        image_quality=82,
        api_key="test-key",
    )

    embedding = client.embed_image(image_path)

    assert embedding == [0.1, 0.2]
    assert calls[0]["url"] == "https://openrouter.ai/api/v1/embeddings"
    assert calls[0]["json"]["model"] == "google/gemini-embedding-2"
    assert calls[0]["json"]["dimensions"] == 768
    image_url = calls[0]["json"]["input"][0]["content"][0]["image_url"]["url"]
    assert image_url.startswith("data:image/jpeg;base64,")


def test_sqlite_image_vector_store_roundtrip(tmp_path):
    database = AppDatabase(tmp_path / "tiklocal.sqlite3")
    database.migrate()
    store = SQLiteImageVectorStore(database)

    store.upsert_image(
        uri="@default/a.jpg",
        embedding=[1.0, 0.0],
        metadata={
            "source_id": "default",
            "rel_path": "a.jpg",
            "model": "demo-embedding",
            "dimensions": 2,
            "image_max_size": 512,
            "image_quality": 82,
            "mtime": 10.0,
            "size_bytes": 100,
            "indexed_at": "2026-06-07T00:00:00Z",
        },
    )
    store.upsert_image(
        uri="@default/b.jpg",
        embedding=[0.9, 0.1],
        metadata={
            "source_id": "default",
            "rel_path": "b.jpg",
            "model": "demo-embedding",
            "dimensions": 2,
            "image_max_size": 512,
            "image_quality": 82,
            "mtime": 11.0,
            "size_bytes": 101,
            "indexed_at": "2026-06-07T00:00:01Z",
        },
    )

    metadata = store.get_metadata("@default/a.jpg")
    assert metadata["model"] == "demo-embedding"
    assert metadata["dimensions"] == 2

    similar = store.query_similar("@default/a.jpg", limit=4)
    assert len(similar) == 1
    assert similar[0]["uri"] == "@default/b.jpg"
    assert similar[0]["distance"] < 0.01

    store.delete(["@default/b.jpg"])
    assert store.get_metadata("@default/b.jpg") is None


@pytest.fixture
def embedding_client(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    (media_root / "a.jpg").write_bytes(b"fake-a")
    (media_root / "b.jpg").write_bytes(b"fake-b")

    data_root = tmp_path / "tiklocal-data"
    monkeypatch.setenv("TIKLOCAL_INSTANCE", str(data_root))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    class FakeEmbeddingClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def embed_image(self, image_path):
            return [1.0, 0.0] if Path(image_path).name == "a.jpg" else [0.9, 0.1]

    monkeypatch.setattr("tiklocal.app.OpenAICompatibleImageEmbeddingClient", FakeEmbeddingClient)
    fake_index = FakeVectorIndex()
    app = create_app(
        {
            "TESTING": True,
            "MEDIA_ROOT": media_root,
            "VECTOR_INDEX": fake_index,
            "EMBEDDING_CONFIG": {
                "enabled": True,
                "base_url": "https://openrouter.ai/api/v1",
                "model_name": "google/gemini-embedding-2",
                "dimensions": 768,
                "image_max_size": 512,
                "image_quality": 82,
            },
        }
    )
    return app.test_client(), fake_index


def test_embedding_index_run_and_similar_api(embedding_client):
    client, fake_index = embedding_client

    res = client.get("/api/ai/embedding-config")
    data = res.get_json()
    assert res.status_code == 200
    assert data["data"]["effective"]["enabled"] is True

    res = client.post("/api/ai/embedding-index/run")
    data = res.get_json()
    assert res.status_code == 200
    assert data["success"] is True
    assert data["data"]["indexed"] == 2
    assert len(fake_index.items) == 2

    res = client.get("/api/recommend/similar?uri=a.jpg&limit=4")
    data = res.get_json()
    assert res.status_code == 200
    assert data["success"] is True
    assert data["data"]["indexed"] is True
    assert len(data["data"]["items"]) == 1
    assert data["data"]["items"][0]["name"].endswith("b.jpg")


def test_vectorize_cli_dry_run(tmp_path, monkeypatch, capsys):
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    (media_root / "a.jpg").write_bytes(b"fake-a")
    data_root = tmp_path / "tiklocal-data"
    monkeypatch.setenv("TIKLOCAL_INSTANCE", str(data_root))

    args = SimpleNamespace(
        media_root=str(media_root),
        media_source=None,
        source=None,
        limit=1,
        order="latest",
        dry_run=True,
        force=False,
        cleanup=False,
        continue_after_cleanup=False,
        max_size=None,
        quality=None,
        dimensions=None,
        yes=True,
    )

    class Parser:
        def error(self, message):
            raise AssertionError(message)

    config = {
        "embedding": {
            "enabled": True,
            "base_url": "https://openrouter.ai/api/v1",
            "model_name": "google/gemini-embedding-2",
            "dimensions": 768,
            "image_max_size": 512,
            "image_quality": 82,
        }
    }

    run_vectorize(config, args, Parser())

    out = capsys.readouterr().out
    assert "TikLocal image vectorization" in out
    assert "selected this run: 1" in out
    assert "image_max_size: 512" in out
