import json
from pathlib import Path
from threading import RLock
from typing import Any

from tiklocal.services.json_storage import write_json_atomic


class ImageMetadataStore:
    def __init__(self, store_path: Path):
        self._lock = RLock()
        self.store_path = store_path
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.store_path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return {}
        if not isinstance(data, dict):
            raise ValueError('媒体元数据文件格式无效')
        return data

    def get(self, key: str) -> dict[str, Any] | None:
        return self._load().get(key)

    def get_many(self, keys) -> dict[str, dict]:
        data = self._load()
        return {key: data[key] for key in keys if key in data}

    def set(self, key: str, value: dict[str, Any], overwrite: bool = True) -> tuple[dict[str, Any], bool]:
        with self._lock:
            data = self._load()
            if not overwrite and key in data:
                return data[key], False
            data[key] = value
            write_json_atomic(self.store_path, data)
            return value, True

    def update_many(self, updates: dict[str, dict], *, defaults: dict[str, dict] | None = None) -> dict[str, dict]:
        """Merge changed fields against the latest state; defaults only fill absent legacy fields."""
        with self._lock:
            data = self._load()
            for key, fields in updates.items():
                data[key] = {**(defaults or {}).get(key, {}), **data.get(key, {}), **fields}
            write_json_atomic(self.store_path, data)
            return {key: data[key] for key in updates}
