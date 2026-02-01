import base64
import datetime
import json
import mimetypes
import os
import re
from pathlib import Path
from typing import Any

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - handled at runtime
    OpenAI = None


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


class CaptionService:
    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        api_mode: str | None = None,
    ):
        self.model = model or os.environ.get('TIKLOCAL_LLM_MODEL')
        self.base_url = base_url or os.environ.get('TIKLOCAL_LLM_BASE_URL')
        self.api_key = api_key or os.environ.get('OPENAI_API_KEY')
        self.api_mode = (api_mode or os.environ.get('TIKLOCAL_LLM_API') or 'auto').lower()
        self._client = None

    def _get_client(self):
        if OpenAI is None:
            raise RuntimeError("OpenAI 客户端未安装，请先安装 openai 依赖。")
        if not self.api_key:
            raise RuntimeError("未配置 OPENAI_API_KEY。")
        if not self.model:
            raise RuntimeError("未配置 TIKLOCAL_LLM_MODEL。")
        if self.base_url and "openrouter.ai" in self.base_url and "/api/v1" not in self.base_url:
            raise RuntimeError("OpenRouter base_url 需要包含 /api/v1，例如 https://openrouter.ai/api/v1")
        if self._client is None:
            kwargs = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = OpenAI(**kwargs)
        return self._client

    def generate(self, image_path: Path, tags_limit: int = 5) -> dict[str, Any]:
        data_url = self._to_data_url(image_path)
        client = self._get_client()

        system_prompt = (
            "你是我的私人媒体库助手。"
            "请仅基于图片可见信息，不要臆测地点、人物或事件。"
            "输出必须是严格 JSON。"
        )
        user_prompt = (
            "这是一张我从社交媒体保存的图片。"
            "请用中文、第一人称、带情绪的一句话给出图片标题，"
            f"并给出 1 到 {tags_limit} 个标签。"
            "标签用简短词语，不要带 #。"
            "输出格式：{\"title\": \"...\", \"tags\": [\"...\", \"...\"]}。"
        )

        api_mode = self._resolve_api_mode()
        text = ""
        if api_mode == "chat":
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    },
                ],
                temperature=0.6,
            )
            text = self._extract_text(response)
        else:
            try:
                response = client.responses.create(
                    model=self.model,
                    instructions=system_prompt,
                    input=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": user_prompt},
                                {"type": "input_image", "image_url": data_url},
                            ],
                        }
                    ],
                    temperature=0.6,
                )
                text = self._extract_text(response)
            except Exception:
                # Fallback for OpenAI-compatible providers without Responses API
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": user_prompt},
                                {"type": "image_url", "image_url": {"url": data_url}},
                            ],
                        },
                    ],
                    temperature=0.6,
                )
                text = self._extract_text(response)
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
            "prompt_version": 1,
        }

    def _to_data_url(self, image_path: Path) -> str:
        mime, _ = mimetypes.guess_type(image_path.name)
        mime = mime or "image/jpeg"
        with image_path.open("rb") as f:
            encoded = base64.b64encode(f.read()).decode("ascii")
        return f"data:{mime};base64,{encoded}"

    def _extract_text(self, response: Any) -> str:
        if isinstance(response, str):
            return response
        if hasattr(response, "output_text"):
            return response.output_text or ""
        if hasattr(response, "choices"):
            try:
                message = response.choices[0].message
                return message.content or ""
            except Exception:
                return ""
        if isinstance(response, dict):
            if response.get("output_text"):
                return response.get("output_text") or ""
            if response.get("choices"):
                message = response["choices"][0].get("message", {})
                return message.get("content") or ""
        return ""

    def _resolve_api_mode(self) -> str:
        if self.api_mode in ("chat", "responses"):
            return self.api_mode
        if not self.base_url:
            return "responses"
        base = self.base_url.lower()
        if "openai.com" in base:
            return "responses"
        return "chat"

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
