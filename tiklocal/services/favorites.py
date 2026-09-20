import json
from threading import RLock
from pathlib import Path

from tiklocal.services.library import LibraryService, normalize_media_uri

from tiklocal.services.json_storage import write_json_atomic

FAVORITE_FILENAME = 'favorite.json'


class FavoriteService:
    def __init__(
        self,
        media_root: str | Path | None = None,
        *,
        db_path: Path | None = None,
        library_service: LibraryService | None = None,
    ):
        self.db_path = db_path or (Path(media_root) / FAVORITE_FILENAME)
        self.library_service = library_service
        self.legacy_db_path = Path(media_root) / FAVORITE_FILENAME if media_root else None
        self._lock = RLock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._import_legacy_if_needed()

    def _normalize(self, filename: str) -> str:
        if self.library_service:
            return self.library_service.canonicalize_uri(filename)
        return normalize_media_uri(filename)

    def _read_raw(self, path: Path) -> set[str]:
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return set()
        if not isinstance(data, list):
            raise ValueError('收藏文件格式无效')
        return {normalize_media_uri(item) for item in data}

    def _import_legacy_if_needed(self) -> None:
        if not self.library_service or not self.legacy_db_path or not self.legacy_db_path.exists():
            return
        existing = self._read_raw(self.db_path)
        legacy = self._read_raw(self.legacy_db_path)
        merged = set(existing)
        for item in legacy:
            canonical = self.library_service.canonicalize_uri(item)
            if canonical:
                merged.add(canonical)
        if merged != existing:
            self.save(merged)

    def load(self) -> set[str]:
        values = self._read_raw(self.db_path)
        if self.library_service:
            return self.library_service.canonicalize_many(values)
        return values

    def save(self, favorites: set[str]) -> None:
        with self._lock:
            write_json_atomic(self.db_path, sorted(self._normalize(item) for item in favorites if normalize_media_uri(item)))

    def toggle(self, filename: str) -> bool:
        """Toggle and persist within one read-modify-write critical section."""
        with self._lock:
            favs = self.load()
            key = self._normalize(filename)
            return self._save_state(favs, key, key not in favs)

    def set_favorite(self, filename: str, is_favorite: bool) -> bool:
        """Set favorite state idempotently and return the persisted state."""
        with self._lock:
            return self._save_state(self.load(), self._normalize(filename), bool(is_favorite))

    def _save_state(self, favs: set[str], key: str, is_favorite: bool) -> bool:
        if is_favorite:
            favs.add(key)
        else:
            favs.discard(key)
        self.save(favs)
        return is_favorite

    def is_favorite(self, filename: str) -> bool:
        return self._normalize(filename) in self.load()
