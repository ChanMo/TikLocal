import base64
import datetime
import io
import json
import math
import os
from array import array
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageOps

from tiklocal.services.database import AppDatabase


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
        return None, "配置格式必须是 JSON 对象。"

    cleaned: dict[str, Any] = {}

    if "enabled" in payload:
        if not isinstance(payload["enabled"], bool):
            return None, "enabled 必须是布尔值。"
        cleaned["enabled"] = payload["enabled"]
    elif not partial:
        cleaned["enabled"] = bool(DEFAULT_EMBEDDING_CONFIG["enabled"])

    if "base_url" in payload or not partial:
        base_url = str(payload.get("base_url", DEFAULT_EMBEDDING_CONFIG["base_url"])).strip()
        if len(base_url) > EMBEDDING_BASE_URL_MAX_LENGTH:
            return None, f"base_url 不能超过 {EMBEDDING_BASE_URL_MAX_LENGTH} 个字符。"
        if base_url and not (base_url.startswith("http://") or base_url.startswith("https://")):
            return None, "base_url 必须以 http:// 或 https:// 开头。"
        cleaned["base_url"] = base_url

    if "model_name" in payload or not partial:
        model_name = str(payload.get("model_name", DEFAULT_EMBEDDING_CONFIG["model_name"])).strip()
        if len(model_name) > EMBEDDING_MODEL_NAME_MAX_LENGTH:
            return None, f"model_name 不能超过 {EMBEDDING_MODEL_NAME_MAX_LENGTH} 个字符。"
        cleaned["model_name"] = model_name

    if "dimensions" in payload or not partial:
        try:
            dimensions = int(payload.get("dimensions", DEFAULT_EMBEDDING_CONFIG["dimensions"]))
        except (TypeError, ValueError):
            return None, "dimensions 必须是整数。"
        if not (EMBEDDING_DIMENSIONS_MIN <= dimensions <= EMBEDDING_DIMENSIONS_MAX):
            return None, f"dimensions 必须在 {EMBEDDING_DIMENSIONS_MIN} 到 {EMBEDDING_DIMENSIONS_MAX} 之间。"
        cleaned["dimensions"] = dimensions

    if "image_max_size" in payload or not partial:
        try:
            image_max_size = int(payload.get("image_max_size", DEFAULT_EMBEDDING_CONFIG["image_max_size"]))
        except (TypeError, ValueError):
            return None, "image_max_size 必须是整数。"
        if not (EMBEDDING_IMAGE_MAX_SIZE_MIN <= image_max_size <= EMBEDDING_IMAGE_MAX_SIZE_MAX):
            return None, f"image_max_size 必须在 {EMBEDDING_IMAGE_MAX_SIZE_MIN} 到 {EMBEDDING_IMAGE_MAX_SIZE_MAX} 之间。"
        cleaned["image_max_size"] = image_max_size

    if "image_quality" in payload or not partial:
        try:
            image_quality = int(payload.get("image_quality", DEFAULT_EMBEDDING_CONFIG["image_quality"]))
        except (TypeError, ValueError):
            return None, "image_quality 必须是整数。"
        if not (EMBEDDING_IMAGE_QUALITY_MIN <= image_quality <= EMBEDDING_IMAGE_QUALITY_MAX):
            return None, f"image_quality 必须在 {EMBEDDING_IMAGE_QUALITY_MIN} 到 {EMBEDDING_IMAGE_QUALITY_MAX} 之间。"
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


class OpenAICompatibleImageEmbeddingClient:
    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        dimensions: int,
        image_max_size: int | None = None,
        image_quality: int | None = None,
        api_key: str | None = None,
        timeout: int = 60,
    ):
        self.model = model
        self.base_url = (base_url or DEFAULT_EMBEDDING_CONFIG["base_url"]).rstrip("/")
        self.dimensions = int(dimensions)
        self.image_max_size = int(image_max_size or DEFAULT_EMBEDDING_CONFIG["image_max_size"])
        self.image_quality = int(image_quality or DEFAULT_EMBEDDING_CONFIG["image_quality"])
        self.api_key = (
            api_key
            or os.environ.get("TIKLOCAL_EMBEDDING_API_KEY")
            or os.environ.get("TIKLOCAL_AI_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("OPENROUTER_API_KEY")
        )
        self.timeout = timeout
        if not self.api_key:
            raise RuntimeError("未配置 TIKLOCAL_EMBEDDING_API_KEY、TIKLOCAL_AI_API_KEY、OPENAI_API_KEY 或 OPENROUTER_API_KEY。")
        if not self.model:
            raise RuntimeError("未配置 embedding model。")

    def embed_image(self, image_path: Path) -> list[float]:
        data_url = self._to_data_url(image_path, max_size=self.image_max_size, quality=self.image_quality)
        payload = {
            "model": self.model,
            "input": [
                {
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            "encoding_format": "float",
            "dimensions": self.dimensions,
        }
        response = requests.post(
            f"{self.base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout,
        )
        text = response.text or ""
        if response.status_code >= 400:
            raise RuntimeError(self._parse_error(text) or f"HTTP {response.status_code}")
        try:
            data = response.json()
        except Exception:
            raise RuntimeError("Embedding API 返回了非 JSON 响应。")
        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError(self._parse_error(data) or "Embedding API error")
        embedding = ((data.get("data") or [{}])[0] or {}).get("embedding") if isinstance(data, dict) else None
        if not isinstance(embedding, list) or not embedding:
            raise RuntimeError("Embedding API 未返回向量。")
        return [float(value) for value in embedding]

    def _to_data_url(self, image_path: Path, max_size: int = 512, quality: int = 82) -> str:
        with Image.open(image_path) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode in ("RGBA", "LA", "P"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")

            width, height = img.size
            if max(width, height) > max_size:
                ratio = max_size / max(width, height)
                img = img.resize((int(width * ratio), int(height * ratio)), Image.Resampling.LANCZOS)

            buffer = io.BytesIO()
            # Save only pixels. Do not pass EXIF/ICC/XMP/IPTC metadata into the JPEG payload.
            img.save(buffer, format="JPEG", quality=quality, optimize=True)
            encoded = base64.b64encode(buffer.getvalue()).decode("ascii")

        return f"data:image/jpeg;base64,{encoded}"

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


class SQLiteImageVectorStore:
    def __init__(self, database: AppDatabase):
        self.database = database

    def is_available(self) -> bool:
        return True

    def get_all_metadata(self) -> dict[str, dict[str, Any]]:
        with self.database.connect() as conn:
            rows = conn.execute("SELECT * FROM image_vectors").fetchall()
        return {str(row["uri"]): self._row_metadata(row) for row in rows}

    def get_metadata(self, uri: str) -> dict[str, Any] | None:
        with self.database.connect() as conn:
            row = conn.execute("SELECT * FROM image_vectors WHERE uri = ?", (uri,)).fetchone()
        return self._row_metadata(row) if row else None

    def upsert_image(
        self,
        *,
        uri: str,
        embedding: list[float],
        metadata: dict[str, Any],
    ) -> None:
        blob = self._embedding_to_blob(embedding)
        norm = self._embedding_norm(embedding)
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO image_vectors (
                  uri, source_id, rel_path, model, dimensions, image_max_size, image_quality,
                  mtime, size_bytes, embedding, embedding_norm, indexed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(uri) DO UPDATE SET
                  source_id = excluded.source_id,
                  rel_path = excluded.rel_path,
                  model = excluded.model,
                  dimensions = excluded.dimensions,
                  image_max_size = excluded.image_max_size,
                  image_quality = excluded.image_quality,
                  mtime = excluded.mtime,
                  size_bytes = excluded.size_bytes,
                  embedding = excluded.embedding,
                  embedding_norm = excluded.embedding_norm,
                  indexed_at = excluded.indexed_at
                """,
                (
                    uri,
                    str(metadata.get("source_id") or ""),
                    str(metadata.get("rel_path") or ""),
                    str(metadata.get("model") or ""),
                    int(metadata.get("dimensions") or 0),
                    int(metadata.get("image_max_size") or 0),
                    int(metadata.get("image_quality") or 0),
                    float(metadata.get("mtime") or 0),
                    int(metadata.get("size_bytes") or 0),
                    blob,
                    norm,
                    str(metadata.get("indexed_at") or ""),
                ),
            )

    def delete(self, ids: list[str]) -> None:
        if not ids:
            return
        with self.database.connect() as conn:
            conn.executemany("DELETE FROM image_vectors WHERE uri = ?", [(item_id,) for item_id in ids])

    def query_similar(self, uri: str, *, limit: int = 12) -> list[dict[str, Any]]:
        with self.database.connect() as conn:
            query_row = conn.execute("SELECT * FROM image_vectors WHERE uri = ?", (uri,)).fetchone()
            if not query_row:
                return []
            query_embedding = self._blob_to_embedding(query_row["embedding"])
            query_norm = float(query_row["embedding_norm"] or 0)
            rows = conn.execute(
                """
                SELECT * FROM image_vectors
                WHERE uri != ? AND model = ? AND dimensions = ?
                """,
                (uri, query_row["model"], int(query_row["dimensions"])),
            ).fetchall()

        if query_norm <= 0:
            return []
        scored: list[dict[str, Any]] = []
        for row in rows:
            candidate_embedding = self._blob_to_embedding(row["embedding"])
            candidate_norm = float(row["embedding_norm"] or 0)
            if candidate_norm <= 0:
                continue
            score = self._cosine_similarity(query_embedding, query_norm, candidate_embedding, candidate_norm)
            scored.append({
                "uri": str(row["uri"]),
                "metadata": self._row_metadata(row),
                "distance": float(1.0 - score),
            })
        scored.sort(key=lambda item: float(item.get("distance") or 0))
        return scored[:limit]

    def list_vectors(self, *, limit: int = 1000) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 5000))
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM image_vectors
                ORDER BY mtime DESC, uri ASC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [
            {
                "uri": str(row["uri"]),
                "embedding": self._blob_to_embedding(row["embedding"]),
                "embedding_norm": float(row["embedding_norm"] or 0),
                "metadata": self._row_metadata(row),
            }
            for row in rows
        ]

    def _row_metadata(self, row) -> dict[str, Any]:
        return {
            "uri": str(row["uri"]),
            "source_id": str(row["source_id"]),
            "rel_path": str(row["rel_path"]),
            "media_type": "image",
            "mtime": float(row["mtime"]),
            "size_bytes": int(row["size_bytes"]),
            "model": str(row["model"]),
            "dimensions": int(row["dimensions"]),
            "image_max_size": int(row["image_max_size"]),
            "image_quality": int(row["image_quality"]),
            "input_kind": "image",
            "indexed_at": str(row["indexed_at"]),
        }

    def _embedding_to_blob(self, embedding: list[float]) -> bytes:
        return array("f", [float(value) for value in embedding]).tobytes()

    def _blob_to_embedding(self, blob: bytes) -> array:
        values = array("f")
        values.frombytes(blob)
        return values

    def _embedding_norm(self, embedding: list[float]) -> float:
        return math.sqrt(sum(float(value) * float(value) for value in embedding))

    def _cosine_similarity(self, query_embedding, query_norm: float, candidate_embedding, candidate_norm: float) -> float:
        if len(query_embedding) != len(candidate_embedding):
            return -1.0
        dot = sum(float(left) * float(right) for left, right in zip(query_embedding, candidate_embedding))
        return dot / (query_norm * candidate_norm)


class ImageVectorService:
    def __init__(self, library_service, vector_index):
        self.library_service = library_service
        self.vector_index = vector_index

    def build_image_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for path in self.library_service.scan_images():
            try:
                uri = self.library_service.get_relative_path(path)
                stat = path.stat()
                source = self.library_service.source_for_uri(uri)
                records.append({
                    "uri": uri,
                    "path": path,
                    "mtime": float(stat.st_mtime),
                    "size_bytes": int(stat.st_size),
                    "source_id": source.id if source else "",
                    "rel_path": self.library_service.relative_path_for_uri(uri),
                })
            except Exception:
                continue
        return records

    def is_stale(self, record: dict[str, Any], metadata: dict[str, Any] | None, config: dict[str, Any]) -> bool:
        if not metadata:
            return True
        return not (
            str(metadata.get("model") or "") == str(config.get("model_name") or "")
            and int(metadata.get("dimensions") or 0) == int(config.get("dimensions") or 0)
            and int(metadata.get("image_max_size") or 0) == int(config.get("image_max_size") or 0)
            and int(metadata.get("image_quality") or 0) == int(config.get("image_quality") or 0)
            and float(metadata.get("mtime") or 0) == float(record.get("mtime") or 0)
            and int(metadata.get("size_bytes") or 0) == int(record.get("size_bytes") or 0)
        )

    def plan_records(
        self,
        *,
        config: dict[str, Any],
        limit: int = 0,
        order: str = "latest",
        source_id: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        records = self.build_image_records()
        if source_id:
            records = [record for record in records if str(record.get("source_id") or "") == source_id]

        if order == "oldest":
            records.sort(key=lambda item: (float(item.get("mtime") or 0), str(item.get("uri") or "")))
        elif order == "path":
            records.sort(key=lambda item: str(item.get("uri") or ""))
        else:
            records.sort(key=lambda item: (float(item.get("mtime") or 0), str(item.get("uri") or "")), reverse=True)

        metadata_by_id = self.vector_index.get_all_metadata()
        missing = 0
        stale = 0
        current = 0
        selected: list[dict[str, Any]] = []
        for record in records:
            uri = str(record["uri"])
            metadata = metadata_by_id.get(uri)
            needs_index = force or self.is_stale(record, metadata, config)
            if metadata is None:
                missing += 1
            elif self.is_stale(record, metadata, config):
                stale += 1
            else:
                current += 1
            if needs_index and (limit <= 0 or len(selected) < limit):
                selected.append(record)

        return {
            "records": records,
            "selected": selected,
            "total_images": len(records),
            "indexed_current": current,
            "missing": missing,
            "stale": stale,
            "selected_count": len(selected),
            "order": order,
            "limit": int(limit),
            "source_id": source_id or "",
            "force": bool(force),
        }

    def status(self, config: dict[str, Any]) -> dict[str, Any]:
        records = self.build_image_records()
        metadata_by_id = self.vector_index.get_all_metadata()
        valid_uris = {str(item["uri"]) for item in records}
        indexed = 0
        stale = 0
        missing = 0
        for record in records:
            metadata = metadata_by_id.get(str(record["uri"]))
            if metadata is None:
                missing += 1
            elif self.is_stale(record, metadata, config):
                stale += 1
            else:
                indexed += 1
        orphaned = len([uri for uri in metadata_by_id if uri not in valid_uris])
        return {
            "available": True,
            "total_images": len(records),
            "indexed": indexed,
            "stale": stale,
            "missing": missing,
            "orphaned": orphaned,
            "model": config.get("model_name") or "",
            "dimensions": int(config.get("dimensions") or 0),
        }

    def index_missing_or_stale(
        self,
        *,
        config: dict[str, Any],
        client: OpenAICompatibleImageEmbeddingClient,
        limit: int = 0,
        order: str = "latest",
        source_id: str | None = None,
        force: bool = False,
        progress_callback=None,
    ) -> dict[str, Any]:
        plan = self.plan_records(
            config=config,
            limit=limit,
            order=order,
            source_id=source_id,
            force=force,
        )
        records = plan["selected"]
        processed = 0
        indexed = 0
        failed = 0
        errors: list[dict[str, str]] = []
        for index, record in enumerate(records, start=1):
            uri = str(record["uri"])
            processed += 1
            try:
                self.index_record(record, config=config, client=client)
                indexed += 1
                if progress_callback:
                    progress_callback(index, len(records), record, "indexed", "")
            except Exception as exc:
                failed += 1
                if len(errors) < 20:
                    errors.append({"uri": uri, "error": str(exc)})
                if progress_callback:
                    progress_callback(index, len(records), record, "failed", str(exc))
        return {
            "total_images": plan["total_images"],
            "processed": processed,
            "indexed": indexed,
            "skipped": 0,
            "failed": failed,
            "errors": errors,
            "plan": {
                key: value
                for key, value in plan.items()
                if key not in {"records", "selected"}
            },
        }

    def index_record(
        self,
        record: dict[str, Any],
        *,
        config: dict[str, Any],
        client: OpenAICompatibleImageEmbeddingClient,
    ) -> None:
        uri = str(record["uri"])
        embedding = client.embed_image(Path(record["path"]))
        metadata = {
            "uri": uri,
            "source_id": str(record.get("source_id") or ""),
            "rel_path": str(record.get("rel_path") or ""),
            "media_type": "image",
            "mtime": float(record.get("mtime") or 0),
            "size_bytes": int(record.get("size_bytes") or 0),
            "model": str(config.get("model_name") or ""),
            "dimensions": int(config.get("dimensions") or 0),
            "image_max_size": int(config.get("image_max_size") or 0),
            "image_quality": int(config.get("image_quality") or 0),
            "input_kind": "image",
            "indexed_at": datetime.datetime.utcnow().isoformat() + "Z",
        }
        self.vector_index.upsert_image(uri=uri, embedding=embedding, metadata=metadata)

    def cleanup_missing(self) -> dict[str, Any]:
        records = self.build_image_records()
        valid_uris = {str(item["uri"]) for item in records}
        metadata_by_id = self.vector_index.get_all_metadata()
        orphaned = [uri for uri in metadata_by_id if uri not in valid_uris]
        self.vector_index.delete(orphaned)
        return {"deleted": len(orphaned)}
