import hashlib
import datetime
from typing import Any

from tiklocal.services.database import AppDatabase


DEFAULT_SIMILARITY_THRESHOLD = 0.84
DEFAULT_SIMILARITY_SCAN_LIMIT = 500
DEFAULT_SIMILARITY_GROUP_LIMIT = 24
DEFAULT_SIMILARITY_MIN_GROUP_SIZE = 2
DEFAULT_SIMILARITY_MAX_GROUP_SIZE = 8
SIMILARITY_KIND_IMAGE_EMBEDDING = "image_embedding"


class SQLiteSimilarityGroupStore:
    def __init__(self, database: AppDatabase):
        self.database = database

    def clear(self, *, kind: str = SIMILARITY_KIND_IMAGE_EMBEDDING) -> int:
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT group_key FROM media_similarity_groups WHERE kind = ?",
                (kind,),
            ).fetchall()
            keys = [str(row["group_key"]) for row in rows]
            conn.execute("DELETE FROM media_similarity_groups WHERE kind = ?", (kind,))
        return len(keys)

    def save_groups(
        self,
        groups: list[dict[str, Any]],
        *,
        threshold: float,
        min_group_size: int,
        max_group_size: int,
        exclusive: bool = True,
        kind: str = SIMILARITY_KIND_IMAGE_EMBEDDING,
    ) -> int:
        now = datetime.datetime.utcnow().isoformat() + "Z"
        saved = 0
        with self.database.connect() as conn:
            conn.execute("DELETE FROM media_similarity_groups WHERE kind = ?", (kind,))
            for group in groups:
                items = [item for item in (group.get("items") or []) if item.get("uri")]
                if len(items) < min_group_size:
                    continue
                profile = self._group_profile(items)
                group_key = str(group.get("group_key") or "")
                if not group_key:
                    continue
                conn.execute(
                    """
                    INSERT INTO media_similarity_groups (
                      group_key, kind, seed_uri, score, item_count, threshold,
                      min_group_size, max_group_size, exclusive, model, dimensions,
                      image_max_size, image_quality, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        group_key,
                        kind,
                        str(group.get("seed_uri") or ""),
                        float(group.get("score") or 0),
                        len(items),
                        float(threshold),
                        int(min_group_size),
                        int(max_group_size),
                        1 if exclusive else 0,
                        profile["model"],
                        profile["dimensions"],
                        profile["image_max_size"],
                        profile["image_quality"],
                        now,
                        now,
                    ),
                )
                conn.executemany(
                    """
                    INSERT INTO media_similarity_group_items(group_key, uri, rank, score)
                    VALUES (?, ?, ?, ?)
                    """,
                    [
                        (
                            group_key,
                            str(item.get("uri") or ""),
                            index,
                            float(item.get("score") or 0),
                        )
                        for index, item in enumerate(items)
                    ],
                )
                saved += 1
        return saved

    def list_groups(
        self,
        *,
        offset: int = 0,
        limit: int = DEFAULT_SIMILARITY_GROUP_LIMIT,
        kind: str = SIMILARITY_KIND_IMAGE_EMBEDDING,
    ) -> dict[str, Any]:
        start = max(0, int(offset))
        safe_limit = max(1, min(int(limit), 5000))
        with self.database.connect() as conn:
            total = int(conn.execute(
                "SELECT COUNT(*) FROM media_similarity_groups WHERE kind = ?",
                (kind,),
            ).fetchone()[0])
            group_rows = conn.execute(
                """
                SELECT * FROM media_similarity_groups
                WHERE kind = ?
                ORDER BY
                  CASE WHEN item_count >= 3 THEN 0 ELSE 1 END,
                  item_count DESC,
                  score DESC,
                  updated_at DESC,
                  group_key ASC
                LIMIT ? OFFSET ?
                """,
                (kind, safe_limit, start),
            ).fetchall()
            group_keys = [str(row["group_key"]) for row in group_rows]
            items_by_group: dict[str, list[dict[str, Any]]] = {key: [] for key in group_keys}
            if group_keys:
                placeholders = ",".join("?" for _ in group_keys)
                item_rows = conn.execute(
                    f"""
                    SELECT * FROM media_similarity_group_items
                    WHERE group_key IN ({placeholders})
                    ORDER BY group_key ASC, rank ASC
                    """,
                    group_keys,
                ).fetchall()
                for row in item_rows:
                    key = str(row["group_key"])
                    items_by_group.setdefault(key, []).append({
                        "uri": str(row["uri"]),
                        "score": float(row["score"]),
                    })

        groups = []
        for row in group_rows:
            key = str(row["group_key"])
            groups.append({
                "type": "similar_group",
                "name": f"similar:{key}",
                "group_key": key,
                "seed_uri": str(row["seed_uri"]),
                "count": int(row["item_count"]),
                "score": float(row["score"]),
                "threshold": float(row["threshold"]),
                "items": items_by_group.get(key, []),
            })

        end = start + safe_limit
        return {
            "items": groups,
            "total": total,
            "offset": start,
            "limit": safe_limit,
            "next_offset": end,
            "has_more": end < total,
        }

    def _group_profile(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        metadata = items[0].get("metadata") if items else {}
        metadata = metadata if isinstance(metadata, dict) else {}
        return {
            "model": str(metadata.get("model") or ""),
            "dimensions": int(metadata.get("dimensions") or 0),
            "image_max_size": int(metadata.get("image_max_size") or 0),
            "image_quality": int(metadata.get("image_quality") or 0),
        }


class ImageSimilarityService:
    def __init__(self, library_service, vector_index):
        self.library_service = library_service
        self.vector_index = vector_index

    def build_groups(
        self,
        *,
        offset: int = 0,
        limit: int = DEFAULT_SIMILARITY_GROUP_LIMIT,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        min_group_size: int = DEFAULT_SIMILARITY_MIN_GROUP_SIZE,
        max_group_size: int = DEFAULT_SIMILARITY_MAX_GROUP_SIZE,
        scan_limit: int = DEFAULT_SIMILARITY_SCAN_LIMIT,
    ) -> dict[str, Any]:
        vectors = self.load_vectors(scan_limit=scan_limit)
        groups = self._greedy_groups(
            vectors,
            threshold=max(0.0, min(float(threshold), 1.0)),
            min_group_size=max(2, int(min_group_size)),
            max_group_size=max(2, int(max_group_size)),
        )

        start = max(0, int(offset))
        safe_limit = max(1, min(int(limit), 48))
        end = start + safe_limit
        page_items = groups[start:end]
        return {
            "items": page_items,
            "total": len(groups),
            "offset": start,
            "limit": safe_limit,
            "next_offset": end,
            "has_more": end < len(groups),
            "threshold": float(threshold),
            "vectors_loaded": len(vectors),
        }

    def profile_thresholds(
        self,
        *,
        scan_limit: int = DEFAULT_SIMILARITY_SCAN_LIMIT,
        thresholds: list[float] | None = None,
        min_group_size: int = DEFAULT_SIMILARITY_MIN_GROUP_SIZE,
        max_group_size: int = DEFAULT_SIMILARITY_MAX_GROUP_SIZE,
    ) -> list[dict[str, Any]]:
        vectors = self.load_vectors(scan_limit=scan_limit)
        values = thresholds or [0.92, 0.88, 0.84, 0.80]
        profile = []
        for threshold in values:
            pair_count = self.count_candidate_pairs(vectors, threshold=float(threshold))
            groups = self._greedy_groups(
                vectors,
                threshold=float(threshold),
                min_group_size=max(2, int(min_group_size)),
                max_group_size=max(2, int(max_group_size)),
            )
            profile.append({
                "threshold": float(threshold),
                "candidate_pairs": pair_count,
                "groups": len(groups),
                "grouped_images": sum(len(group.get("items") or []) for group in groups),
            })
        return profile

    def load_vectors(self, *, scan_limit: int) -> list[dict[str, Any]]:
        rows = self.vector_index.list_vectors(limit=scan_limit)
        result: list[dict[str, Any]] = []
        active_state: tuple[str, int, int, int] | None = None
        for row in rows:
            uri = self.library_service.find_existing_uri(str(row.get("uri") or ""))
            target = self.library_service.resolve_path(uri)
            if not target or not target.exists():
                continue
            metadata = dict(row.get("metadata") or {})
            state = (
                str(metadata.get("model") or ""),
                int(metadata.get("dimensions") or 0),
                int(metadata.get("image_max_size") or 0),
                int(metadata.get("image_quality") or 0),
            )
            if active_state is None:
                active_state = state
            if state != active_state:
                continue
            metadata["uri"] = uri
            result.append({
                "uri": uri,
                "embedding": row.get("embedding"),
                "embedding_norm": float(row.get("embedding_norm") or 0),
                "metadata": metadata,
            })
        return result

    def count_candidate_pairs(self, vectors: list[dict[str, Any]], *, threshold: float) -> int:
        count = 0
        for index, left in enumerate(vectors):
            for right in vectors[index + 1:]:
                if self._cosine_similarity(left, right) >= threshold:
                    count += 1
        return count

    def _greedy_groups(
        self,
        vectors: list[dict[str, Any]],
        *,
        threshold: float,
        min_group_size: int,
        max_group_size: int,
    ) -> list[dict[str, Any]]:
        used: set[str] = set()
        groups: list[dict[str, Any]] = []
        for seed in vectors:
            seed_uri = str(seed.get("uri") or "")
            if not seed_uri or seed_uri in used:
                continue
            seed_norm = float(seed.get("embedding_norm") or 0)
            if seed_norm <= 0:
                continue

            candidates: list[dict[str, Any]] = []
            for candidate in vectors:
                candidate_uri = str(candidate.get("uri") or "")
                if not candidate_uri or candidate_uri == seed_uri or candidate_uri in used:
                    continue
                score = self._cosine_similarity(seed, candidate)
                if score < threshold:
                    continue
                candidates.append({
                    "uri": candidate_uri,
                    "score": score,
                    "metadata": candidate.get("metadata") or {},
                })

            candidates.sort(key=lambda item: (-float(item.get("score") or 0), str(item.get("uri") or "")))
            members = [
                {"uri": seed_uri, "score": 1.0, "metadata": seed.get("metadata") or {}},
                *candidates[:max(0, max_group_size - 1)],
            ]
            if len(members) < min_group_size:
                continue

            member_uris = [str(item["uri"]) for item in members]
            used.update(member_uris)
            scores = [float(item.get("score") or 0) for item in members[1:]]
            average_score = sum(scores) / len(scores) if scores else 1.0
            groups.append({
                "type": "similar_group",
                "name": f"similar:{self._group_key(member_uris)}",
                "group_key": self._group_key(member_uris),
                "seed_uri": seed_uri,
                "count": len(members),
                "score": round(average_score, 4),
                "items": members,
            })

        groups.sort(key=lambda item: (-int(item.get("count") or 0), -float(item.get("score") or 0), str(item.get("seed_uri") or "")))
        return groups

    def _cosine_similarity(self, left: dict[str, Any], right: dict[str, Any]) -> float:
        left_embedding = left.get("embedding")
        right_embedding = right.get("embedding")
        left_norm = float(left.get("embedding_norm") or 0)
        right_norm = float(right.get("embedding_norm") or 0)
        if (
            left_norm <= 0
            or right_norm <= 0
            or left_embedding is None
            or right_embedding is None
            or len(left_embedding) != len(right_embedding)
        ):
            return -1.0
        dot = sum(float(a) * float(b) for a, b in zip(left_embedding, right_embedding))
        return dot / (left_norm * right_norm)

    def _group_key(self, uris: list[str]) -> str:
        payload = "\n".join(sorted(str(uri) for uri in uris if uri)).encode("utf-8")
        return hashlib.sha1(payload).hexdigest()[:16]
