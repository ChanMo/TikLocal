from PIL import Image

from tiklocal.app import create_app
from tiklocal.services.embedded_metadata import read_embedded_generation


def _write_jpeg_with_comment(path, comment: str):
    image = Image.new("RGB", (16, 16), color=(128, 128, 128))
    image.save(path, format="JPEG", comment=comment.encode("utf-8"))


def test_read_embedded_generation_from_jpeg_comment(tmp_path):
    image_path = tmp_path / "generated.jpg"
    _write_jpeg_with_comment(
        image_path,
        "Prompt: cinematic portrait with soft window light | Model: x-ai/grok-imagine-image-quality | GeneratedBy: Hermes or-img",
    )

    payload = read_embedded_generation(image_path)

    assert payload is not None
    assert payload["source_format"] == "jpeg_comment"
    assert payload["prompt"] == "cinematic portrait with soft window light"
    assert payload["model"] == "x-ai/grok-imagine-image-quality"


def test_embedded_metadata_api_returns_prompt_and_model(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    image_path = media_root / "generated.jpg"
    _write_jpeg_with_comment(
        image_path,
        "Prompt: bathroom editorial portrait | Model: x-ai/grok-imagine-image-quality | GeneratedAt: 2026-06-06T20:28:16+08:00",
    )

    data_root = tmp_path / "tiklocal-data"
    monkeypatch.setenv("MEDIA_ROOT", str(media_root))
    monkeypatch.setenv("TIKLOCAL_INSTANCE", str(data_root))
    app = create_app({"TESTING": True, "MEDIA_ROOT": media_root})
    client = app.test_client()

    res = client.get("/api/image/embedded-metadata?uri=generated.jpg")
    data = res.get_json()

    assert res.status_code == 200
    assert data["success"] is True
    embedded = data["data"]["embedded_generation"]
    assert embedded["prompt"] == "bathroom editorial portrait"
    assert embedded["model"] == "x-ai/grok-imagine-image-quality"


def test_image_detail_has_embedded_generation_panel(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    image_path = media_root / "generated.jpg"
    _write_jpeg_with_comment(
        image_path,
        "Prompt: compact prompt | Model: demo-model",
    )

    data_root = tmp_path / "tiklocal-data"
    monkeypatch.setenv("MEDIA_ROOT", str(media_root))
    monkeypatch.setenv("TIKLOCAL_INSTANCE", str(data_root))
    app = create_app({"TESTING": True, "MEDIA_ROOT": media_root})
    client = app.test_client()

    res = client.get("/image?uri=generated.jpg")
    body = res.data.decode("utf-8")

    assert res.status_code == 200
    assert 'id="embedded-generation-card"' in body
    assert 'id="embedded-model"' in body
    assert 'id="embedded-prompt"' in body
    assert "/api/image/embedded-metadata" in body
