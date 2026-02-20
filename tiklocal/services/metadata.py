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


PROMPT_TEMPLATE_VERSION = 2
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
        "你是我的私人媒体库助手，风格自然、真实、有轻微情绪起伏。"
        "只根据图片可见信息，不要臆测地点、人物身份或具体事件。"
        "输出必须是严格 JSON，不要包含多余文字。"
    ),
    "user_prompt": (
        "这是一张我从社交媒体保存的图片。"
        "请用中文、第一人称、带情绪的一句话给出图片标题。"
        "请给出 1 到 {tags_limit} 个标签。"
        "风格要求：更口语、更生活化，避免模板句；"
        "语气可以轻微变化（偶尔克制、偶尔感慨、偶尔俏皮）。"
        "不确定的信息不要写，避免具体人名/地名/时间。"
        "标签用简短词语，不要带 #，允许情绪词。"
        "输出格式：{\"title\": \"...\", \"tags\": [\"...\", \"...\"]}。"
    ),
    "temperature": 0.6,
    "tags_limit": 5,
    "enabled": True,
}

DEFAULT_LLM_CONFIG = {
    "base_url": "",
    "model_name": "",
}


def get_default_prompt_config() -> dict[str, Any]:
    return dict(DEFAULT_PROMPT_CONFIG)


def get_default_llm_config() -> dict[str, Any]:
    return dict(DEFAULT_LLM_CONFIG)


def merge_prompt_config(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(base)
    if not override:
        return merged
    for key in ("system_prompt", "user_prompt", "temperature", "tags_limit", "enabled"):
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
        return None, "配置格式必须是 JSON 对象。"

    cleaned: dict[str, Any] = {}

    def _read_text(field: str, max_length: int) -> tuple[str | None, str | None]:
        if field not in payload:
            if partial:
                return None, None
            return None, f"缺少字段: {field}"
        value = str(payload.get(field, "")).strip()
        if not value:
            return None, f"{field} 不能为空。"
        if len(value) > max_length:
            return None, f"{field} 不能超过 {max_length} 个字符。"
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
            return None, "temperature 必须是数字。"
        if not (PROMPT_TEMPERATURE_MIN <= temperature <= PROMPT_TEMPERATURE_MAX):
            return None, f"temperature 必须在 {PROMPT_TEMPERATURE_MIN} 到 {PROMPT_TEMPERATURE_MAX} 之间。"
        cleaned["temperature"] = temperature
    elif not partial:
        cleaned["temperature"] = float(DEFAULT_PROMPT_CONFIG["temperature"])

    if "tags_limit" in payload:
        try:
            tags_limit = int(payload["tags_limit"])
        except (TypeError, ValueError):
            return None, "tags_limit 必须是整数。"
        if not (PROMPT_TAGS_MIN <= tags_limit <= PROMPT_TAGS_MAX):
            return None, f"tags_limit 必须在 {PROMPT_TAGS_MIN} 到 {PROMPT_TAGS_MAX} 之间。"
        cleaned["tags_limit"] = tags_limit
    elif not partial:
        cleaned["tags_limit"] = int(DEFAULT_PROMPT_CONFIG["tags_limit"])

    if include_enabled:
        if "enabled" in payload:
            value = payload["enabled"]
            if not isinstance(value, bool):
                return None, "enabled 必须是布尔值。"
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
        return None, "配置格式必须是 JSON 对象。"

    cleaned: dict[str, Any] = {}

    if "base_url" in payload or not partial:
        base_url = str(payload.get("base_url", "")).strip()
        if len(base_url) > LLM_BASE_URL_MAX_LENGTH:
            return None, f"base_url 不能超过 {LLM_BASE_URL_MAX_LENGTH} 个字符。"
        if base_url and not (base_url.startswith("http://") or base_url.startswith("https://")):
            return None, "base_url 必须以 http:// 或 https:// 开头。"
        cleaned["base_url"] = base_url

    if "model_name" in payload or not partial:
        model_name = str(payload.get("model_name", "")).strip()
        if len(model_name) > LLM_MODEL_NAME_MAX_LENGTH:
            return None, f"model_name 不能超过 {LLM_MODEL_NAME_MAX_LENGTH} 个字符。"
        cleaned["model_name"] = model_name

    return cleaned, None


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


class ImageMetadataStore:
    def __init__(self, store_path: Path):
        self.store_path = store_path
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, Any]:
        if not self.store_path.exists():
            return {}
        try:
            with self.store_path.open('r', encoding='utf-8') as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def get(self, key: str) -> dict[str, Any] | None:
        return self._load().get(key)

    def set(self, key: str, value: dict[str, Any], overwrite: bool = True) -> tuple[dict[str, Any], bool]:
        data = self._load()
        if not overwrite and key in data:
            return data[key], False
        data[key] = value
        self._write(data)
        return value, True

    def _write(self, data: dict[str, Any]) -> None:
        tmp_path = self.store_path.with_name(self.store_path.name + ".tmp")
        with tmp_path.open('w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.store_path)


class PromptConfigStore:
    def __init__(self, store_path: Path):
        self.store_path = store_path
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, Any]:
        if not self.store_path.exists():
            return {}
        try:
            with self.store_path.open('r', encoding='utf-8') as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def get(self) -> dict[str, Any] | None:
        data = self._load()
        if not data:
            return None
        validated, error = validate_prompt_config(data, partial=False, include_enabled=True)
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
        with tmp_path.open('w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.store_path)


class LLMConfigStore:
    def __init__(self, store_path: Path):
        self.store_path = store_path
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, Any]:
        if not self.store_path.exists():
            return {}
        try:
            with self.store_path.open('r', encoding='utf-8') as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def get(self) -> dict[str, Any] | None:
        data = self._load()
        if not data:
            return None
        validated, error = validate_llm_config(data, partial=False)
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
        with tmp_path.open('w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.store_path)


class CaptionService:
    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
    ):
        self.model = model or os.environ.get('TIKLOCAL_LLM_MODEL')
        self.base_url = base_url or os.environ.get('TIKLOCAL_LLM_BASE_URL')
        self.api_key = api_key or os.environ.get('OPENAI_API_KEY')
        if not self.api_key:
            raise RuntimeError("未配置 OPENAI_API_KEY。")
        if not self.model:
            raise RuntimeError("未配置 TIKLOCAL_LLM_MODEL。")
        if self.base_url and "openrouter.ai" in self.base_url and "/api/v1" not in self.base_url:
            raise RuntimeError("OpenRouter base_url 需要包含 /api/v1，例如 https://openrouter.ai/api/v1")

    def generate(
        self,
        image_path: Path,
        tags_limit: int = 5,
        prompt_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data_url = self._to_data_url(image_path)

        effective_prompt = get_default_prompt_config()
        effective_prompt["tags_limit"] = int(tags_limit)
        effective_prompt = merge_prompt_config(effective_prompt, prompt_config)

        tags_limit = int(effective_prompt["tags_limit"])
        temperature = float(effective_prompt["temperature"])
        system_prompt = str(effective_prompt["system_prompt"])
        user_prompt = self._render_user_prompt(str(effective_prompt["user_prompt"]), tags_limit)

        text = self._request_chat_completion(system_prompt, user_prompt, data_url, temperature)
        if self._looks_like_html(text):
            raise RuntimeError("模型返回了 HTML 页面，请检查 base_url 或 model 是否正确。")

        parsed = self._parse_output(text, tags_limit)

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
        """将图片转换为 base64 data URL，自动压缩以减少 token 消耗。

        Args:
            image_path: 图片文件路径
            max_size: 最长边最大像素，默认 1536px
            quality: JPEG 质量 (1-100)，默认 85

        Returns:
            压缩后的 base64 data URL
        """
        with Image.open(image_path) as img:
            # 转换为 RGB（处理 RGBA、灰度等格式）
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            # 调整尺寸
            width, height = img.size
            if max(width, height) > max_size:
                ratio = max_size / max(width, height)
                new_size = (int(width * ratio), int(height * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)

            # 压缩为 JPEG
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
        if not title:
            title = text.strip().splitlines()[0] if text.strip() else ""

        if isinstance(tags, str):
            tags = re.split(r"[，,;/\n]+", tags)
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
