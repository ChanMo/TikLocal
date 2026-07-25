import datetime
import hashlib
import hmac
import json
import os
import secrets
import threading
from dataclasses import dataclass
from pathlib import Path


DEVICE_AUTH_FILE_VERSION = 1
TOKEN_PREFIX = "tlr_"


@dataclass(frozen=True)
class DeviceCredential:
    device_id: str
    device_name: str
    token: str


class DeviceAuthStore:
    """Issue and verify revocable high-entropy tokens for native Radio clients."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.RLock()

    def issue(self, device_name: str, *, auth_revision: int) -> DeviceCredential:
        with self._lock:
            name = str(device_name or "").strip()[:48] or "TikLocal Radio"
            device_id = secrets.token_hex(8)
            token = TOKEN_PREFIX + secrets.token_urlsafe(32)
            devices = self._load()
            devices.append({
                "id": device_id,
                "name": name,
                "token_hash": self._token_hash(token),
                "auth_revision": int(auth_revision),
                "created_at": datetime.datetime.now(datetime.timezone.utc)
                .replace(microsecond=0)
                .isoformat(),
            })
            self._save(devices)
        return DeviceCredential(device_id=device_id, device_name=name, token=token)

    def verify(self, token: str, *, auth_revision: int) -> bool:
        candidate = str(token or "").strip()
        if not candidate.startswith(TOKEN_PREFIX):
            return False
        candidate_hash = self._token_hash(candidate)
        with self._lock:
            return any(
                int(device.get("auth_revision") or 0) == int(auth_revision)
                and hmac.compare_digest(str(device.get("token_hash") or ""), candidate_hash)
                for device in self._load()
            )

    def list_devices(self, *, auth_revision: int) -> list[dict]:
        with self._lock:
            devices = list(reversed(self._load()))
        return [
            {
                "id": str(device.get("id") or ""),
                "name": str(device.get("name") or "TikLocal Radio"),
                "created_at": str(device.get("created_at") or ""),
                "active": int(device.get("auth_revision") or 0) == int(auth_revision),
            }
            for device in devices
            if device.get("id")
        ]

    def revoke(self, device_id: str) -> bool:
        with self._lock:
            devices = self._load()
            kept = [device for device in devices if str(device.get("id")) != str(device_id)]
            if len(kept) == len(devices):
                return False
            self._save(kept)
            return True

    def revoke_token(self, token: str, *, auth_revision: int) -> bool:
        candidate = str(token or "").strip()
        if not candidate.startswith(TOKEN_PREFIX):
            return False
        candidate_hash = self._token_hash(candidate)
        with self._lock:
            for device in self._load():
                if (
                    int(device.get("auth_revision") or 0) == int(auth_revision)
                    and hmac.compare_digest(
                        str(device.get("token_hash") or ""),
                        candidate_hash,
                    )
                ):
                    return self.revoke(str(device.get("id") or ""))
        return False

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"设备认证配置无法读取: {self.path}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"设备认证配置不完整: {self.path}")
        devices = payload.get("devices")
        if payload.get("version") != DEVICE_AUTH_FILE_VERSION or not isinstance(devices, list):
            raise RuntimeError(f"设备认证配置不完整: {self.path}")
        return [device for device in devices if isinstance(device, dict)]

    def _save(self, devices: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temp_path.write_text(
            json.dumps(
                {"version": DEVICE_AUTH_FILE_VERSION, "devices": devices},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        try:
            os.chmod(temp_path, 0o600)
        except OSError:
            pass
        os.replace(temp_path, self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()
