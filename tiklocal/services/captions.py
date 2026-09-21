import base64
import datetime
import hashlib
import io
import json
import mimetypes
import os
import re
import requests
from pathlib import Path
from typing import Any

from PIL import Image

from tiklocal.services.json_storage import write_json_atomic


PROMPT_TEMPLATE_VERSION = 3
PROMPT_MAX_SYSTEM_LENGTH = 4000
PROMPT_MAX_USER_LENGTH = 8000
PROMPT_TEMPERATURE_MIN = 0.0
PROMPT_TEMPERATURE_MAX = 2.0
PROMPT_TAGS_MIN = 1
PROMPT_TAGS_MAX = 20
LLM_BASE_URL_MAX_LENGTH = 512
LLM_MODEL_NAME_MAX_LENGTH = 256

DEFAULT_PROMPT_CONFIG = {
    "system_prompt": (
        "You analyze images for a local media library. Generate a concise English title and tags "
        "based on the visible content. Return JSON only, without Markdown."
    ),
    "user_prompt": (
        "Analyze this image and generate:\n"
        "1. A short, natural English title\n"
        "2. Up to {tags_limit} concise English tags\n\n"
        "Output JSON: {\"title\":\"...\",\"tags\":[\"...\"]}"
    ),
    "temperature": 0.6,
    "tags_limit": 5,
    "enabled": False,
}

DEFAULT_VISION_CONFIG = {
    "enabled": True,
    "base_url": "",
    "model_name": "",
    "system_prompt": DEFAULT_PROMPT_CONFIG["system_prompt"],
    "user_prompt": DEFAULT_PROMPT_CONFIG["user_prompt"],
    "temperature": DEFAULT_PROMPT_CONFIG["temperature"],
    "tags_limit": DEFAULT_PROMPT_CONFIG["tags_limit"],
}


def get_default_prompt_config() -> dict[str, Any]:
    return dict(DEFAULT_PROMPT_CONFIG)


def get_default_vision_config() -> dict[str, Any]:
    return dict(DEFAULT_VISION_CONFIG)


def merge_vision_config(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(base)
    if not override:
        return merged
    for key in ("enabled", "base_url", "model_name", "system_prompt", "user_prompt", "temperature", "tags_limit"):
        if key in override:
            merged[key] = override[key]
    return merged


def validate_prompt_config(
    payload: Any,
    *,
    partial: bool = False,
    include_enabled: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(payload, dict):
        return None, "Configuration must be a JSON object."

    cleaned: dict[str, Any] = {}

    def _read_text(field: str, max_length: int) -> tuple[str | None, str | None]:
        if field not in payload:
            if partial:
                return None, None
            return None, f"Missing field: {field}"
        value = str(payload.get(field, "")).strip()
        if not value:
            return None, f"{field} cannot be empty."
        if len(value) > max_length:
            return None, f"{field} cannot exceed {max_length} characters."
        return value, None

    system_prompt, error = _read_text("system_prompt", PROMPT_MAX_SYSTEM_LENGTH)
    if error:
        return None, error
    if system_prompt is not None:
        cleaned["system_prompt"] = system_prompt

    user_prompt, error = _read_text("user_prompt", PROMPT_MAX_USER_LENGTH)
    if error:
        return None, error
    if user_prompt is not None:
        cleaned["user_prompt"] = user_prompt

    if "temperature" in payload:
        try:
            temperature = float(payload["temperature"])
        except (TypeError, ValueError):
            return None, "temperature must be a number."
        if not (PROMPT_TEMPERATURE_MIN <= temperature <= PROMPT_TEMPERATURE_MAX):
            return None, f"temperature must be between {PROMPT_TEMPERATURE_MIN} and {PROMPT_TEMPERATURE_MAX}."
        cleaned["temperature"] = temperature
    elif not partial:
        cleaned["temperature"] = float(DEFAULT_PROMPT_CONFIG["temperature"])

    if "tags_limit" in payload:
        try:
            tags_limit = int(payload["tags_limit"])
        except (TypeError, ValueError):
            return None, "tags_limit must be an integer."
        if not (PROMPT_TAGS_MIN <= tags_limit <= PROMPT_TAGS_MAX):
            return None, f"tags_limit must be between {PROMPT_TAGS_MIN} and {PROMPT_TAGS_MAX}."
        cleaned["tags_limit"] = tags_limit
    elif not partial:
        cleaned["tags_limit"] = int(DEFAULT_PROMPT_CONFIG["tags_limit"])

    if include_enabled:
        if "enabled" in payload:
            value = payload["enabled"]
            if not isinstance(value, bool):
                return None, "enabled must be a boolean."
            cleaned["enabled"] = value
        elif not partial:
            cleaned["enabled"] = bool(DEFAULT_PROMPT_CONFIG["enabled"])

    return cleaned, None


def validate_llm_config(
    payload: Any,
    *,
    partial: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(payload, dict):
        return None, "Configuration must be a JSON object."

    cleaned: dict[str, Any] = {}

    if "base_url" in payload or not partial:
        base_url = str(payload.get("base_url", "")).strip()
        if len(base_url) > LLM_BASE_URL_MAX_LENGTH:
            return None, f"base_url cannot exceed {LLM_BASE_URL_MAX_LENGTH} characters."
        if base_url and not (base_url.startswith("http://") or base_url.startswith("https://")):
            return None, "base_url must start with http:// or https://."
        cleaned["base_url"] = base_url

    if "model_name" in payload or not partial:
        model_name = str(payload.get("model_name", "")).strip()
        if len(model_name) > LLM_MODEL_NAME_MAX_LENGTH:
            return None, f"model_name cannot exceed {LLM_MODEL_NAME_MAX_LENGTH} characters."
        cleaned["model_name"] = model_name

    return cleaned, None


def validate_vision_config(payload, *, partial=False):
    if not isinstance(payload, dict):
        return None, "Configuration must be a JSON object."
    value = dict(payload) if partial else {**DEFAULT_VISION_CONFIG, **payload}
    if isinstance(payload.get('prompt'), dict):
        for source, target in (('system', 'system_prompt'), ('user', 'user_prompt')):
            if source in payload['prompt']:
                value[target] = payload['prompt'][source]
    prompt, error = validate_prompt_config(value, partial=partial, include_enabled=True)
    if error:
        return None, error
    llm, error = validate_llm_config(value, partial=partial)
    return (None, error) if error else ({**prompt, **llm}, None)


def merge_llm_config(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(base)
    if not override:
        return merged
    for key in ("base_url", "model_name"):
        value = str(override.get(key, "")).strip() if key in override else ""
        if value:
            merged[key] = value
    return merged


def compute_prompt_hash(prompt_config: dict[str, Any]) -> str:
    stable = {
        "system_prompt": str(prompt_config.get("system_prompt") or ""),
        "user_prompt": str(prompt_config.get("user_prompt") or ""),
        "temperature": float(prompt_config.get("temperature", DEFAULT_PROMPT_CONFIG["temperature"])),
        "tags_limit": int(prompt_config.get("tags_limit", DEFAULT_PROMPT_CONFIG["tags_limit"])),
    }
    encoded = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


class CaptionConfigStore:
    """The two existing editable profiles retain their on-disk formats."""
    def __init__(self, path: Path, kind: str):
        self.path, self.kind = path, kind
        path.parent.mkdir(parents=True, exist_ok=True)

    def validate(self, value):
        if self.kind == 'prompt':
            return validate_prompt_config(value, include_enabled=True)
        return validate_llm_config(value)

    def get(self):
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None
        validated, error = self.validate(data)
        if error:
            return None
        if isinstance(data.get('updated_at'), str):
            validated['updated_at'] = data['updated_at']
        return validated

    def set(self, value):
        payload = {**value, 'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        write_json_atomic(self.path, payload)

    def reset(self):
        self.path.unlink(missing_ok=True)


def caption_api_key() -> str:
    return next((value for name in (
        'TIKLOCAL_VISION_API_KEY', 'TIKLOCAL_AI_API_KEY', 'OPENAI_API_KEY', 'OPENROUTER_API_KEY',
    ) if (value := os.environ.get(name, '').strip())), '')


class CaptionSettings:
    def __init__(self, vision_config, prompt_path: Path, llm_path: Path):
        self.vision_config = vision_config
        self.profiles = {
            'prompt': CaptionConfigStore(prompt_path, 'prompt'),
            'llm': CaptionConfigStore(llm_path, 'llm'),
        }

    def resolve(self, override=None) -> dict:
        """Resolve once for both configuration display and execution, without exposing secrets."""
        prompt_default = get_default_prompt_config()
        prompt_default.pop('enabled')
        prompt_custom = self.profiles['prompt'].get()
        prompt_profile = 'custom' if prompt_custom and prompt_custom.get('enabled') else 'default'
        llm_default = {
            'base_url': os.environ.get('TIKLOCAL_LLM_BASE_URL', '').strip(),
            'model_name': os.environ.get('TIKLOCAL_LLM_MODEL', '').strip(),
        }
        llm_custom = self.profiles['llm'].get()
        llm_effective = merge_llm_config(llm_default, llm_custom)
        llm_profile = 'custom' if llm_custom and any(llm_custom.get(k) for k in llm_default) else 'default'
        vision_default = {
            **get_default_vision_config(),
            'base_url': os.environ.get('TIKLOCAL_VISION_BASE_URL', '').strip(),
            'model_name': os.environ.get('TIKLOCAL_VISION_MODEL', '').strip(),
        }
        file_config, error = validate_vision_config(self.vision_config or {}, partial=True)
        file_config = {} if error else file_config
        effective = merge_vision_config(vision_default, file_config)
        prompt_source = 'config' if file_config else 'default'
        if not file_config and prompt_profile == 'custom':
            effective.update({key: prompt_custom[key] for key in prompt_default})
            prompt_source = 'custom'
        if override:
            effective.update(override)
            prompt_source = 'override'
        llm_source = llm_profile
        if effective['model_name'] or effective['base_url']:
            # Preserve the existing vision -> legacy environment fallback, not custom LLM.
            for key in llm_default:
                effective[key] = effective[key] or llm_default[key]
            llm_source = 'config'
        else:
            effective.update(llm_effective)
        has_key = bool(caption_api_key())
        return {
            'prompt': {'active_profile': prompt_profile, 'custom': prompt_custom, 'default': prompt_default},
            'llm': {'active_profile': llm_profile, 'custom': llm_custom, 'default': llm_default,
                    'effective': llm_effective, 'has_api_key': has_key},
            'vision': {'active_profile': 'config' if file_config else 'default',
                       'default': vision_default, 'config': file_config, 'effective': effective,
                       'prompt_source': prompt_source, 'llm_source': llm_source, 'has_api_key': has_key},
        }


def generate_caption(image_path: Path, resolved: dict) -> dict:
    effective = resolved['effective']
    prompt = {key: effective[key] for key in ('system_prompt', 'user_prompt', 'temperature', 'tags_limit')}
    service = CaptionService(model=effective['model_name'], base_url=effective['base_url'], api_key=caption_api_key())
    result = service.generate(image_path, prompt_config=prompt)
    return {**result, 'prompt_source': resolved['prompt_source'], 'llm_source': resolved['llm_source']}


class CaptionService:
    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str,
    ):
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured.")
        if not self.model:
            raise RuntimeError("TIKLOCAL_LLM_MODEL is not configured.")
        if self.base_url and "openrouter.ai" in self.base_url and "/api/v1" not in self.base_url:
            raise RuntimeError("base_url must include the full API path, such as https://openrouter.ai/api/v1")

    def generate(
        self,
        image_path: Path,
        prompt_config: dict[str, Any],
    ) -> dict[str, Any]:
        data_url = self._to_data_url(image_path)

        effective_prompt = prompt_config

        tags_limit = int(effective_prompt["tags_limit"])
        temperature = float(effective_prompt["temperature"])
        system_prompt = str(effective_prompt["system_prompt"])
        user_prompt = self._render_user_prompt(str(effective_prompt["user_prompt"]), tags_limit)
        if not system_prompt.strip() or not user_prompt.strip():
            raise RuntimeError("Configure the vision prompt first, or provide a prompt override for this request.")

        text = self._request_chat_completion(system_prompt, user_prompt, data_url, temperature)
        if self._looks_like_html(text):
            raise RuntimeError("The model returned an HTML page. Check base_url and model.")

        parsed = self._parse_output(text, tags_limit)
        if not parsed['title'] and not parsed['tags']:
            raise RuntimeError('The model returned neither a title nor tags.')

        return {
            "title": parsed.get("title", ""),
            "tags": parsed.get("tags", []),
            "style": "first_person_emotion_zh",
            "model": self.model,
            "provider": "openai",
            "base_url": self.base_url or "",
            "created_at": datetime.datetime.utcnow().isoformat() + "Z",
            "prompt_version": PROMPT_TEMPLATE_VERSION,
            "prompt_hash": compute_prompt_hash(effective_prompt),
        }

    def _render_user_prompt(self, template: str, tags_limit: int) -> str:
        rendered = template.replace("{{tags_limit}}", str(tags_limit))
        return rendered.replace("{tags_limit}", str(tags_limit))

    def _to_data_url(self, image_path: Path, max_size: int = 1536, quality: int = 85) -> str:
        """Convert an image to a compressed base64 data URL to reduce token use.

        Args:
            image_path: Image file path.
            max_size: Maximum size of the longest edge, 1536px by default.
            quality: JPEG quality from 1 to 100, 85 by default.

        Returns:
            The compressed base64 data URL.
        """
        with Image.open(image_path) as img:
            # Convert RGBA, grayscale, and other modes to RGB.
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            # Resize if needed.
            width, height = img.size
            if max(width, height) > max_size:
                ratio = max_size / max(width, height)
                new_size = (int(width * ratio), int(height * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)

            # Encode as JPEG.
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=quality, optimize=True)
            encoded = base64.b64encode(buffer.getvalue()).decode("ascii")

        return f"data:image/jpeg;base64,{encoded}"

    def _request_chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        data_url: str,
        temperature: float,
    ) -> str:
        base_url = (self.base_url or "https://api.openai.com/v1").rstrip("/")
        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
        }
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        text = response.text or ""
        if response.status_code >= 400:
            raise RuntimeError(self._parse_error(text) or f"HTTP {response.status_code}")

        if self._looks_like_html(text):
            return text
        try:
            data = response.json()
        except Exception:
            return text

        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError(self._parse_error(data) or "API error")

        return self._extract_text_from_json(data)

    def _extract_text_from_json(self, data: Any) -> str:
        if not isinstance(data, dict):
            return ""
        choices = data.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            content = message.get("content")
            if isinstance(content, str):
                return content
        return ""

    def _parse_error(self, data: Any) -> str:
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                return data.strip()
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict):
                return err.get("message") or ""
            if isinstance(err, str):
                return err
        return ""

    def _looks_like_html(self, text: str) -> bool:
        if not text:
            return False
        lowered = text.lstrip().lower()
        head = lowered[:400]
        if lowered.startswith("<!doctype") or lowered.startswith("<html"):
            return True
        return "<html" in head or "<head" in head or "<body" in head

    def _parse_output(self, text: str, tags_limit: int) -> dict[str, Any]:
        data = None
        try:
            data = json.loads(text)
        except Exception:
            match = re.search(r"\{.*\}", text, re.S)
            if match:
                try:
                    data = json.loads(match.group(0))
                except Exception:
                    data = None

        title = ""
        tags: list[str] = []

        if isinstance(data, dict):
            title = str(data.get("title") or data.get("caption") or "").strip()
            tags = data.get("tags") or []
        else:
            title = text.strip().splitlines()[0] if text.strip() else ""

        if isinstance(tags, str):
            tags = re.split(r"[,;/\n]+", tags)
        if isinstance(tags, list):
            tags = [str(t).strip() for t in tags if str(t).strip()]
        else:
            tags = []

        # De-dup and clamp
        seen = set()
        cleaned = []
        for tag in tags:
            if tag in seen:
                continue
            seen.add(tag)
            cleaned.append(tag)
            if len(cleaned) >= tags_limit:
                break

        return {"title": title, "tags": cleaned}
