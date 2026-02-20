import pytest

from tiklocal.app import create_app
from tiklocal.services.metadata import PromptConfigStore


def _build_prompt_payload(enabled: bool = True, tags_limit: int = 5, temperature: float = 0.6):
    return {
        "enabled": enabled,
        "system_prompt": "你是一个测试助手，只能输出 JSON。",
        "user_prompt": "请给出标题和 {tags_limit} 个标签。",
        "temperature": temperature,
        "tags_limit": tags_limit,
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    (media_root / "photo.jpg").write_bytes(b"fake-image")

    data_root = tmp_path / "tiklocal-data"
    monkeypatch.setenv("MEDIA_ROOT", str(media_root))
    monkeypatch.setenv("TIKLOCAL_INSTANCE", str(data_root))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("TIKLOCAL_LLM_MODEL", "test-model")

    calls = []

    def fake_generate(self, image_path, tags_limit=5, prompt_config=None):  # noqa: ARG001
        calls.append({"tags_limit": tags_limit, "prompt_config": prompt_config or {}})
        return {
            "title": "测试标题",
            "tags": ["测试"],
            "model": self.model,
            "provider": "openai",
            "base_url": self.base_url or "",
            "prompt_version": 2,
            "prompt_hash": "deadbeef",
        }

    monkeypatch.setattr("tiklocal.services.metadata.CaptionService.generate", fake_generate)

    app = create_app({"TESTING": True, "MEDIA_ROOT": media_root})
    return app.test_client(), calls


def test_prompt_config_store_roundtrip(tmp_path):
    store_path = tmp_path / "prompt_config.json"
    store = PromptConfigStore(store_path)

    assert store.get() is None

    saved = store.set(_build_prompt_payload())
    assert saved["enabled"] is True
    assert "updated_at" in saved

    loaded = store.get()
    assert loaded is not None
    assert loaded["system_prompt"] == "你是一个测试助手，只能输出 JSON。"
    assert loaded["tags_limit"] == 5

    store.reset()
    assert store.get() is None


def test_prompt_config_api_crud(client):
    test_client, _ = client

    res = test_client.get("/api/ai/prompt-config")
    data = res.get_json()
    assert res.status_code == 200
    assert data["success"] is True
    assert data["data"]["active_profile"] == "default"

    save_payload = _build_prompt_payload(enabled=True, tags_limit=7, temperature=0.8)
    res = test_client.post("/api/ai/prompt-config", json=save_payload)
    data = res.get_json()
    assert res.status_code == 200
    assert data["success"] is True
    assert data["data"]["active_profile"] == "custom"
    assert data["data"]["custom"]["tags_limit"] == 7
    assert data["data"]["custom"]["enabled"] is True

    res = test_client.post("/api/ai/prompt-config/reset")
    data = res.get_json()
    assert res.status_code == 200
    assert data["success"] is True
    assert data["data"]["active_profile"] == "default"
    assert data["data"]["custom"] is None


def test_prompt_config_api_validation(client):
    test_client, _ = client
    payload = _build_prompt_payload(temperature=2.5)

    res = test_client.post("/api/ai/prompt-config", json=payload)
    data = res.get_json()
    assert res.status_code == 400
    assert data["success"] is False
    assert "temperature" in data["error"]


def test_metadata_prompt_source_priority(client):
    test_client, calls = client

    custom_payload = _build_prompt_payload(enabled=True, tags_limit=7, temperature=0.7)
    res = test_client.post("/api/ai/prompt-config", json=custom_payload)
    assert res.status_code == 200

    res = test_client.post(
        "/api/image/metadata",
        json={"uri": "photo.jpg", "force": True},
    )
    data = res.get_json()
    assert res.status_code == 200
    assert data["success"] is True
    assert data["data"]["prompt_source"] == "custom"
    assert calls[-1]["prompt_config"]["tags_limit"] == 7

    override = {
        "system_prompt": "仅本次覆盖",
        "user_prompt": "请输出 1 到 {tags_limit} 个标签",
        "temperature": 0.3,
        "tags_limit": 3,
    }
    res = test_client.post(
        "/api/image/metadata",
        json={"uri": "photo.jpg", "force": True, "prompt_override": override},
    )
    data = res.get_json()
    assert res.status_code == 200
    assert data["success"] is True
    assert data["data"]["prompt_source"] == "override"
    assert calls[-1]["prompt_config"]["tags_limit"] == 3


def test_llm_config_api_crud(client):
    test_client, _ = client

    res = test_client.get("/api/ai/llm-config")
    data = res.get_json()
    assert res.status_code == 200
    assert data["success"] is True
    assert "effective" in data["data"]
    assert "has_api_key" in data["data"]

    payload = {
        "model_name": "gpt-test-custom",
        "base_url": "https://example.com/v1",
    }
    res = test_client.post("/api/ai/llm-config", json=payload)
    data = res.get_json()
    assert res.status_code == 200
    assert data["success"] is True
    assert data["data"]["effective"]["model_name"] == "gpt-test-custom"
    assert data["data"]["effective"]["base_url"] == "https://example.com/v1"
    assert data["data"]["active_profile"] == "custom"

    res = test_client.post("/api/ai/llm-config/reset")
    data = res.get_json()
    assert res.status_code == 200
    assert data["success"] is True
    assert data["data"]["active_profile"] == "default"


def test_llm_config_api_validation(client):
    test_client, _ = client
    res = test_client.post(
        "/api/ai/llm-config",
        json={"model_name": "gpt-test", "base_url": "ftp://invalid-url"},
    )
    data = res.get_json()
    assert res.status_code == 400
    assert data["success"] is False
    assert "base_url" in data["error"]


def test_metadata_uses_custom_llm_settings(client):
    test_client, _ = client

    res = test_client.post(
        "/api/ai/llm-config",
        json={"model_name": "gpt-override", "base_url": "https://custom.example/v1"},
    )
    assert res.status_code == 200

    res = test_client.post("/api/image/metadata", json={"uri": "photo.jpg", "force": True})
    data = res.get_json()
    assert res.status_code == 200
    assert data["success"] is True
    assert data["data"]["model"] == "gpt-override"
    assert data["data"]["base_url"] == "https://custom.example/v1"
    assert data["data"]["llm_source"] == "custom"
