import datetime
import json
import os
from pathlib import Path
from typing import Any

from tiklocal.paths import get_embedding_config_path


EMBEDDING_BASE_URL_MAX_LENGTH = 512
EMBEDDING_MODEL_NAME_MAX_LENGTH = 256
EMBEDDING_DIMENSIONS_MIN = 128
EMBEDDING_DIMENSIONS_MAX = 3072
EMBEDDING_IMAGE_MAX_SIZE_MIN = 128
EMBEDDING_IMAGE_MAX_SIZE_MAX = 2048
EMBEDDING_IMAGE_QUALITY_MIN = 50
EMBEDDING_IMAGE_QUALITY_MAX = 95

DEFAULT_EMBEDDING_CONFIG = {
    "enabled": False,
    "base_url": "https://openrouter.ai/api/v1",
    "model_name": "google/gemini-embedding-2",
    "dimensions": 768,
    "image_max_size": 512,
    "image_quality": 82,
}


def get_default_embedding_config() -> dict[str, Any]:
    return dict(DEFAULT_EMBEDDING_CONFIG)


def merge_embedding_config(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(base)
    if not override:
        return merged
    for key in ("enabled", "base_url", "model_name", "dimensions", "image_max_size", "image_quality"):
        if key in override:
            merged[key] = override[key]
    return merged


def validate_embedding_config(
    payload: Any,
    *,
    partial: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(payload, dict):
        return None, "Configuration must be a JSON object."

    cleaned: dict[str, Any] = {}

    if "enabled" in payload:
        if not isinstance(payload["enabled"], bool):
            return None, "enabled must be a boolean."
        cleaned["enabled"] = payload["enabled"]
    elif not partial:
        cleaned["enabled"] = bool(DEFAULT_EMBEDDING_CONFIG["enabled"])

    if "base_url" in payload or not partial:
        base_url = str(payload.get("base_url", DEFAULT_EMBEDDING_CONFIG["base_url"])).strip()
        if len(base_url) > EMBEDDING_BASE_URL_MAX_LENGTH:
            return None, f"base_url cannot exceed {EMBEDDING_BASE_URL_MAX_LENGTH} characters."
        if base_url and not (base_url.startswith("http://") or base_url.startswith("https://")):
            return None, "base_url must start with http:// or https://."
        cleaned["base_url"] = base_url

    if "model_name" in payload or not partial:
        model_name = str(payload.get("model_name", DEFAULT_EMBEDDING_CONFIG["model_name"])).strip()
        if len(model_name) > EMBEDDING_MODEL_NAME_MAX_LENGTH:
            return None, f"model_name cannot exceed {EMBEDDING_MODEL_NAME_MAX_LENGTH} characters."
        cleaned["model_name"] = model_name

    if "dimensions" in payload or not partial:
        try:
            dimensions = int(payload.get("dimensions", DEFAULT_EMBEDDING_CONFIG["dimensions"]))
        except (TypeError, ValueError):
            return None, "dimensions must be an integer."
        if not (EMBEDDING_DIMENSIONS_MIN <= dimensions <= EMBEDDING_DIMENSIONS_MAX):
            return None, f"dimensions must be between {EMBEDDING_DIMENSIONS_MIN} and {EMBEDDING_DIMENSIONS_MAX}."
        cleaned["dimensions"] = dimensions

    if "image_max_size" in payload or not partial:
        try:
            image_max_size = int(payload.get("image_max_size", DEFAULT_EMBEDDING_CONFIG["image_max_size"]))
        except (TypeError, ValueError):
            return None, "image_max_size must be an integer."
        if not (EMBEDDING_IMAGE_MAX_SIZE_MIN <= image_max_size <= EMBEDDING_IMAGE_MAX_SIZE_MAX):
            return None, f"image_max_size must be between {EMBEDDING_IMAGE_MAX_SIZE_MIN} and {EMBEDDING_IMAGE_MAX_SIZE_MAX}."
        cleaned["image_max_size"] = image_max_size

    if "image_quality" in payload or not partial:
        try:
            image_quality = int(payload.get("image_quality", DEFAULT_EMBEDDING_CONFIG["image_quality"]))
        except (TypeError, ValueError):
            return None, "image_quality must be an integer."
        if not (EMBEDDING_IMAGE_QUALITY_MIN <= image_quality <= EMBEDDING_IMAGE_QUALITY_MAX):
            return None, f"image_quality must be between {EMBEDDING_IMAGE_QUALITY_MIN} and {EMBEDDING_IMAGE_QUALITY_MAX}."
        cleaned["image_quality"] = image_quality

    return cleaned, None


class EmbeddingConfigStore:
    def __init__(self, store_path: Path):
        self.store_path = store_path
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, Any]:
        if not self.store_path.exists():
            return {}
        try:
            with self.store_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def get(self) -> dict[str, Any] | None:
        data = self._load()
        if not data:
            return None
        validated, error = validate_embedding_config(data, partial=False)
        if error:
            return None
        if isinstance(data.get("updated_at"), str):
            validated["updated_at"] = data["updated_at"]
        return validated

    def set(self, value: dict[str, Any]) -> dict[str, Any]:
        payload = dict(value)
        payload["updated_at"] = datetime.datetime.utcnow().isoformat() + "Z"
        self._write(payload)
        return payload

    def reset(self) -> None:
        try:
            self.store_path.unlink(missing_ok=True)
        except Exception:
            pass

    def _write(self, data: dict[str, Any]) -> None:
        tmp_path = self.store_path.with_name(self.store_path.name + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.store_path)


def resolve_embedding_config(config, args=None):
    effective = get_default_embedding_config()
    file_config, error = validate_embedding_config(config.get('embedding') or config.get('embedding_config') or {}, partial=True)
    if error:
        file_config = {}
    effective = merge_embedding_config(effective, file_config)

    effective = merge_embedding_config(effective, EmbeddingConfigStore(get_embedding_config_path()).get())

    if args is not None:
        overrides = {}
        if getattr(args, 'max_size', None):
            overrides['image_max_size'] = args.max_size
        if getattr(args, 'quality', None):
            overrides['image_quality'] = args.quality
        if getattr(args, 'dimensions', None):
            overrides['dimensions'] = args.dimensions
        if overrides:
            validated, error = validate_embedding_config(overrides, partial=True)
            if error:
                raise ValueError(error)
            effective = merge_embedding_config(effective, validated)
    return effective

