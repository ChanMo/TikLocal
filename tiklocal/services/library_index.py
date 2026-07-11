import datetime
from pathlib import Path

from tiklocal.services import AUDIO_EXTENSIONS, IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from tiklocal.services.database import AppDatabase


class MediaIndexStore:
    """SQLite query index for the filesystem-backed media library."""

    def __init__(self, database: AppDatabase):
        self.database = database

    def replace_snapshot(self, records: list[dict]) -> dict:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.database.connect() as conn:
            conn.execute("CREATE TEMP TABLE media_index_seen(uri TEXT PRIMARY KEY)")
            for record in records:
                values = self._record_values(record, now)
                conn.execute(
                    """
                    INSERT INTO media_items(
                      uri, source_id, rel_path, filename, parent_path, media_type,
                      extension, size_bytes, mtime, discovered_at, indexed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(uri) DO UPDATE SET
                      source_id = excluded.source_id,
                      rel_path = excluded.rel_path,
                      filename = excluded.filename,
                      parent_path = excluded.parent_path,
                      media_type = excluded.media_type,
                      extension = excluded.extension,
                      size_bytes = excluded.size_bytes,
                      mtime = excluded.mtime,
                      indexed_at = excluded.indexed_at
                    """,
                    values,
                )
                conn.execute("INSERT OR IGNORE INTO media_index_seen(uri) VALUES (?)", (record["uri"],))
            deleted = conn.execute(
                "DELETE FROM media_items WHERE uri NOT IN (SELECT uri FROM media_index_seen)"
            ).rowcount
            conn.execute("DROP TABLE media_index_seen")
            conn.execute(
                """
                INSERT INTO media_index_state(id, last_synced_at, item_count)
                VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  last_synced_at = excluded.last_synced_at,
                  item_count = excluded.item_count
                """,
                (now, len(records)),
            )
        return {"indexed": len(records), "deleted": max(deleted, 0), "last_synced_at": now}

    def upsert(self, records: list[dict]) -> int:
        if not records:
            return 0
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.database.connect() as conn:
            for record in records:
                conn.execute(
                    """
                    INSERT INTO media_items(
                      uri, source_id, rel_path, filename, parent_path, media_type,
                      extension, size_bytes, mtime, discovered_at, indexed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(uri) DO UPDATE SET
                      size_bytes = excluded.size_bytes,
                      mtime = excluded.mtime,
                      indexed_at = excluded.indexed_at
                    """,
                    self._record_values(record, now),
                )
            count = conn.execute("SELECT COUNT(*) FROM media_items").fetchone()[0]
            conn.execute(
                """
                INSERT INTO media_index_state(id, last_synced_at, item_count)
                VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET item_count = excluded.item_count
                """,
                (now, count),
            )
        return len(records)

    def delete(self, uri: str) -> bool:
        with self.database.connect() as conn:
            deleted = conn.execute("DELETE FROM media_items WHERE uri = ?", (uri,)).rowcount
            if deleted:
                conn.execute(
                    "UPDATE media_index_state SET item_count = MAX(0, item_count - 1) WHERE id = 1"
                )
        return bool(deleted)

    def records(self, *, search: str = "", media_type: str = "") -> list[dict]:
        where, params = self._filters(search=search, media_type=media_type)
        with self.database.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM media_items {where} ORDER BY mtime DESC, uri",
                params,
            ).fetchall()
        return [self._to_library_record(row) for row in rows]

    def page(
        self,
        *,
        search: str = "",
        media_type: str = "",
        min_size: int = 0,
        offset: int = 0,
        limit: int = 48,
    ) -> dict:
        where, params = self._filters(
            search=search,
            media_type=media_type,
            min_size=min_size,
        )
        safe_offset = max(0, int(offset))
        safe_limit = max(1, min(int(limit), 96))
        with self.database.connect() as conn:
            total = int(conn.execute(
                f"SELECT COUNT(*) FROM media_items {where}",
                params,
            ).fetchone()[0])
            rows = conn.execute(
                f"SELECT * FROM media_items {where} ORDER BY mtime DESC, uri LIMIT ? OFFSET ?",
                [*params, safe_limit, safe_offset],
            ).fetchall()
        return {
            "records": [self._to_library_record(row) for row in rows],
            "total": total,
            "offset": safe_offset,
            "limit": safe_limit,
            "next_offset": safe_offset + safe_limit,
            "has_more": safe_offset + safe_limit < total,
        }

    def records_for_uris(self, uris: list[str]) -> list[dict]:
        wanted = list(dict.fromkeys(str(uri) for uri in uris if uri))
        if not wanted:
            return []
        found: dict[str, dict] = {}
        with self.database.connect() as conn:
            for start in range(0, len(wanted), 500):
                chunk = wanted[start:start + 500]
                placeholders = ",".join("?" for _ in chunk)
                rows = conn.execute(
                    f"SELECT * FROM media_items WHERE uri IN ({placeholders})",
                    chunk,
                ).fetchall()
                found.update({str(row["uri"]): self._to_library_record(row) for row in rows})
        return [found[uri] for uri in wanted if uri in found]

    def stats(self) -> dict:
        with self.database.connect() as conn:
            counts = {
                str(row["media_type"]): int(row["count"])
                for row in conn.execute(
                    "SELECT media_type, COUNT(*) AS count FROM media_items GROUP BY media_type"
                ).fetchall()
            }
            state = conn.execute("SELECT * FROM media_index_state WHERE id = 1").fetchone()
        return {
            "videos": counts.get("video", 0),
            "images": counts.get("image", 0),
            "audios": counts.get("audio", 0),
            "total": sum(counts.values()),
            "last_synced_at": str(state["last_synced_at"]) if state else "",
        }

    @staticmethod
    def _record_values(record: dict, now: str) -> tuple:
        return (
            record["uri"], record["source_id"], record["rel_path"], record["filename"],
            record["parent_path"], record["media_type"], record["extension"],
            int(record["size_bytes"]), float(record["mtime"]), now, now,
        )

    @staticmethod
    def _to_library_record(row) -> dict:
        return {
            "name": str(row["uri"]),
            "media_type": str(row["media_type"]),
            "mtime_ts": float(row["mtime"]),
            "size_bytes": int(row["size_bytes"]),
            "is_favorite": False,
        }

    @staticmethod
    def _like_term(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"%{escaped}%"

    @classmethod
    def _filters(
        cls,
        *,
        search: str,
        media_type: str,
        min_size: int = 0,
    ) -> tuple[str, list[object]]:
        clauses: list[str] = []
        params: list[object] = []
        if media_type:
            clauses.append("media_type = ?")
            params.append(media_type)
        else:
            clauses.append("media_type IN ('video', 'image')")
        if min_size > 0:
            clauses.append("size_bytes >= ?")
            params.append(int(min_size))
        term = str(search or "").strip()
        if term:
            clauses.append("(filename LIKE ? ESCAPE '\\' OR rel_path LIKE ? ESCAPE '\\')")
            escaped = cls._like_term(term)
            params.extend((escaped, escaped))
        return f"WHERE {' AND '.join(clauses)}", params


class LibraryIndexer:
    """Translate the filesystem library into stable index records."""

    def __init__(self, library_service, store: MediaIndexStore):
        self.library = library_service
        self.store = store

    def sync(self) -> dict:
        paths = (
            self.library.scan_videos()
            + self.library.scan_images()
            + self.library.scan_audios()
        )
        records_by_uri = {
            record["uri"]: record
            for path in paths
            if (record := self._record_for_path(path))
        }
        return self.store.replace_snapshot(list(records_by_uri.values()))

    def register_uris(self, uris: list[str]) -> int:
        records = []
        for uri in uris:
            path = self.library.resolve_path(uri)
            record = self._record_for_path(path) if path else None
            if record:
                records.append(record)
        return self.store.upsert(records)

    def _record_for_path(self, path: Path) -> dict | None:
        try:
            stat = path.stat()
            uri = self.library.get_relative_path(path)
            ref = self.library.parse_uri(uri)
            if not ref:
                return None
            suffix = path.suffix.lower()
            if suffix in VIDEO_EXTENSIONS:
                media_type = "video"
            elif suffix in IMAGE_EXTENSIONS:
                media_type = "image"
            elif suffix in AUDIO_EXTENSIONS:
                media_type = "audio"
            else:
                return None
            return {
                "uri": uri,
                "source_id": ref.source_id,
                "rel_path": ref.rel_path,
                "filename": path.name,
                "parent_path": str(Path(ref.rel_path).parent).replace("\\", "/"),
                "media_type": media_type,
                "extension": suffix,
                "size_bytes": int(stat.st_size),
                "mtime": float(stat.st_mtime),
            }
        except OSError:
            return None
