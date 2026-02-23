import datetime
import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any


COLLECTIONS_VERSION = 1
MAX_COLLECTION_NAME_LENGTH = 80
MAX_COLLECTION_DESCRIPTION_LENGTH = 280
MAX_COLLECTION_ITEMS_MUTATION = 200


def _utc_now_iso() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _normalize_uri(value: Any) -> str:
    text = str(value or "").strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


class CollectionStore:
    def __init__(self, store_path: Path):
        self.store_path = store_path
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _read(self) -> dict[str, Any]:
        if not self.store_path.exists():
            return {
                "version": COLLECTIONS_VERSION,
                "updated_at": _utc_now_iso(),
                "collections": [],
            }
        try:
            with self.store_path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            return {
                "version": COLLECTIONS_VERSION,
                "updated_at": _utc_now_iso(),
                "collections": [],
            }
        return self._normalize_payload(payload)

    def _normalize_payload(self, payload: Any) -> dict[str, Any]:
        data = payload if isinstance(payload, dict) else {}
        raw_collections = data.get("collections")
        collections: list[dict[str, Any]] = []
        if isinstance(raw_collections, list):
            for item in raw_collections:
                normalized = self._normalize_collection(item)
                if normalized:
                    collections.append(normalized)

        collections.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        return {
            "version": int(data.get("version") or COLLECTIONS_VERSION),
            "updated_at": _normalize_text(data.get("updated_at")) or _utc_now_iso(),
            "collections": collections,
        }

    def _normalize_collection(self, raw: Any) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        collection_id = _normalize_text(raw.get("id"))
        if not collection_id:
            return None

        created_at = _normalize_text(raw.get("created_at")) or _utc_now_iso()
        updated_at = _normalize_text(raw.get("updated_at")) or created_at
        name = _normalize_text(raw.get("name"))[:MAX_COLLECTION_NAME_LENGTH]
        if not name:
            return None
        description = _normalize_text(raw.get("description"))[:MAX_COLLECTION_DESCRIPTION_LENGTH]
        cover_uri = _normalize_uri(raw.get("cover_uri"))

        items_raw = raw.get("items")
        items: list[dict[str, str]] = []
        seen: set[str] = set()
        if isinstance(items_raw, list):
            for item in items_raw:
                if not isinstance(item, dict):
                    continue
                uri = _normalize_uri(item.get("uri"))
                if not uri or uri in seen:
                    continue
                seen.add(uri)
                added_at = _normalize_text(item.get("added_at")) or created_at
                items.append({"uri": uri, "added_at": added_at})

        if cover_uri and all(entry["uri"] != cover_uri for entry in items):
            cover_uri = ""
        if not cover_uri and items:
            cover_uri = items[-1]["uri"]

        return {
            "id": collection_id,
            "name": name,
            "description": description,
            "cover_uri": cover_uri,
            "created_at": created_at,
            "updated_at": updated_at,
            "item_count": len(items),
            "items": items,
        }

    def _write(self, payload: dict[str, Any]) -> None:
        tmp_path = self.store_path.with_name(self.store_path.name + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.store_path)

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            payload = self._read()
            return [self._collection_copy(item, include_items=False) for item in payload["collections"]]

    def get(self, collection_id: str) -> dict[str, Any] | None:
        key = _normalize_text(collection_id)
        if not key:
            return None
        with self._lock:
            payload = self._read()
            found = self._find_collection(payload["collections"], key)
            if not found:
                return None
            return self._collection_copy(found, include_items=True)

    def create(self, name: str, description: str = "") -> dict[str, Any]:
        clean_name = _normalize_text(name)[:MAX_COLLECTION_NAME_LENGTH]
        if not clean_name:
            raise ValueError("name 不能为空。")
        clean_desc = _normalize_text(description)[:MAX_COLLECTION_DESCRIPTION_LENGTH]

        now = _utc_now_iso()
        item = {
            "id": "col_" + uuid.uuid4().hex[:12],
            "name": clean_name,
            "description": clean_desc,
            "cover_uri": "",
            "created_at": now,
            "updated_at": now,
            "item_count": 0,
            "items": [],
        }
        with self._lock:
            payload = self._read()
            payload["collections"].insert(0, item)
            payload["updated_at"] = now
            self._write(payload)
        return self._collection_copy(item, include_items=True)

    def update(
        self,
        collection_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        cover_uri: str | None = None,
    ) -> dict[str, Any] | None:
        key = _normalize_text(collection_id)
        if not key:
            return None

        with self._lock:
            payload = self._read()
            found = self._find_collection(payload["collections"], key)
            if not found:
                return None

            if name is not None:
                clean = _normalize_text(name)[:MAX_COLLECTION_NAME_LENGTH]
                if not clean:
                    raise ValueError("name 不能为空。")
                found["name"] = clean
            if description is not None:
                found["description"] = _normalize_text(description)[:MAX_COLLECTION_DESCRIPTION_LENGTH]
            if cover_uri is not None:
                normalized_cover = _normalize_uri(cover_uri)
                if normalized_cover and all(entry["uri"] != normalized_cover for entry in found["items"]):
                    raise ValueError("cover_uri 不在集合条目中。")
                found["cover_uri"] = normalized_cover

            found["item_count"] = len(found["items"])
            if not found["cover_uri"] and found["items"]:
                found["cover_uri"] = found["items"][-1]["uri"]
            if found["cover_uri"] and all(entry["uri"] != found["cover_uri"] for entry in found["items"]):
                found["cover_uri"] = found["items"][-1]["uri"] if found["items"] else ""

            now = _utc_now_iso()
            found["updated_at"] = now
            payload["updated_at"] = now
            payload["collections"].sort(key=lambda item: item.get("updated_at", ""), reverse=True)
            self._write(payload)
            return self._collection_copy(found, include_items=True)

    def delete(self, collection_id: str) -> bool:
        key = _normalize_text(collection_id)
        if not key:
            return False
        with self._lock:
            payload = self._read()
            collections = payload["collections"]
            next_collections = [item for item in collections if item.get("id") != key]
            if len(next_collections) == len(collections):
                return False
            payload["collections"] = next_collections
            payload["updated_at"] = _utc_now_iso()
            self._write(payload)
            return True

    def add_items(self, collection_id: str, uris: list[str]) -> dict[str, Any] | None:
        key = _normalize_text(collection_id)
        if not key:
            return None
        normalized = self._normalize_mutation_uris(uris)
        if not normalized:
            return self.get(collection_id)

        with self._lock:
            payload = self._read()
            found = self._find_collection(payload["collections"], key)
            if not found:
                return None

            seen = {entry["uri"] for entry in found["items"]}
            now = _utc_now_iso()
            changed = False
            for uri in normalized:
                if uri in seen:
                    continue
                found["items"].append({"uri": uri, "added_at": now})
                seen.add(uri)
                changed = True
            if changed:
                found["item_count"] = len(found["items"])
                if not found["cover_uri"]:
                    found["cover_uri"] = found["items"][-1]["uri"]
                found["updated_at"] = now
                payload["updated_at"] = now
                payload["collections"].sort(key=lambda item: item.get("updated_at", ""), reverse=True)
                self._write(payload)
            return self._collection_copy(found, include_items=True)

    def remove_items(self, collection_id: str, uris: list[str]) -> dict[str, Any] | None:
        key = _normalize_text(collection_id)
        if not key:
            return None
        normalized = set(self._normalize_mutation_uris(uris))
        if not normalized:
            return self.get(collection_id)

        with self._lock:
            payload = self._read()
            found = self._find_collection(payload["collections"], key)
            if not found:
                return None

            next_items = [entry for entry in found["items"] if entry["uri"] not in normalized]
            if len(next_items) == len(found["items"]):
                return self._collection_copy(found, include_items=True)

            found["items"] = next_items
            found["item_count"] = len(next_items)
            if found["cover_uri"] and all(entry["uri"] != found["cover_uri"] for entry in next_items):
                found["cover_uri"] = next_items[-1]["uri"] if next_items else ""
            elif not found["cover_uri"] and next_items:
                found["cover_uri"] = next_items[-1]["uri"]

            now = _utc_now_iso()
            found["updated_at"] = now
            payload["updated_at"] = now
            payload["collections"].sort(key=lambda item: item.get("updated_at", ""), reverse=True)
            self._write(payload)
            return self._collection_copy(found, include_items=True)

    def list_for_media(self, uri: str) -> list[dict[str, Any]]:
        key = _normalize_uri(uri)
        if not key:
            return []
        with self._lock:
            payload = self._read()
            result: list[dict[str, Any]] = []
            for item in payload["collections"]:
                if any(entry["uri"] == key for entry in item["items"]):
                    result.append(self._collection_copy(item, include_items=False))
            return result

    def list_item_uris(self, collection_id: str, *, newest_first: bool = True) -> list[str]:
        data = self.get(collection_id)
        if not data:
            return []
        items = data.get("items") if isinstance(data, dict) else []
        if not isinstance(items, list):
            return []
        uris = [str(entry.get("uri") or "") for entry in items if isinstance(entry, dict)]
        uris = [uri for uri in uris if uri]
        if newest_first:
            uris.reverse()
        return uris

    def _normalize_mutation_uris(self, uris: Any) -> list[str]:
        if not isinstance(uris, list):
            return []
        normalized: list[str] = []
        seen: set[str] = set()
        for item in uris:
            uri = _normalize_uri(item)
            if not uri or uri in seen:
                continue
            seen.add(uri)
            normalized.append(uri)
            if len(normalized) >= MAX_COLLECTION_ITEMS_MUTATION:
                break
        return normalized

    def _find_collection(self, collections: list[dict[str, Any]], collection_id: str) -> dict[str, Any] | None:
        for item in collections:
            if item.get("id") == collection_id:
                return item
        return None

    def _collection_copy(self, item: dict[str, Any], *, include_items: bool) -> dict[str, Any]:
        data = {
            "id": str(item.get("id") or ""),
            "name": str(item.get("name") or ""),
            "description": str(item.get("description") or ""),
            "cover_uri": str(item.get("cover_uri") or ""),
            "created_at": str(item.get("created_at") or ""),
            "updated_at": str(item.get("updated_at") or ""),
            "item_count": int(item.get("item_count") or 0),
        }
        if include_items:
            items = item.get("items")
            normalized_items: list[dict[str, str]] = []
            if isinstance(items, list):
                for entry in items:
                    if not isinstance(entry, dict):
                        continue
                    uri = _normalize_uri(entry.get("uri"))
                    if not uri:
                        continue
                    normalized_items.append({
                        "uri": uri,
                        "added_at": _normalize_text(entry.get("added_at")) or data["created_at"] or _utc_now_iso(),
                    })
            data["items"] = normalized_items
        return data
