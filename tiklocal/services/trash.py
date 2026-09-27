"""Recoverable deletes: files move into a hidden folder inside their own media source."""

import datetime
import json
import secrets
import shutil
from pathlib import Path

TRASH_DIR = '.tiklocal-trash'
RETENTION_DAYS = 30


class TrashService:
    def __init__(self, library_service, retention_days: int = RETENTION_DAYS):
        self.library = library_service
        self.retention = datetime.timedelta(days=retention_days)

    def move(self, uri: str) -> dict:
        """Move a media file into its source's trash and return the new entry."""
        resolved = self.library.resolve_source_relative_path(uri)
        target = self.library.resolve_path(uri)
        if not resolved or not target or not target.is_file():
            raise FileNotFoundError(uri)
        source, _ = resolved
        now = datetime.datetime.now(datetime.timezone.utc)
        folder = source.path / TRASH_DIR / f"{now:%Y%m%d%H%M%S}-{secrets.token_hex(3)}"
        folder.mkdir(parents=True)
        entry = {
            'uri': self.library.canonicalize_uri(uri),
            'name': target.name,
            'size': target.stat().st_size,
            'deleted_at': now.isoformat(timespec='seconds'),
        }
        # Same filesystem as the source, so this is a rename rather than a copy.
        shutil.move(str(target), str(folder / target.name))
        (folder / 'entry.json').write_text(json.dumps(entry, ensure_ascii=False), encoding='utf-8')
        return {**entry, 'id': f"{source.id}.{folder.name}"}

    def restore(self, entry_id: str) -> str:
        """Put a trashed file back at its original path and return its URI."""
        folder, entry = self._entry(entry_id)
        target = self.library.resolve_path(entry['uri'])
        if not target:
            raise FileNotFoundError(entry['uri'])
        if target.exists():
            raise FileExistsError(entry['uri'])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(folder / entry['name']), str(target))
        shutil.rmtree(folder, ignore_errors=True)
        return entry['uri']

    def purge(self, entry_id: str) -> str:
        """Permanently delete one entry and return the URI it came from."""
        folder, entry = self._entry(entry_id)
        shutil.rmtree(folder)
        return entry['uri']

    def entries(self) -> list[dict]:
        """All trashed files across sources, newest first."""
        items = []
        for source in self.library.sources:
            root = source.path / TRASH_DIR
            if not root.is_dir():
                continue
            for folder in root.iterdir():
                entry = self._read(folder)
                if entry:
                    items.append({**entry, 'id': f"{source.id}.{folder.name}"})
        return sorted(items, key=lambda item: item['deleted_at'], reverse=True)

    def expired(self) -> list[str]:
        """Ids of entries older than the retention period."""
        cutoff = (datetime.datetime.now(datetime.timezone.utc) - self.retention).isoformat(timespec='seconds')
        return [item['id'] for item in self.entries() if item['deleted_at'] < cutoff]

    def _entry(self, entry_id: str) -> tuple[Path, dict]:
        source_id, _, name = str(entry_id).partition('.')
        source = self.library.sources_by_id.get(source_id)
        if not source or not name or '/' in name or '\\' in name or name.startswith('.'):
            raise KeyError(entry_id)
        folder = source.path / TRASH_DIR / name
        entry = self._read(folder)
        if not entry:
            raise KeyError(entry_id)
        return folder, entry

    @staticmethod
    def _read(folder: Path) -> dict | None:
        try:
            entry = json.loads((folder / 'entry.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None
        if not isinstance(entry, dict) or not (folder / str(entry.get('name', ''))).is_file():
            return None
        return entry
