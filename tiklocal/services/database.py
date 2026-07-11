import datetime
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    up: Callable[[sqlite3.Connection], None]


def _migrate_001_create_image_vectors(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS image_vectors (
          uri TEXT PRIMARY KEY,
          source_id TEXT NOT NULL,
          rel_path TEXT NOT NULL,
          model TEXT NOT NULL,
          dimensions INTEGER NOT NULL,
          image_max_size INTEGER NOT NULL,
          image_quality INTEGER NOT NULL,
          mtime REAL NOT NULL,
          size_bytes INTEGER NOT NULL,
          embedding BLOB NOT NULL,
          embedding_norm REAL NOT NULL,
          indexed_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_image_vectors_source ON image_vectors(source_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_image_vectors_model ON image_vectors(model, dimensions)")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_image_vectors_state
        ON image_vectors(model, dimensions, image_max_size, image_quality, mtime, size_bytes)
        """
    )


def _migrate_002_create_media_similarity_groups(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS media_similarity_groups (
          group_key TEXT PRIMARY KEY,
          kind TEXT NOT NULL,
          seed_uri TEXT NOT NULL,
          score REAL NOT NULL,
          item_count INTEGER NOT NULL,
          threshold REAL NOT NULL,
          min_group_size INTEGER NOT NULL,
          max_group_size INTEGER NOT NULL,
          exclusive INTEGER NOT NULL,
          model TEXT NOT NULL,
          dimensions INTEGER NOT NULL,
          image_max_size INTEGER NOT NULL,
          image_quality INTEGER NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS media_similarity_group_items (
          group_key TEXT NOT NULL,
          uri TEXT NOT NULL,
          rank INTEGER NOT NULL,
          score REAL NOT NULL,
          PRIMARY KEY (group_key, uri),
          FOREIGN KEY (group_key) REFERENCES media_similarity_groups(group_key) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_media_similarity_groups_rank
        ON media_similarity_groups(kind, item_count DESC, score DESC, updated_at DESC)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_media_similarity_group_items_group_rank
        ON media_similarity_group_items(group_key, rank)
        """
    )


def _migrate_003_create_media_activity(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS media_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          session_id TEXT NOT NULL,
          uri TEXT NOT NULL,
          media_type TEXT NOT NULL,
          surface TEXT NOT NULL,
          event_type TEXT NOT NULL,
          consumed_ratio REAL,
          visible_ms INTEGER,
          metadata_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_media_events_uri_created
        ON media_events(uri, created_at DESC)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS media_affinity (
          uri TEXT PRIMARY KEY,
          media_type TEXT NOT NULL,
          impressions INTEGER NOT NULL DEFAULT 0,
          completes INTEGER NOT NULL DEFAULT 0,
          skips INTEGER NOT NULL DEFAULT 0,
          favorites INTEGER NOT NULL DEFAULT 0,
          replays INTEGER NOT NULL DEFAULT 0,
          total_visible_ms INTEGER NOT NULL DEFAULT 0,
          affinity_score REAL NOT NULL DEFAULT 0,
          last_shown_at TEXT,
          last_consumed_at TEXT,
          updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_media_affinity_recent
        ON media_affinity(last_shown_at DESC)
        """
    )


def _migrate_004_create_preference_dimensions(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS preference_dimensions (
          dimension_type TEXT NOT NULL,
          dimension_value TEXT NOT NULL,
          positive_score REAL NOT NULL DEFAULT 0,
          negative_score REAL NOT NULL DEFAULT 0,
          sample_count INTEGER NOT NULL DEFAULT 0,
          updated_at TEXT NOT NULL,
          PRIMARY KEY (dimension_type, dimension_value)
        )
        """
    )


def _migrate_005_create_media_index(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS media_items (
          uri TEXT PRIMARY KEY,
          source_id TEXT NOT NULL,
          rel_path TEXT NOT NULL,
          filename TEXT NOT NULL,
          parent_path TEXT NOT NULL,
          media_type TEXT NOT NULL,
          extension TEXT NOT NULL,
          size_bytes INTEGER NOT NULL,
          mtime REAL NOT NULL,
          discovered_at TEXT NOT NULL,
          indexed_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_media_items_type_mtime
        ON media_items(media_type, mtime DESC)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_media_items_source_parent
        ON media_items(source_id, parent_path)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS media_index_state (
          id INTEGER PRIMARY KEY CHECK (id = 1),
          last_synced_at TEXT NOT NULL,
          item_count INTEGER NOT NULL
        )
        """
    )


MIGRATIONS = [
    Migration(1, "create_image_vectors", _migrate_001_create_image_vectors),
    Migration(2, "create_media_similarity_groups", _migrate_002_create_media_similarity_groups),
    Migration(3, "create_media_activity", _migrate_003_create_media_activity),
    Migration(4, "create_preference_dimensions", _migrate_004_create_preference_dimensions),
    Migration(5, "create_media_index", _migrate_005_create_media_index),
]


class AppDatabase:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def migrate(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                  version INTEGER PRIMARY KEY,
                  name TEXT NOT NULL,
                  applied_at TEXT NOT NULL
                )
                """
            )

        for migration in MIGRATIONS:
            if self._is_applied(migration.version):
                continue
            self._apply(migration)

    def _is_applied(self, version: int) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM schema_migrations WHERE version = ?",
                (version,),
            ).fetchone()
            return row is not None

    def _apply(self, migration: Migration) -> None:
        with self.connect() as conn:
            migration.up(conn)
            conn.execute(
                "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, ?)",
                (migration.version, migration.name, datetime.datetime.now(datetime.timezone.utc).isoformat()),
            )


class MediaActivityStore:
    """Store sparse consumption events and a compact recommendation profile."""

    EVENT_DELTAS = {
        "complete": 0.22,
        "favorite": 0.30,
        "unfavorite": -0.20,
        "replay": 0.18,
        "open_detail": 0.10,
        "consumed": 0.0,
        "skip": -0.10,
        "error": 0.0,
    }
    DIMENSION_DELTAS = {
        "consumed": 0.015,
        "complete": 0.06,
        "favorite": 0.12,
        "unfavorite": -0.06,
        "replay": 0.08,
        "open_detail": 0.05,
        "skip": -0.035,
    }
    MAX_EVENTS = 20_000

    def __init__(self, database: AppDatabase):
        self.database = database

    def record_many(self, events: list[dict]) -> int:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        accepted = 0
        with self.database.connect() as conn:
            for raw in events[:50]:
                uri = str(raw.get("uri") or raw.get("name") or "").strip()
                event_type = str(raw.get("event") or raw.get("event_type") or "").strip()
                media_type = str(raw.get("media_type") or "").strip()
                surface = str(raw.get("surface") or "flow").strip()[:32]
                session_id = str(raw.get("session_id") or "").strip()[:80]
                if not uri or event_type not in {"impression", *self.EVENT_DELTAS}:
                    continue
                if media_type not in {"video", "image", "audio"}:
                    continue
                ratio = self._bounded_float(raw.get("ratio"), 0.0, 1.0)
                visible_ms = self._bounded_int(raw.get("visible_ms"), 0, 86_400_000)
                metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
                conn.execute(
                    """
                    INSERT INTO media_events(
                      session_id, uri, media_type, surface, event_type,
                      consumed_ratio, visible_ms, metadata_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (session_id, uri, media_type, surface, event_type, ratio,
                     visible_ms, json.dumps(metadata, ensure_ascii=False), now),
                )
                self._update_affinity(conn, uri, media_type, event_type, ratio, visible_ms, now)
                self._update_dimensions(conn, uri, media_type, event_type, now)
                accepted += 1
            if accepted:
                conn.execute(
                    """
                    DELETE FROM media_events
                    WHERE id NOT IN (
                      SELECT id FROM media_events ORDER BY id DESC LIMIT ?
                    )
                    """,
                    (self.MAX_EVENTS,),
                )
        return accepted

    def profiles_for(self, uris: list[str]) -> dict[str, dict]:
        unique = list(dict.fromkeys(str(uri) for uri in uris if uri))
        if not unique:
            return {}
        results: dict[str, dict] = {}
        with self.database.connect() as conn:
            for start in range(0, len(unique), 500):
                chunk = unique[start:start + 500]
                placeholders = ",".join("?" for _ in chunk)
                rows = conn.execute(
                    f"SELECT * FROM media_affinity WHERE uri IN ({placeholders})",
                    chunk,
                ).fetchall()
                results.update({str(row["uri"]): dict(row) for row in rows})
        return results

    def dimension_scores(self) -> dict[tuple[str, str], float]:
        with self.database.connect() as conn:
            rows = conn.execute("SELECT * FROM preference_dimensions").fetchall()
        return {
            (str(row["dimension_type"]), str(row["dimension_value"])):
                float(row["positive_score"]) - float(row["negative_score"])
            for row in rows
        }

    def clear(self) -> None:
        with self.database.connect() as conn:
            conn.execute("DELETE FROM media_events")
            conn.execute("DELETE FROM media_affinity")
            conn.execute("DELETE FROM preference_dimensions")

    def _update_affinity(
        self,
        conn: sqlite3.Connection,
        uri: str,
        media_type: str,
        event_type: str,
        ratio: float | None,
        visible_ms: int,
        now: str,
    ) -> None:
        delta = self.EVENT_DELTAS.get(event_type, 0.0)
        if event_type == "complete" and ratio is not None:
            delta += ratio * 0.08
        if event_type == "skip" and ratio is not None and ratio < 0.12:
            delta -= 0.04
        conn.execute(
            """
            INSERT INTO media_affinity(
              uri, media_type, impressions, completes, skips, favorites, replays,
              total_visible_ms, affinity_score, last_shown_at, last_consumed_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(uri) DO UPDATE SET
              media_type = excluded.media_type,
              impressions = impressions + excluded.impressions,
              completes = completes + excluded.completes,
              skips = skips + excluded.skips,
              favorites = CASE
                WHEN ? = 'favorite' THEN favorites + 1
                WHEN ? = 'unfavorite' THEN MAX(0, favorites - 1)
                ELSE favorites
              END,
              replays = replays + excluded.replays,
              total_visible_ms = total_visible_ms + excluded.total_visible_ms,
              affinity_score = MAX(-1.0, MIN(1.8, affinity_score + excluded.affinity_score)),
              last_shown_at = COALESCE(excluded.last_shown_at, last_shown_at),
              last_consumed_at = COALESCE(excluded.last_consumed_at, last_consumed_at),
              updated_at = excluded.updated_at
            """,
            (
                uri, media_type,
                1 if event_type == "impression" else 0,
                1 if event_type == "complete" else 0,
                1 if event_type == "skip" else 0,
                1 if event_type == "favorite" else 0,
                1 if event_type == "replay" else 0,
                visible_ms,
                delta,
                now if event_type == "impression" else None,
                now if event_type != "impression" else None,
                now,
                event_type,
                event_type,
            ),
        )

    def _update_dimensions(
        self,
        conn: sqlite3.Connection,
        uri: str,
        media_type: str,
        event_type: str,
        now: str,
    ) -> None:
        delta = self.DIMENSION_DELTAS.get(event_type, 0.0)
        if not delta:
            return
        for dimension_type, dimension_value in self.dimensions_for(uri, media_type):
            conn.execute(
                """
                INSERT INTO preference_dimensions(
                  dimension_type, dimension_value, positive_score,
                  negative_score, sample_count, updated_at
                ) VALUES (?, ?, ?, ?, 1, ?)
                ON CONFLICT(dimension_type, dimension_value) DO UPDATE SET
                  positive_score = MIN(3.0, positive_score + excluded.positive_score),
                  negative_score = MIN(3.0, negative_score + excluded.negative_score),
                  sample_count = sample_count + 1,
                  updated_at = excluded.updated_at
                """,
                (
                    dimension_type,
                    dimension_value,
                    max(delta, 0.0),
                    abs(min(delta, 0.0)),
                    now,
                ),
            )

    @staticmethod
    def dimensions_for(uri: str, media_type: str) -> list[tuple[str, str]]:
        clean = str(uri or "").strip().replace("\\", "/")
        source = "default"
        rel_path = clean
        if clean.startswith("@"):
            source, separator, rel_path = clean[1:].partition("/")
            if not separator:
                rel_path = ""
        parent = str(PurePosixPath(rel_path).parent)
        dimensions = [("media_type", media_type), ("source", source or "default")]
        if parent and parent != ".":
            dimensions.append(("directory", f"{source or 'default'}/{parent}"))
        return dimensions

    @staticmethod
    def _bounded_float(value, minimum: float, maximum: float) -> float | None:
        try:
            return max(minimum, min(float(value), maximum))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _bounded_int(value, minimum: int, maximum: int) -> int:
        try:
            return max(minimum, min(int(value or 0), maximum))
        except (TypeError, ValueError):
            return 0
