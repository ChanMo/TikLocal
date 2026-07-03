import datetime
import json
import random
import subprocess as sp
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from tiklocal.services import FavoriteService, LibraryService


def _positive_float(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


@dataclass(frozen=True)
class RadioStation:
    id: str
    name: str
    description: str


@dataclass(frozen=True)
class RadioCandidate:
    path: Path
    name: str
    title: str
    artist: str
    album: str
    duration: float | None
    parent_key: str
    is_favorite: bool
    mtime: float


@dataclass(frozen=True)
class AudioMetadata:
    title: str = ""
    artist: str = ""
    album: str = ""
    duration: float | None = None


class RadioService:
    """Build low-decision radio batches from local audio files."""

    stations = [
        RadioStation("default", "默认电台", "综合最近添加与收藏内容"),
        RadioStation("recent", "最近添加", "优先播放新加入的音频"),
        RadioStation("favorites", "收藏电台", "优先播放已收藏的音频"),
    ]

    def __init__(self, library_service: LibraryService, favorite_service: FavoriteService):
        self.library = library_service
        self.favorites = favorite_service
        self._metadata_cache: dict[str, tuple[float, AudioMetadata]] = {}

    def list_stations(self) -> list[dict]:
        return [
            {"id": station.id, "name": station.name, "description": station.description}
            for station in self.stations
        ]

    def tune(
        self,
        *,
        station: str = "default",
        limit: int = 12,
        exclude: set[str] | None = None,
        seed: str | None = None,
        serialize_track: Callable[[RadioCandidate], dict],
    ) -> dict:
        station_id = station if station in {item.id for item in self.stations} else "default"
        candidates = self._collect_candidates()
        excluded = set(exclude or set())
        available = [item for item in candidates if item.name not in excluded]
        if not available and candidates:
            available = candidates

        rng = random.Random(seed) if seed else random.Random()
        if station_id == "recent":
            selected = self._select_recent(available, limit, rng)
        elif station_id == "favorites":
            selected = self._select_favorites(available, candidates, excluded, limit, rng)
        else:
            selected = self._select_weighted(available, limit, rng)

        station_meta = next(item for item in self.list_stations() if item["id"] == station_id)
        return {
            "station": station_meta,
            "items": [serialize_track(item) for item in selected],
            "total": len(candidates),
            "available": len(available),
        }

    def _collect_candidates(self) -> list[RadioCandidate]:
        favs = self.favorites.load()
        candidates: list[RadioCandidate] = []
        for path in self.library.scan_audios():
            try:
                name = self.library.get_relative_path(path)
                parent = self.library.relative_path_for_uri(name).rsplit("/", 1)[0]
                metadata = self.metadata_for(path)
                candidates.append(
                    RadioCandidate(
                        path=path,
                        name=name,
                        title=metadata.title or path.stem,
                        artist=metadata.artist,
                        album=metadata.album,
                        duration=metadata.duration,
                        parent_key=parent,
                        is_favorite=self.library.is_uri_in_set(name, favs),
                        mtime=path.stat().st_mtime,
                    )
                )
            except Exception:
                continue
        return candidates

    def metadata_for(self, path: Path) -> AudioMetadata:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return AudioMetadata()

        cache_key = str(path)
        cached = self._metadata_cache.get(cache_key)
        if cached and cached[0] == mtime:
            return cached[1]

        metadata = self._probe_audio_metadata(path)
        self._metadata_cache[cache_key] = (mtime, metadata)
        return metadata

    def _probe_audio_metadata(self, path: Path) -> AudioMetadata:
        try:
            proc = sp.run(
                [
                    "ffprobe",
                    "-v", "error",
                    "-show_entries", "format=duration:format_tags=title,artist,album",
                    "-of", "json",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if proc.returncode != 0:
                return AudioMetadata()
            payload = json.loads(proc.stdout or "{}")
            fmt = payload.get("format") if isinstance(payload, dict) else {}
            fmt = fmt if isinstance(fmt, dict) else {}
            tags = fmt.get("tags") if isinstance(fmt.get("tags"), dict) else {}
            normalized_tags = {str(key).lower(): str(value).strip() for key, value in tags.items()}
            duration = _positive_float(fmt.get("duration"))
            return AudioMetadata(
                title=normalized_tags.get("title", ""),
                artist=normalized_tags.get("artist", ""),
                album=normalized_tags.get("album", ""),
                duration=duration,
            )
        except Exception:
            return AudioMetadata()

    def _select_recent(
        self,
        candidates: list[RadioCandidate],
        limit: int,
        rng: random.Random,
    ) -> list[RadioCandidate]:
        pool = sorted(candidates, key=lambda item: item.mtime, reverse=True)[: max(limit * 8, 40)]
        return self._spread_by_parent(pool, limit, rng)

    def _select_favorites(
        self,
        available: list[RadioCandidate],
        all_candidates: list[RadioCandidate],
        excluded: set[str],
        limit: int,
        rng: random.Random,
    ) -> list[RadioCandidate]:
        favorites = [item for item in available if item.is_favorite]
        selected = self._spread_by_parent(favorites, limit, rng)
        if len(selected) >= limit:
            return selected

        favorite_parents = {item.parent_key for item in favorites}
        related = [
            item for item in available
            if item.name not in {chosen.name for chosen in selected}
            and item.parent_key in favorite_parents
        ]
        selected.extend(self._spread_by_parent(related, limit - len(selected), rng))
        if len(selected) >= limit:
            return selected

        fallback = [
            item for item in all_candidates
            if item.name not in excluded and item.name not in {chosen.name for chosen in selected}
        ]
        selected.extend(self._select_weighted(fallback, limit - len(selected), rng))
        return selected

    def _select_weighted(
        self,
        candidates: list[RadioCandidate],
        limit: int,
        rng: random.Random,
    ) -> list[RadioCandidate]:
        now = datetime.datetime.now().timestamp()
        weighted: list[tuple[RadioCandidate, float]] = []
        for item in candidates:
            age_days = max((now - item.mtime) / 86400, 0.0)
            recency = 2.0 if age_days <= 30 else max(0.2, 1.0 - min(age_days, 365) / 365)
            favorite = 3.0 if item.is_favorite else 1.0
            weighted.append((item, favorite * recency))

        selected: list[RadioCandidate] = []
        recent_parents: list[str] = []
        pool = weighted[:]
        while pool and len(selected) < limit:
            parent_counts = {parent: recent_parents.count(parent) for parent in set(recent_parents)}
            usable = [
                (item, weight) for item, weight in pool
                if parent_counts.get(item.parent_key, 0) < 2 or len(pool) <= 2
            ]
            if not usable:
                usable = pool
            picked = self._weighted_pick(usable, rng)
            selected.append(picked)
            recent_parents = (recent_parents + [picked.parent_key])[-2:]
            pool = [(item, weight) for item, weight in pool if item.name != picked.name]
        return selected

    def _spread_by_parent(
        self,
        candidates: list[RadioCandidate],
        limit: int,
        rng: random.Random,
    ) -> list[RadioCandidate]:
        pool = candidates[:]
        rng.shuffle(pool)
        selected: list[RadioCandidate] = []
        recent_parents: list[str] = []
        while pool and len(selected) < limit:
            idx = next(
                (
                    index for index, item in enumerate(pool)
                    if recent_parents.count(item.parent_key) < 2
                ),
                0,
            )
            picked = pool.pop(idx)
            selected.append(picked)
            recent_parents = (recent_parents + [picked.parent_key])[-2:]
        return selected

    def _weighted_pick(
        self,
        weighted: list[tuple[RadioCandidate, float]],
        rng: random.Random,
    ) -> RadioCandidate:
        total = sum(max(weight, 0.01) for _, weight in weighted)
        pick = rng.random() * total
        current = 0.0
        for item, weight in weighted:
            current += max(weight, 0.01)
            if current >= pick:
                return item
        return weighted[-1][0]
