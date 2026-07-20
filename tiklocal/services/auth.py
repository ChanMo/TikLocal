import datetime
import json
import os
import secrets
import string
from dataclasses import dataclass
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash


AUTH_FILE_VERSION = 1
MIN_PASSWORD_LENGTH = 8


@dataclass(frozen=True)
class AuthBootstrap:
    created: bool
    generated_password: str | None = None


def generate_initial_password() -> str:
    alphabet = string.ascii_letters.replace('I', '').replace('l', '').replace('O', '').replace('o', '') + '23456789'
    groups = [''.join(secrets.choice(alphabet) for _ in range(4)) for _ in range(4)]
    return '-'.join(groups)


class AuthStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._data: dict | None = None
        self._mtime_ns: int | None = None

    def _load(self) -> dict | None:
        if not self.path.exists():
            self._data = None
            self._mtime_ns = None
            return None
        try:
            mtime_ns = self.path.stat().st_mtime_ns
        except OSError as exc:
            raise RuntimeError(f'认证配置无法读取: {self.path}') from exc
        if self._data is not None and self._mtime_ns == mtime_ns:
            return self._data
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f'认证配置无法读取: {self.path}') from exc
        required = {'password_hash', 'secret_key', 'revision'}
        if not isinstance(data, dict) or not required.issubset(data):
            raise RuntimeError(f'认证配置不完整: {self.path}')
        self._data = data
        self._mtime_ns = mtime_ns
        return data

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(f'{self.path.suffix}.tmp')
        temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        try:
            os.chmod(temp_path, 0o600)
        except OSError:
            pass
        os.replace(temp_path, self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass
        self._data = data
        try:
            self._mtime_ns = self.path.stat().st_mtime_ns
        except OSError:
            self._mtime_ns = None

    def ensure(self, initial_password: str | None = None) -> AuthBootstrap:
        if self._load() is not None:
            return AuthBootstrap(created=False)
        supplied = str(initial_password or '').strip()
        password = supplied or generate_initial_password()
        self._validate_password(password)
        now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
        self._save({
            'version': AUTH_FILE_VERSION,
            'password_hash': generate_password_hash(password),
            'secret_key': secrets.token_hex(32),
            'revision': 1,
            'created_at': now,
            'updated_at': now,
        })
        return AuthBootstrap(created=True, generated_password=None if supplied else password)

    def set_password(self, password: str) -> None:
        self._validate_password(password)
        current = self._load() or {}
        now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
        self._save({
            'version': AUTH_FILE_VERSION,
            'password_hash': generate_password_hash(password),
            'secret_key': current.get('secret_key') or secrets.token_hex(32),
            'revision': int(current.get('revision') or 0) + 1,
            'created_at': current.get('created_at') or now,
            'updated_at': now,
        })

    def verify(self, password: str) -> bool:
        data = self._load()
        return bool(data and check_password_hash(str(data['password_hash']), str(password or '')))

    @property
    def secret_key(self) -> str:
        data = self._load()
        if not data:
            raise RuntimeError('认证尚未初始化')
        return str(data['secret_key'])

    @property
    def revision(self) -> int:
        data = self._load()
        if not data:
            raise RuntimeError('认证尚未初始化')
        return int(data['revision'])

    @staticmethod
    def _validate_password(password: str) -> None:
        if len(str(password or '')) < MIN_PASSWORD_LENGTH:
            raise ValueError(f'访问密码至少需要 {MIN_PASSWORD_LENGTH} 个字符')
