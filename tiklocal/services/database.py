import datetime
import sqlite3
from dataclasses import dataclass
from pathlib import Path
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


MIGRATIONS = [
    Migration(1, "create_image_vectors", _migrate_001_create_image_vectors),
    Migration(2, "create_media_similarity_groups", _migrate_002_create_media_similarity_groups),
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
                (migration.version, migration.name, datetime.datetime.utcnow().isoformat() + "Z"),
            )
