"""Where a downloaded file came from: the recorded source map and fallbacks."""
import datetime
import json
import os
import re
import threading
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

SOURCE_MAP_VERSION = 1

_TRACKING_QUERY_KEYS = {"fbclid", "gclid", "igshid"}
_OLD_TEMPLATE_ID_RE = re.compile(r"\[(?P<id>[^\]]+)\]")


def utc_now_iso() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def normalize_file_rel(value: str) -> str:
    text = str(value or "").strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def derive_source_domain(url: str) -> str:
    parsed = urlparse(url)
    return (parsed.hostname or "").strip().lower()


def strip_tracking_query(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return url
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    filtered = []
    for key, value in pairs:
        lowered = key.lower()
        if lowered.startswith("utm_"):
            continue
        if lowered in _TRACKING_QUERY_KEYS:
            continue
        filtered.append((key, value))
    cleaned = parsed._replace(query=urlencode(filtered, doseq=True), fragment="")
    return urlunparse(cleaned)


def normalize_source_meta(meta: dict[str, Any], *, resolved_by: str | None = None) -> dict[str, Any] | None:
    raw = str(meta.get("source_url_raw") or "").strip()
    display = str(meta.get("source_url_display") or "").strip()
    if not raw and not display:
        return None

    raw = raw or display
    display = display or strip_tracking_query(raw)
    domain = str(meta.get("source_domain") or "").strip().lower() or derive_source_domain(raw)
    payload = {
        "source_url_raw": raw,
        "source_url_display": display,
        "source_domain": domain,
        "engine": str(meta.get("engine") or "").strip(),
        "job_id": str(meta.get("job_id") or "").strip(),
        "created_at": str(meta.get("created_at") or utc_now_iso()).strip(),
    }
    if resolved_by:
        payload["resolved_by"] = resolved_by
    payload["url"] = payload["source_url_display"] or payload["source_url_raw"]
    return payload


def source_meta_for_url(raw_url: str, *, resolved_by: str, **fields: Any) -> dict[str, Any] | None:
    """Build source metadata for a page URL, hiding tracking parameters."""
    return normalize_source_meta({
        "source_url_raw": raw_url,
        "source_url_display": strip_tracking_query(raw_url),
        "source_domain": derive_source_domain(raw_url),
        **fields,
    }, resolved_by=resolved_by)


def source_from_info_json(media_file: Path) -> dict[str, Any] | None:
    """Read the page URL yt-dlp wrote next to the media file."""
    for path in (media_file.with_suffix(".info.json"), Path(str(media_file) + ".info.json")):
        if not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for field in ("webpage_url", "original_url", "url"):
            raw_url = str(data.get(field) or "").strip()
            if raw_url:
                return source_meta_for_url(
                    raw_url,
                    resolved_by="infojson",
                    engine=str(data.get("extractor_key") or "").strip(),
                )
        return None
    return None


def _filename_url(extractor: str, uploader_id: str, display_id: str, media_id: str) -> tuple[str, str] | None:
    if extractor in {"twitter", "x"} and display_id:
        if uploader_id:
            return f"https://x.com/{uploader_id}/status/{display_id}", "x.com"
        return f"https://x.com/i/web/status/{display_id}", "x.com"
    if extractor.startswith("youtube") and media_id:
        return f"https://www.youtube.com/watch?v={media_id}", "youtube.com"
    if extractor.startswith("tiktok") and media_id:
        return f"https://www.tiktok.com/@_/video/{media_id}", "tiktok.com"
    if extractor.startswith("instagram") and display_id:
        return f"https://www.instagram.com/p/{display_id}/", "instagram.com"
    return None


def source_from_filename(file_rel: str) -> dict[str, Any] | None:
    """Rebuild the page URL from the yt-dlp output template fields in a filename."""
    name = Path(file_rel).name
    parts = Path(name).stem.split("__")
    found = None
    if len(parts) >= 4:
        fields = ["" if part.strip().lower() == "na" else part.strip() for part in parts[1:4]]
        found = _filename_url(parts[0].strip().lower(), *fields)
    if not found:
        # Older templates put a numeric X status id in brackets.
        old_match = _OLD_TEMPLATE_ID_RE.search(name)
        old_id = old_match.group("id").strip() if old_match else ""
        if old_id.isdigit():
            found = f"https://x.com/i/web/status/{old_id}", "x.com"
    if not found:
        return None
    url, domain = found
    return normalize_source_meta(
        {"source_url_raw": url, "source_url_display": url, "source_domain": domain, "engine": "yt-dlp"},
        resolved_by="filename",
    )


class DownloadSourceStore:
    def __init__(self, store_path: Path):
        self.store_path = store_path
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _read(self) -> dict[str, Any]:
        if not self.store_path.exists():
            return {"version": SOURCE_MAP_VERSION, "items": {}, "updated_at": utc_now_iso()}
        try:
            with self.store_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            return {"version": SOURCE_MAP_VERSION, "items": {}, "updated_at": utc_now_iso()}
        return {"version": SOURCE_MAP_VERSION, "items": {}, "updated_at": utc_now_iso()}

    def _normalized_payload(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = payload if isinstance(payload, dict) else self._read()
        items = data.get("items")
        if not isinstance(items, dict):
            items = {}
        try:
            version = int(data.get("version"))
        except (TypeError, ValueError):
            version = 0
        return {
            "version": version or SOURCE_MAP_VERSION,
            "items": {str(k): v for k, v in items.items() if isinstance(v, dict)},
            "updated_at": str(data.get("updated_at") or utc_now_iso()),
        }

    def _write(self, payload: dict[str, Any]) -> None:
        tmp_path = self.store_path.with_name(self.store_path.name + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.store_path)

    def get(self, file_rel: str) -> dict[str, Any] | None:
        key = normalize_file_rel(file_rel)
        if not key:
            return None
        with self._lock:
            payload = self._normalized_payload()
            value = payload["items"].get(key)
            return dict(value) if isinstance(value, dict) else None

    def get_many(self, file_rels: list[str]) -> dict[str, dict[str, Any] | None]:
        normalized = [normalize_file_rel(item) for item in file_rels]
        normalized = [item for item in normalized if item]
        result: dict[str, dict[str, Any] | None] = {}
        if not normalized:
            return result
        with self._lock:
            payload = self._normalized_payload()
            items = payload["items"]
            for key in normalized:
                value = items.get(key)
                result[key] = dict(value) if isinstance(value, dict) else None
        return result

    def set_many(self, records: dict[str, dict[str, Any]]) -> int:
        cleaned: dict[str, dict[str, Any]] = {}
        for file_rel, meta in records.items():
            key = normalize_file_rel(file_rel)
            if not key or not isinstance(meta, dict):
                continue
            cleaned[key] = dict(meta)
        if not cleaned:
            return 0
        with self._lock:
            payload = self._normalized_payload()
            payload["items"].update(cleaned)
            payload["updated_at"] = utc_now_iso()
            self._write(payload)
        return len(cleaned)

    def delete(self, file_rel: str) -> bool:
        key = normalize_file_rel(file_rel)
        if not key:
            return False
        with self._lock:
            payload = self._normalized_payload()
            if key not in payload["items"]:
                return False
            payload["items"].pop(key, None)
            payload["updated_at"] = utc_now_iso()
            self._write(payload)
        return True
