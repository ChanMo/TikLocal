import datetime
import re
from pathlib import Path

from PIL import Image

from tiklocal.services import AUDIO_EXTENSIONS, IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from tiklocal.services.database import AppDatabase


class MediaIndexStore:
    """SQLite query index for the filesystem-backed media library."""

    def __init__(self, database: AppDatabase):
        self.database = database

    def replace_snapshot(
        self,
        records: list[dict],
        *,
        synced_source_ids: set[str] | None = None,
    ) -> dict:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        source_ids = sorted(
            {str(record["source_id"]) for record in records}
            if synced_source_ids is None
            else synced_source_ids
        )
        with self.database.connect() as conn:
            conn.execute("CREATE TEMP TABLE media_index_seen(uri TEXT PRIMARY KEY)")
            for record in records:
                values = self._record_values(record, now)
                conn.execute(
                    """
                    INSERT INTO media_items(
                      uri, source_id, rel_path, filename, parent_path, media_type,
                      extension, size_bytes, mtime, captured_at, captured_local_date,
                      capture_year, capture_month, time_source, time_confidence,
                      time_metadata_version, discovered_at, indexed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(uri) DO UPDATE SET
                      source_id = excluded.source_id,
                      rel_path = excluded.rel_path,
                      filename = excluded.filename,
                      parent_path = excluded.parent_path,
                      media_type = excluded.media_type,
                      extension = excluded.extension,
                      size_bytes = excluded.size_bytes,
                      mtime = excluded.mtime,
                      captured_at = excluded.captured_at,
                      captured_local_date = excluded.captured_local_date,
                      capture_year = excluded.capture_year,
                      capture_month = excluded.capture_month,
                      time_source = excluded.time_source,
                      time_confidence = excluded.time_confidence,
                      time_metadata_version = excluded.time_metadata_version,
                      indexed_at = excluded.indexed_at
                    """,
                    values,
                )
                conn.execute("INSERT OR IGNORE INTO media_index_seen(uri) VALUES (?)", (record["uri"],))
            deleted = 0
            if source_ids:
                placeholders = ",".join("?" for _ in source_ids)
                deleted = conn.execute(
                    f"""
                    DELETE FROM media_items
                    WHERE source_id IN ({placeholders})
                      AND uri NOT IN (SELECT uri FROM media_index_seen)
                    """,
                    source_ids,
                ).rowcount
            conn.execute("DROP TABLE media_index_seen")
            item_count = int(conn.execute("SELECT COUNT(*) FROM media_items").fetchone()[0])
            conn.execute(
                """
                INSERT INTO media_index_state(id, last_synced_at, item_count)
                VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  last_synced_at = excluded.last_synced_at,
                  item_count = excluded.item_count
                """,
                (now, item_count),
            )
        return {
            "indexed": len(records),
            "deleted": max(deleted, 0),
            "last_synced_at": now,
        }

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
                      extension, size_bytes, mtime, captured_at, captured_local_date,
                      capture_year, capture_month, time_source, time_confidence,
                      time_metadata_version, discovered_at, indexed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(uri) DO UPDATE SET
                      size_bytes = excluded.size_bytes,
                      mtime = excluded.mtime,
                      captured_at = excluded.captured_at,
                      captured_local_date = excluded.captured_local_date,
                      capture_year = excluded.capture_year,
                      capture_month = excluded.capture_month,
                      time_source = excluded.time_source,
                      time_confidence = excluded.time_confidence,
                      time_metadata_version = excluded.time_metadata_version,
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
        month: str = "",
        offset: int = 0,
        limit: int = 48,
    ) -> dict:
        where, params = self._filters(
            search=search,
            media_type=media_type,
            min_size=min_size,
            month=month,
        )
        safe_offset = max(0, int(offset))
        safe_limit = max(1, min(int(limit), 96))
        order_by = "captured_at DESC, uri" if self.is_month_key(month) else "mtime DESC, uri"
        with self.database.connect() as conn:
            total = int(conn.execute(
                f"SELECT COUNT(*) FROM media_items {where}",
                params,
            ).fetchone()[0])
            rows = conn.execute(
                f"SELECT * FROM media_items {where} ORDER BY {order_by} LIMIT ? OFFSET ?",
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

    def timeline_months(
        self,
        *,
        before: str = "",
        limit: int = 18,
        preview_limit: int = 18,
    ) -> dict:
        """Return compact month chapters without probing media metadata."""
        safe_limit = max(1, min(int(limit), 36))
        safe_preview_limit = max(1, min(int(preview_limit), 18))
        before_key = before if self.is_month_key(before) else ""
        month_expr = "capture_month"
        before_clause = f"AND {month_expr} < ?" if before_key else ""
        params: list[object] = [before_key] if before_key else []
        params.append(safe_limit + 1)

        with self.database.connect() as conn:
            year_rows = conn.execute(
                f"""
                SELECT
                  capture_year AS year,
                  COUNT(*) AS item_count,
                  COUNT(DISTINCT {month_expr}) AS month_count
                FROM media_items
                WHERE media_type IN ('image', 'video')
                GROUP BY year
                HAVING year IS NOT NULL
                ORDER BY year DESC
                """
            ).fetchall()
            month_rows = conn.execute(
                f"""
                SELECT
                  {month_expr} AS month_key,
                  COUNT(*) AS item_count,
                  SUM(CASE WHEN media_type = 'image' THEN 1 ELSE 0 END) AS image_count,
                  SUM(CASE WHEN media_type = 'video' THEN 1 ELSE 0 END) AS video_count,
                  MAX(mtime) AS latest_mtime
                FROM media_items
                WHERE media_type IN ('image', 'video')
                  {before_clause}
                GROUP BY month_key
                HAVING month_key IS NOT NULL
                ORDER BY month_key DESC
                LIMIT ?
                """,
                params,
            ).fetchall()

            has_more = len(month_rows) > safe_limit
            visible_rows = month_rows[:safe_limit]
            months: list[dict] = []
            for month_row in visible_rows:
                month_key = str(month_row["month_key"])
                # A bounded candidate window keeps dense months cheap while still
                # giving the sampler enough temporal spread for stable covers.
                candidates = conn.execute(
                    f"""
                    SELECT *
                    FROM media_items
                    WHERE media_type IN ('image', 'video')
                      AND {month_expr} = ?
                    ORDER BY captured_at DESC, uri
                    LIMIT 120
                    """,
                    (month_key,),
                ).fetchall()
                months.append({
                    "key": month_key,
                    "count": int(month_row["item_count"] or 0),
                    "image_count": int(month_row["image_count"] or 0),
                    "video_count": int(month_row["video_count"] or 0),
                    "latest_mtime": float(month_row["latest_mtime"] or 0),
                    "records": [
                        self._to_library_record(row)
                        for row in self._sample_timeline_records(candidates, safe_preview_limit)
                    ],
                })

        next_before = str(visible_rows[-1]["month_key"]) if visible_rows and has_more else ""
        return {
            "months": months,
            "years": [
                {
                    "year": str(row["year"]),
                    "count": int(row["item_count"] or 0),
                    "month_count": int(row["month_count"] or 0),
                }
                for row in year_rows
            ],
            "has_more": has_more,
            "next_before": next_before,
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

    def time_states(self) -> dict[str, dict]:
        """Return cached capture metadata so unchanged files are not reopened."""
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT uri, size_bytes, mtime, captured_at, captured_local_date,
                       time_source, time_confidence, time_metadata_version
                FROM media_items
                """
            ).fetchall()
        return {str(row["uri"]): dict(row) for row in rows}

    @staticmethod
    def _record_values(record: dict, now: str) -> tuple:
        return (
            record["uri"], record["source_id"], record["rel_path"], record["filename"],
            record["parent_path"], record["media_type"], record["extension"],
            int(record["size_bytes"]), float(record["mtime"]),
            float(record.get("captured_at") or record["mtime"]),
            str(record.get("captured_local_date") or ""),
            str(record.get("captured_local_date") or "")[:4],
            str(record.get("captured_local_date") or "")[:7],
            str(record.get("time_source") or "filesystem_mtime"),
            str(record.get("time_confidence") or "fallback"),
            int(record.get("time_metadata_version") or 1),
            now, now,
        )

    @staticmethod
    def _to_library_record(row) -> dict:
        return {
            "name": str(row["uri"]),
            "media_type": str(row["media_type"]),
            "mtime_ts": float(row["mtime"]),
            "captured_at": float(row["captured_at"] or row["mtime"]),
            "captured_local_date": str(row["captured_local_date"] or ""),
            "time_source": str(row["time_source"] or "filesystem_mtime"),
            "time_confidence": str(row["time_confidence"] or "fallback"),
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
        month: str = "",
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
        if cls.is_month_key(month):
            clauses.append("capture_month = ?")
            params.append(month)
        term = str(search or "").strip()
        if term:
            clauses.append("(filename LIKE ? ESCAPE '\\' OR rel_path LIKE ? ESCAPE '\\')")
            escaped = cls._like_term(term)
            params.extend((escaped, escaped))
        return f"WHERE {' AND '.join(clauses)}", params

    @staticmethod
    def is_month_key(value: str) -> bool:
        return bool(re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", str(value or "")))

    @staticmethod
    def _sample_timeline_records(rows, limit: int):
        """Pick stable, time-spread covers and avoid a video-heavy chapter."""
        values = list(rows)
        if len(values) <= limit:
            return values

        target_indexes = {
            round(position * (len(values) - 1) / max(1, limit - 1))
            for position in range(limit)
        }
        sampled = [values[index] for index in sorted(target_indexes)]
        video_limit = max(1, limit // 4)
        selected: list = []
        deferred_videos: list = []
        video_count = 0
        for row in sampled:
            if str(row["media_type"]) == "video" and video_count >= video_limit:
                deferred_videos.append(row)
                continue
            selected.append(row)
            if str(row["media_type"]) == "video":
                video_count += 1

        if len(selected) < limit:
            selected_uris = {str(row["uri"]) for row in selected}
            for row in values:
                if str(row["uri"]) in selected_uris or str(row["media_type"]) == "video":
                    continue
                selected.append(row)
                selected_uris.add(str(row["uri"]))
                if len(selected) >= limit:
                    break
        if len(selected) < limit:
            selected.extend(deferred_videos[:limit - len(selected)])
        return selected[:limit]


_FILENAME_DATE_PATTERNS = (
    re.compile(r"(?<!\d)(?P<year>19\d{2}|20\d{2})[-_]?\s?(?P<month>0[1-9]|1[0-2])[-_]?\s?(?P<day>0[1-9]|[12]\d|3[01])(?:[T_ -]?(?P<hour>[01]\d|2[0-3])[:._-]?(?P<minute>[0-5]\d)[:._-]?(?P<second>[0-5]\d))?(?!\d)"),
)


def _capture_payload(value: datetime.datetime, source: str, confidence: str) -> dict:
    return {
        "captured_at": value.timestamp(),
        "captured_local_date": value.strftime("%Y-%m-%dT%H:%M:%S"),
        "time_source": source,
        "time_confidence": confidence,
        "time_metadata_version": 1,
    }


def _parse_embedded_datetime(value: object) -> datetime.datetime | None:
    text = str(value or "").strip().replace("\x00", "")
    for pattern in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed = datetime.datetime.strptime(text[:19], pattern)
            if 1970 <= parsed.year <= 2100:
                return parsed
        except ValueError:
            continue
    return None


def _image_capture_time(path: Path) -> dict | None:
    try:
        with Image.open(path) as image:
            exif = image.getexif()
            for tag, source in (
                (36867, "exif_original"),
                (36868, "exif_digitized"),
                (306, "exif_datetime"),
            ):
                parsed = _parse_embedded_datetime(exif.get(tag))
                if parsed:
                    return _capture_payload(parsed, source, "high")
    except Exception:
        return None
    return None


def _filename_capture_time(path: Path) -> dict | None:
    stem = path.stem
    for pattern in _FILENAME_DATE_PATTERNS:
        match = pattern.search(stem)
        if not match:
            continue
        values = match.groupdict()
        try:
            parsed = datetime.datetime(
                int(values["year"]), int(values["month"]), int(values["day"]),
                int(values.get("hour") or 12), int(values.get("minute") or 0),
                int(values.get("second") or 0),
            )
            return _capture_payload(parsed, "filename", "medium")
        except ValueError:
            continue
    return None


def discover_capture_time(path: Path, media_type: str, mtime: float) -> dict:
    if media_type == "image":
        embedded = _image_capture_time(path)
        if embedded:
            return embedded
    filename_value = _filename_capture_time(path)
    if filename_value:
        return filename_value
    return _capture_payload(
        datetime.datetime.fromtimestamp(mtime),
        "filesystem_mtime",
        "fallback",
    )


class LibraryIndexer:
    """Translate the filesystem library into stable index records."""

    def __init__(self, library_service, store: MediaIndexStore):
        self.library = library_service
        self.store = store

    def sync(self) -> dict:
        time_states = self.store.time_states()
        available_source_ids = {
            source.id
            for source in self.library.sources
            if source.path.exists() and source.path.is_dir()
        }
        paths = (
            self.library.scan_videos()
            + self.library.scan_images()
            + self.library.scan_audios()
        )
        records_by_uri = {
            record["uri"]: record
            for path in paths
            if (record := self._record_for_path(path, time_states))
        }
        result = self.store.replace_snapshot(
            list(records_by_uri.values()),
            synced_source_ids=available_source_ids,
        )
        result["unavailable_sources"] = [
            source.id for source in self.library.sources if source.id not in available_source_ids
        ]
        return result

    def register_uris(self, uris: list[str]) -> int:
        time_states = self.store.time_states()
        records = []
        for uri in uris:
            path = self.library.resolve_path(uri)
            record = self._record_for_path(path, time_states) if path else None
            if record:
                records.append(record)
        return self.store.upsert(records)

    def _record_for_path(self, path: Path, time_states: dict[str, dict] | None = None) -> dict | None:
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
            existing = (time_states or {}).get(uri) or {}
            unchanged = (
                int(existing.get("size_bytes") or -1) == int(stat.st_size)
                and float(existing.get("mtime") or -1) == float(stat.st_mtime)
                and bool(existing.get("captured_local_date"))
                and int(existing.get("time_metadata_version") or 0) >= 1
            )
            capture = {
                "captured_at": float(existing.get("captured_at") or stat.st_mtime),
                "captured_local_date": str(existing.get("captured_local_date") or ""),
                "time_source": str(existing.get("time_source") or "filesystem_mtime"),
                "time_confidence": str(existing.get("time_confidence") or "fallback"),
                "time_metadata_version": int(existing.get("time_metadata_version") or 0),
            } if unchanged else discover_capture_time(path, media_type, float(stat.st_mtime))
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
                **capture,
            }
        except OSError:
            return None
