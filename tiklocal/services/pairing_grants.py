import datetime
import hashlib
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Callable


PAIRING_GRANT_PREFIX = "tlpg_"


@dataclass(frozen=True)
class PairingGrant:
    token: str
    expires_at: str
    expires_in: int


class PairingGrantStore:
    """Hold short-lived, single-use Radio pairing grants in memory."""

    def __init__(
        self,
        *,
        ttl_seconds: int = 120,
        max_active: int = 20,
        clock: Callable[[], float] = time.time,
    ):
        self.ttl_seconds = max(30, min(int(ttl_seconds), 600))
        self.max_active = max(1, int(max_active))
        self._clock = clock
        self._grants: dict[str, dict[str, int | float]] = {}
        self._lock = threading.Lock()

    def issue(self, *, auth_revision: int) -> PairingGrant:
        now = self._clock()
        token = PAIRING_GRANT_PREFIX + secrets.token_urlsafe(32)
        expires_at = now + self.ttl_seconds
        with self._lock:
            self._discard_expired(now)
            if len(self._grants) >= self.max_active:
                oldest = min(
                    self._grants,
                    key=lambda grant_hash: float(
                        self._grants[grant_hash]["expires_at"]
                    ),
                )
                self._grants.pop(oldest, None)
            self._grants[self._token_hash(token)] = {
                "auth_revision": int(auth_revision),
                "expires_at": expires_at,
            }
        return PairingGrant(
            token=token,
            expires_at=datetime.datetime.fromtimestamp(
                expires_at,
                tz=datetime.timezone.utc,
            ).replace(microsecond=0).isoformat(),
            expires_in=self.ttl_seconds,
        )

    def consume(self, token: str, *, auth_revision: int) -> bool:
        candidate = str(token or "").strip()
        if (
            not candidate.startswith(PAIRING_GRANT_PREFIX)
            or len(candidate) != len(PAIRING_GRANT_PREFIX) + 43
        ):
            return False
        candidate_hash = self._token_hash(candidate)
        now = self._clock()
        with self._lock:
            self._discard_expired(now)
            grant = self._grants.pop(candidate_hash, None)
            return bool(
                grant
                and int(grant["auth_revision"]) == int(auth_revision)
            )

    def _discard_expired(self, now: float) -> None:
        expired = [
            grant_hash
            for grant_hash, grant in self._grants.items()
            if float(grant["expires_at"]) <= now
        ]
        for grant_hash in expired:
            self._grants.pop(grant_hash, None)

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()
