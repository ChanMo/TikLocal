import datetime
import math
import random

from tiklocal.services.library import LibraryService, VIDEO_EXTENSIONS
from tiklocal.services.favorites import FavoriteService


class RecommendService:
    def __init__(
        self,
        library_service: LibraryService,
        favorite_service: FavoriteService,
        activity_store=None,
        media_index=None,
    ):
        self.library = library_service
        self.favorites = favorite_service
        self.activity_store = activity_store
        self.media_index = media_index

    def get_weighted_selection(self, file_type='video', limit=20, seed=None) -> list[str]:
        """Get intelligent random selection of files."""
        if self.media_index:
            candidates = [
                {'uri': item['name'], 'mtime': item['mtime_ts']}
                for item in self.media_index.records(media_type=file_type)
            ]
        elif file_type == 'video':
            candidates = [
                {'uri': self.library.get_relative_path(path), 'mtime': path.stat().st_mtime}
                for path in self.library.scan_videos()
            ]
        else:
            candidates = [
                {'uri': self.library.get_relative_path(path), 'mtime': path.stat().st_mtime}
                for path in self.library.scan_images()
            ]
        if not candidates:
            return []

        favs = self.favorites.load()
        names = [item['uri'] for item in candidates]
        profiles = self.activity_store.profiles_for(names) if self.activity_store else {}
        dimension_scores = self.activity_store.dimension_scores() if self.activity_store else {}
        now = datetime.datetime.now()
        weighted_pool: list[dict] = []

        for candidate in candidates:
            try:
                rel_path = candidate['uri']
                mtime = candidate['mtime']
                is_fav = self.library.is_uri_in_set(rel_path, favs)
                base_score = 2.0 if is_fav else 1.0
                age_days = max((now - datetime.datetime.fromtimestamp(mtime)).total_seconds() / 86400, 0.0)
                time_score = math.exp(-age_days / 90.0)
                profile = profiles.get(rel_path) or {}
                affinity = max(-1.0, min(float(profile.get('affinity_score') or 0.0), 1.8))
                revisit_score = max(0.65, 1.0 + affinity * 0.2)
                recent_penalty = self._recent_exposure_weight(profile.get('last_shown_at'), now)
                dimensions = self.activity_store.dimensions_for(rel_path, file_type) if self.activity_store else []
                preference_score = sum(dimension_scores.get(dimension, 0.0) for dimension in dimensions)
                preference_weight = max(0.8, min(1.25, 1.0 + preference_score * 0.08))
                weighted_pool.append({
                    'uri': rel_path,
                    'weight': base_score * (0.1 + time_score) * revisit_score * recent_penalty * preference_weight,
                    'impressions': int(profile.get('impressions') or 0),
                    'dimensions': dict(dimensions),
                })
            except Exception:
                continue

        rng = random.Random(seed) if seed else random
        result: list[str] = []
        recent_dimensions: list[dict[str, str]] = []
        pool = weighted_pool[:]
        while pool and len(result) < limit:
            if len(result) % 4 == 3:
                least_seen = sorted(pool, key=lambda item: item['impressions'])
                exploration_pool = least_seen[:max(1, len(least_seen) // 3)]
                varied = [item for item in exploration_pool if self._diversity_weight(item, recent_dimensions) >= 1.0]
                if varied:
                    exploration_pool = varied
                chosen = rng.choice(exploration_pool)
            else:
                weighted = [
                    (item, item['weight'] * self._diversity_weight(item, recent_dimensions))
                    for item in pool
                ]
                total_weight = sum(weight for _, weight in weighted)
                if total_weight <= 0:
                    break
                pick = rng.random() * total_weight
                current = 0.0
                chosen = weighted[-1][0]
                for item, weight in weighted:
                    current += weight
                    if current >= pick:
                        chosen = item
                        break

            result.append(chosen['uri'])
            recent_dimensions = (recent_dimensions + [chosen['dimensions']])[-3:]
            pool.remove(chosen)
        return result

    @staticmethod
    def _diversity_weight(candidate: dict, recent: list[dict[str, str]]) -> float:
        dimensions = candidate.get('dimensions') or {}
        directory = dimensions.get('directory')
        source = dimensions.get('source')
        directory_count = sum(1 for item in recent if directory and item.get('directory') == directory)
        source_count = sum(1 for item in recent if source and item.get('source') == source)
        weight = 0.35 if directory_count >= 2 else 1.0
        if source_count >= 3:
            weight *= 0.5
        return weight

    def reasons_for(self, uris: list[str]) -> dict[str, str]:
        """Return a short, user-facing explanation for each selected item."""
        profiles = self.activity_store.profiles_for(uris) if self.activity_store else {}
        dimension_scores = self.activity_store.dimension_scores() if self.activity_store else {}
        favorites = self.favorites.load()
        now = datetime.datetime.now().timestamp()
        reasons: dict[str, str] = {}
        for uri in uris:
            profile = profiles.get(uri) or {}
            path = self.library.resolve_path(uri)
            media_type = str(profile.get('media_type') or '')
            if not media_type:
                media_type = 'video' if path and path.suffix.lower() in VIDEO_EXTENSIONS else 'image'
            if self.library.is_uri_in_set(uri, favorites):
                reasons[uri] = '来自你的收藏'
            elif self.activity_store and any(
                dimension_scores.get(dimension, 0.0) >= 0.15
                for dimension in self.activity_store.dimensions_for(uri, media_type)
            ):
                reasons[uri] = '符合你的浏览偏好'
            elif int(profile.get('impressions') or 0) == 0:
                reasons[uri] = '随机探索'
            else:
                try:
                    age_days = max((now - path.stat().st_mtime) / 86400, 0.0) if path else 999
                except OSError:
                    age_days = 999
                reasons[uri] = '最近加入' if age_days <= 30 else '很久没看'
        return reasons

    @staticmethod
    def _recent_exposure_weight(value: object, now: datetime.datetime) -> float:
        if not value:
            return 1.0
        try:
            shown = datetime.datetime.fromisoformat(str(value).replace('Z', '+00:00')).replace(tzinfo=None)
            hours = max((now - shown).total_seconds() / 3600, 0.0)
        except (TypeError, ValueError):
            return 1.0
        if hours < 6:
            return 0.12
        if hours < 48:
            return 0.35
        if hours < 24 * 14:
            return 0.7
        return 1.0
