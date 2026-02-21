import datetime
import json
import os
import queue
import re
import shutil
import subprocess as sp
import threading
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


DOWNLOAD_MAX_URL_LENGTH = 2048
DOWNLOAD_MAX_CONCURRENT_LIMIT = 16
DOWNLOAD_HISTORY_LIMIT = 200
COOKIE_MAX_UPLOAD_BYTES = 1024 * 1024
COOKIE_MATCH_MODE = "filename_contains_domain"
COOKIE_FILE_EXTENSIONS = {".txt", ".cookies"}
DOWNLOAD_ENGINES = {"yt-dlp", "gallery-dl"}
DEFAULT_DOWNLOAD_ENGINE = "yt-dlp"

DEFAULT_DOWNLOAD_CONFIG = {
    "enabled": True,
    "max_concurrent": 2,
    "default_to_root": True,
    "allow_playlist": False,
    "cookie_enabled": True,
    "cookie_dir": "~/.tiklocal/cookies",
    "cookie_match_mode": COOKIE_MATCH_MODE,
    "gallery_archive_enabled": True,
    "gallery_archive_file": "~/.tiklocal/gallery-dl-archive.txt",
}

TERMINAL_JOB_STATUS = {"success", "failed", "canceled"}

_PROGRESS_RE = re.compile(r"\[download\]\s+(?P<percent>\d+(?:\.\d+)?)%")
_ETA_RE = re.compile(r"ETA\s+(?P<eta>[0-9:]+)")
_DESTINATION_PATTERNS = [
    re.compile(r"^\[download\] Destination: (?P<path>.+)$"),
    re.compile(r'^\[Merger\] Merging formats into "(?P<path>.+)"$'),
    re.compile(r'^\[ExtractAudio\] Destination: (?P<path>.+)$'),
]


def _utc_now_iso() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _merge_download_config(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(base)
    if not override:
        return merged
    for key in (
        "enabled",
        "max_concurrent",
        "default_to_root",
        "allow_playlist",
        "cookie_enabled",
        "cookie_dir",
        "cookie_match_mode",
        "gallery_archive_enabled",
        "gallery_archive_file",
    ):
        if key in override:
            merged[key] = override[key]
    return merged


def validate_download_config(payload: Any, *, partial: bool = False) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(payload, dict):
        return None, "配置格式必须是 JSON 对象。"

    cleaned: dict[str, Any] = {}

    defaults = dict(DEFAULT_DOWNLOAD_CONFIG)
    env_cookie_dir = str(os.environ.get("TIKLOCAL_COOKIE_DIR", "")).strip()
    if env_cookie_dir:
        defaults["cookie_dir"] = env_cookie_dir

    def _read_bool(field: str) -> str | None:
        if field not in payload:
            if partial:
                return None
            cleaned[field] = bool(defaults[field])
            return None
        value = payload[field]
        if not isinstance(value, bool):
            return f"{field} 必须是布尔值。"
        cleaned[field] = value
        return None

    for field in ("enabled", "default_to_root", "allow_playlist", "cookie_enabled", "gallery_archive_enabled"):
        error = _read_bool(field)
        if error:
            return None, error

    if "max_concurrent" in payload or not partial:
        value = payload.get("max_concurrent", defaults["max_concurrent"])
        max_concurrent = _to_int(value)
        if max_concurrent is None:
            return None, "max_concurrent 必须是整数。"
        if max_concurrent < 0 or max_concurrent > DOWNLOAD_MAX_CONCURRENT_LIMIT:
            return None, f"max_concurrent 必须在 0 到 {DOWNLOAD_MAX_CONCURRENT_LIMIT} 之间。"
        cleaned["max_concurrent"] = max_concurrent

    if "cookie_dir" in payload or not partial:
        cookie_dir = str(payload.get("cookie_dir", defaults["cookie_dir"])).strip()
        if not cookie_dir:
            return None, "cookie_dir 不能为空。"
        cleaned["cookie_dir"] = cookie_dir

    if "cookie_match_mode" in payload or not partial:
        mode = str(payload.get("cookie_match_mode", defaults["cookie_match_mode"])).strip()
        if mode != COOKIE_MATCH_MODE:
            return None, f"cookie_match_mode 仅支持 {COOKIE_MATCH_MODE}。"
        cleaned["cookie_match_mode"] = mode

    if "gallery_archive_file" in payload or not partial:
        archive_file = str(payload.get("gallery_archive_file", defaults["gallery_archive_file"])).strip()
        if not archive_file:
            return None, "gallery_archive_file 不能为空。"
        cleaned["gallery_archive_file"] = archive_file

    return cleaned, None


def validate_download_url(payload: Any) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(payload, dict):
        return None, "请求格式必须是 JSON 对象。"

    url = str(payload.get("url", "")).strip()
    if not url:
        return None, "url 不能为空。"
    if len(url) > DOWNLOAD_MAX_URL_LENGTH:
        return None, f"url 长度不能超过 {DOWNLOAD_MAX_URL_LENGTH} 个字符。"

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None, "只支持 http/https 格式的 URL。"

    save_mode = str(payload.get("save_mode", "root")).strip() or "root"
    if save_mode != "root":
        return None, "首版仅支持保存到媒体根目录。"

    engine = str(payload.get("engine", DEFAULT_DOWNLOAD_ENGINE)).strip().lower() or DEFAULT_DOWNLOAD_ENGINE
    if engine not in DOWNLOAD_ENGINES:
        return None, "engine 必须是 yt-dlp 或 gallery-dl。"

    cookie_mode = str(payload.get("cookie_mode", "")).strip().lower()
    cookie_file_raw = payload.get("cookie_file")
    cookie_file = str(cookie_file_raw).strip() if cookie_file_raw is not None else ""

    if cookie_file and not cookie_mode:
        cookie_mode = "manual"
    if not cookie_mode:
        cookie_mode = "auto"

    if cookie_mode not in {"auto", "none", "manual"}:
        return None, "cookie_mode 必须是 auto、none 或 manual。"

    if cookie_mode == "manual":
        if not cookie_file:
            return None, "手动 cookie 模式需要 cookie_file。"
        if not is_safe_cookie_filename(cookie_file):
            return None, "cookie_file 非法，仅允许文件名。"
    else:
        cookie_file = ""

    return {
        "url": url,
        "save_mode": save_mode,
        "engine": engine,
        "cookie_mode": cookie_mode,
        "cookie_file": cookie_file,
    }, None


def is_safe_cookie_filename(name: str) -> bool:
    if not name:
        return False
    if name in {".", ".."}:
        return False
    if "/" in name or "\\" in name:
        return False
    if Path(name).name != name:
        return False
    if Path(name).suffix.lower() not in COOKIE_FILE_EXTENSIONS:
        return False
    return True


def _domain_candidates(host: str) -> list[str]:
    host = host.strip().lower().strip(".")
    if not host:
        return []
    parts = host.split(".")
    if len(parts) <= 1:
        return [host]
    candidates = []
    for i in range(0, len(parts) - 1):
        candidates.append(".".join(parts[i:]))
    return candidates


class DownloadConfigStore:
    def __init__(self, store_path: Path):
        self.store_path = store_path
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, Any]:
        if not self.store_path.exists():
            return {}
        try:
            with self.store_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def get(self) -> dict[str, Any]:
        data = self._load()
        defaults = dict(DEFAULT_DOWNLOAD_CONFIG)
        env_cookie_dir = str(os.environ.get("TIKLOCAL_COOKIE_DIR", "")).strip()
        if env_cookie_dir:
            defaults["cookie_dir"] = env_cookie_dir
        validated, _ = validate_download_config(data, partial=True)
        merged = _merge_download_config(defaults, validated)
        if isinstance(data.get("updated_at"), str):
            merged["updated_at"] = data["updated_at"]
        return merged

    def set(self, value: dict[str, Any]) -> dict[str, Any]:
        defaults = self.get()
        defaults.pop("updated_at", None)
        merged = _merge_download_config(defaults, value)
        validated, error = validate_download_config(merged, partial=False)
        if error:
            raise ValueError(error)

        payload = dict(validated)
        payload["updated_at"] = _utc_now_iso()
        self._write(payload)
        return payload

    def _write(self, data: dict[str, Any]) -> None:
        tmp_path = self.store_path.with_name(self.store_path.name + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.store_path)


class DownloadHistoryStore:
    def __init__(self, store_path: Path):
        self.store_path = store_path
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

    def get(self) -> list[dict[str, Any]]:
        if not self.store_path.exists():
            return []
        try:
            with self.store_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return [item for item in data if isinstance(item, dict)]
        except Exception:
            return []
        return []

    def save(self, jobs: list[dict[str, Any]]) -> None:
        tmp_path = self.store_path.with_name(self.store_path.name + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(jobs[:DOWNLOAD_HISTORY_LIMIT], f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.store_path)


class DownloadManager:
    def __init__(
        self,
        media_root: Path,
        config_store: DownloadConfigStore,
        history_store: DownloadHistoryStore,
    ):
        self.media_root = media_root.resolve()
        self.config_store = config_store
        self.history_store = history_store

        self._lock = threading.Lock()
        self._shutdown = threading.Event()
        self._queue: queue.Queue[str | None] = queue.Queue()

        self._jobs: dict[str, dict[str, Any]] = {}
        self._job_order: list[str] = []
        self._cancel_events: dict[str, threading.Event] = {}
        self._processes: dict[str, sp.Popen[str]] = {}
        self._workers: list[threading.Thread] = []

        self._config = self.config_store.get()
        self._load_history()
        self._ensure_workers()

    def probe_dependencies(self) -> dict[str, Any]:
        yt_dlp_path, yt_dlp_version = self._probe_binary("yt-dlp")
        gallery_dl_path, gallery_dl_version = self._probe_binary("gallery-dl")
        ffmpeg_path, _ = self._probe_binary("ffmpeg")

        return {
            "yt_dlp_available": bool(yt_dlp_path),
            "yt_dlp_path": yt_dlp_path or "",
            "yt_dlp_version": yt_dlp_version,
            "gallery_dl_available": bool(gallery_dl_path),
            "gallery_dl_path": gallery_dl_path or "",
            "gallery_dl_version": gallery_dl_version,
            "ffmpeg_available": bool(ffmpeg_path),
            "ffmpeg_path": ffmpeg_path or "",
        }

    def get_config(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._config)

    def update_config(self, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            merged = _merge_download_config(self._config, patch)
        validated, error = validate_download_config(merged, partial=False)
        if error:
            raise ValueError(error)

        saved = self.config_store.set(validated)
        with self._lock:
            self._config = _merge_download_config(DEFAULT_DOWNLOAD_CONFIG, saved)
            self._config["updated_at"] = saved.get("updated_at")
            self._ensure_workers_locked()
            return dict(self._config)

    def list_cookie_files(self) -> dict[str, Any]:
        with self._lock:
            cookie_enabled = bool(self._config.get("cookie_enabled", True))
            cookie_dir_text = str(self._config.get("cookie_dir", DEFAULT_DOWNLOAD_CONFIG["cookie_dir"])).strip()
        cookie_dir = self._expand_cookie_dir(cookie_dir_text)

        files: list[str] = []
        if cookie_enabled and cookie_dir.exists() and cookie_dir.is_dir():
            for entry in cookie_dir.iterdir():
                if not entry.is_file():
                    continue
                if entry.suffix.lower() not in COOKIE_FILE_EXTENSIONS:
                    continue
                files.append(entry.name)
        files.sort(key=lambda name: name.lower())
        return {
            "cookie_enabled": cookie_enabled,
            "cookie_dir": str(cookie_dir),
            "files": files,
        }

    def enqueue(
        self,
        url: str,
        *,
        save_mode: str = "root",
        engine: str = DEFAULT_DOWNLOAD_ENGINE,
        cookie_mode: str = "auto",
        cookie_file: str = "",
        retry_of: str = "",
        output_token: str = "",
    ) -> dict[str, Any]:
        engine = (engine or DEFAULT_DOWNLOAD_ENGINE).strip().lower()
        if engine not in DOWNLOAD_ENGINES:
            raise RuntimeError("不支持的下载引擎。")

        chosen_file, chosen_mode, cookie_error = self._resolve_cookie_choice(
            url=url,
            cookie_mode=cookie_mode,
            cookie_file=cookie_file,
        )
        if cookie_error:
            raise RuntimeError(cookie_error)

        with self._lock:
            if not self._config.get("enabled", True):
                raise RuntimeError("下载功能已禁用。")

            job_id = uuid.uuid4().hex[:12]
            now = _utc_now_iso()
            job = {
                "id": job_id,
                "url": url,
                "save_mode": save_mode,
                "engine": engine,
                "engine_version": self._probe_binary(engine)[1],
                "status": "queued",
                "progress_percent": None,
                "eta_sec": None,
                "created_at": now,
                "started_at": None,
                "finished_at": None,
                "output_path_rel": "",
                "output_files_rel": [],
                "file_count": 0,
                "error_message": "",
                "requested_format": "mp4_preferred",
                "cancel_requested": False,
                "cookie_file": chosen_file,
                "cookie_match_mode": chosen_mode,
                "retry_of": retry_of.strip(),
                "output_token": output_token.strip() or now.replace(":", "").replace("-", "").replace("Z", ""),
            }
            self._jobs[job_id] = job
            self._job_order.insert(0, job_id)
            self._cancel_events[job_id] = threading.Event()
            self._persist_locked()
            max_concurrent = int(self._config.get("max_concurrent", 2))

        if max_concurrent == 0:
            threading.Thread(target=self._run_job, args=(job_id,), daemon=True).start()
        else:
            self._ensure_workers()
            self._queue.put(job_id)

        return self.get_job(job_id) or job

    def upload_cookie_file(self, filename: str, content: bytes, *, replace: bool = False) -> dict[str, Any]:
        safe_name = str(filename or "").strip()
        if not is_safe_cookie_filename(safe_name):
            raise ValueError("文件名非法，仅支持 .txt/.cookies。")
        if not isinstance(content, (bytes, bytearray)):
            raise ValueError("文件内容格式错误。")
        if len(content) == 0:
            raise ValueError("文件内容不能为空。")
        if len(content) > COOKIE_MAX_UPLOAD_BYTES:
            raise ValueError(f"文件不能超过 {COOKIE_MAX_UPLOAD_BYTES // 1024} KB。")

        cookie_dir = self._cookie_dir_path()
        target = (cookie_dir / safe_name).resolve()
        try:
            target.relative_to(cookie_dir.resolve())
        except ValueError as exc:
            raise ValueError("文件路径非法。") from exc

        if target.exists() and not replace:
            raise ValueError(f"文件已存在: {safe_name}")

        tmp_path = target.with_suffix(target.suffix + ".tmp")
        with tmp_path.open("wb") as f:
            f.write(bytes(content))
        os.replace(tmp_path, target)
        try:
            os.chmod(target, 0o600)
        except Exception:
            pass

        return {
            "filename": safe_name,
            "size": target.stat().st_size if target.exists() else len(content),
            "cookie_dir": str(cookie_dir),
        }

    def delete_job(self, job_id: str) -> tuple[bool, str | None]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return False, "Job not found"
            if job.get("status") not in TERMINAL_JOB_STATUS:
                return False, "运行中任务不可删除"

            self._jobs.pop(job_id, None)
            self._cancel_events.pop(job_id, None)
            self._processes.pop(job_id, None)
            self._job_order = [jid for jid in self._job_order if jid != job_id]
            self._persist_locked()
        return True, None

    def clear_history(self) -> int:
        deleted = 0
        with self._lock:
            keep_ids: list[str] = []
            for job_id in self._job_order:
                job = self._jobs.get(job_id)
                if not job:
                    continue
                if job.get("status") in TERMINAL_JOB_STATUS:
                    deleted += 1
                    self._jobs.pop(job_id, None)
                    self._cancel_events.pop(job_id, None)
                    self._processes.pop(job_id, None)
                else:
                    keep_ids.append(job_id)
            self._job_order = keep_ids
            self._persist_locked()
        return deleted

    def retry_job(self, job_id: str) -> tuple[dict[str, Any] | None, str | None]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None, "Job not found"
            if job.get("status") not in {"failed", "canceled"}:
                return None, "仅失败或已取消任务支持重试"
            url = str(job.get("url") or "")
            save_mode = str(job.get("save_mode") or "root")
            engine = str(job.get("engine") or DEFAULT_DOWNLOAD_ENGINE)
            cookie_file = str(job.get("cookie_file") or "")
            cookie_match_mode = str(job.get("cookie_match_mode") or "none")
            output_token = str(job.get("output_token") or "")

        cookie_mode = "none"
        if cookie_match_mode in {"auto", "manual"}:
            cookie_mode = cookie_match_mode

        try:
            new_job = self.enqueue(
                url,
                save_mode=save_mode,
                engine=engine,
                cookie_mode=cookie_mode,
                cookie_file=cookie_file,
                retry_of=job_id,
                output_token=output_token,
            )
            return new_job, None
        except RuntimeError as exc:
            return None, str(exc)

    def list_jobs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit or 50), DOWNLOAD_HISTORY_LIMIT))
        with self._lock:
            job_ids = self._job_order[:limit]
            return [dict(self._jobs[job_id]) for job_id in job_ids if job_id in self._jobs]

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def cancel(self, job_id: str) -> dict[str, Any] | None:
        process: sp.Popen[str] | None = None
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None

            if job["status"] in TERMINAL_JOB_STATUS:
                return dict(job)

            cancel_event = self._cancel_events.get(job_id)
            if cancel_event:
                cancel_event.set()

            job["cancel_requested"] = True
            if job["status"] == "queued":
                self._mark_canceled_locked(job)
                return dict(job)

            process = self._processes.get(job_id)

        if process:
            self._terminate_process(process)

        return self.get_job(job_id)

    def _load_history(self) -> None:
        history = self.history_store.get()
        now = _utc_now_iso()
        with self._lock:
            for item in history[:DOWNLOAD_HISTORY_LIMIT]:
                job_id = str(item.get("id") or "").strip()
                if not job_id:
                    continue

                status = str(item.get("status") or "failed")
                if status in {"queued", "running"}:
                    status = "failed"
                    item["error_message"] = "任务因服务重启中断。"
                    item["finished_at"] = now
                raw_output_files = item.get("output_files_rel")
                output_files_rel = raw_output_files if isinstance(raw_output_files, list) else []

                job = {
                    "id": job_id,
                    "url": str(item.get("url") or ""),
                    "save_mode": str(item.get("save_mode") or "root"),
                    "engine": str(item.get("engine") or DEFAULT_DOWNLOAD_ENGINE),
                    "engine_version": str(item.get("engine_version") or ""),
                    "status": status,
                    "progress_percent": item.get("progress_percent"),
                    "eta_sec": item.get("eta_sec"),
                    "created_at": str(item.get("created_at") or now),
                    "started_at": item.get("started_at"),
                    "finished_at": item.get("finished_at"),
                    "output_path_rel": str(item.get("output_path_rel") or ""),
                    "output_files_rel": [str(v) for v in output_files_rel if str(v).strip()],
                    "file_count": _to_int(item.get("file_count")) or 0,
                    "error_message": str(item.get("error_message") or ""),
                    "requested_format": str(item.get("requested_format") or "mp4_preferred"),
                    "cancel_requested": False,
                    "cookie_file": str(item.get("cookie_file") or ""),
                    "cookie_match_mode": str(item.get("cookie_match_mode") or "none"),
                    "retry_of": str(item.get("retry_of") or ""),
                    "output_token": str(
                        item.get("output_token")
                        or str(item.get("created_at") or now).replace(":", "").replace("-", "").replace("Z", "")
                    ),
                }
                if not job["file_count"] and job["output_files_rel"]:
                    job["file_count"] = len(job["output_files_rel"])
                if not job["output_files_rel"] and job["output_path_rel"]:
                    job["output_files_rel"] = [job["output_path_rel"]]
                    job["file_count"] = max(1, job["file_count"])
                self._jobs[job_id] = job
                self._job_order.append(job_id)
                self._cancel_events[job_id] = threading.Event()

    def _ensure_workers(self) -> None:
        with self._lock:
            self._ensure_workers_locked()

    def _ensure_workers_locked(self) -> None:
        max_concurrent = int(self._config.get("max_concurrent", DEFAULT_DOWNLOAD_CONFIG["max_concurrent"]))
        if max_concurrent <= 0:
            return

        self._workers = [worker for worker in self._workers if worker.is_alive()]
        missing = max_concurrent - len(self._workers)
        for _ in range(max(0, missing)):
            worker = threading.Thread(target=self._worker_loop, daemon=True)
            worker.start()
            self._workers.append(worker)

    def _worker_loop(self) -> None:
        while not self._shutdown.is_set():
            try:
                job_id = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if job_id is None:
                self._queue.task_done()
                break

            self._run_job(job_id)
            self._queue.task_done()

    def _run_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return

            if job["status"] != "queued":
                return

            cancel_event = self._cancel_events.get(job_id)
            if cancel_event and cancel_event.is_set():
                self._mark_canceled_locked(job)
                return

            job["status"] = "running"
            job["started_at"] = _utc_now_iso()
            job["progress_percent"] = 0.0
            self._persist_locked()

        try:
            result = self._execute_download(job_id)
            return_code, error_message, output_rel_list = self._normalize_execute_result(result)

            with self._lock:
                job = self._jobs.get(job_id)
                if not job:
                    return

                cancel_event = self._cancel_events.get(job_id)
                if cancel_event and cancel_event.is_set():
                    self._mark_canceled_locked(job)
                    return

                if return_code == 0:
                    job["status"] = "success"
                    job["progress_percent"] = 100.0
                    job["eta_sec"] = 0
                    job["output_files_rel"] = output_rel_list
                    job["file_count"] = len(output_rel_list)
                    job["output_path_rel"] = output_rel_list[0] if output_rel_list else ""
                    job["error_message"] = ""
                else:
                    job["status"] = "failed"
                    job["error_message"] = error_message or "下载失败，请检查 URL 与网络环境。"

                job["finished_at"] = _utc_now_iso()
                self._persist_locked()
        except FileNotFoundError as exc:
            with self._lock:
                job = self._jobs.get(job_id)
                if not job:
                    return
                engine = str(job.get("engine") or DEFAULT_DOWNLOAD_ENGINE)
                job["status"] = "failed"
                job["finished_at"] = _utc_now_iso()
                missing_text = str(exc or "").lower()
                if "gallery-dl" in missing_text or engine == "gallery-dl":
                    job["error_message"] = "未检测到 gallery-dl，请先安装后再使用该引擎。"
                else:
                    job["error_message"] = "未检测到 yt-dlp，请先安装后再使用下载功能。"
                self._persist_locked()
        except Exception as exc:  # pragma: no cover - defensive branch
            with self._lock:
                job = self._jobs.get(job_id)
                if not job:
                    return
                job["status"] = "failed"
                job["finished_at"] = _utc_now_iso()
                job["error_message"] = str(exc)
                self._persist_locked()
        finally:
            with self._lock:
                self._processes.pop(job_id, None)

    def _execute_download(self, job_id: str) -> tuple[int, str, list[str]] | tuple[int, str, str]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return 1, "任务不存在。", ""
            engine = str(job.get("engine") or DEFAULT_DOWNLOAD_ENGINE)

        if engine == "gallery-dl":
            return self._execute_download_gallery_dl(job_id)
        return self._execute_download_yt_dlp(job_id)

    def _execute_download_yt_dlp(self, job_id: str) -> tuple[int, str, list[str]]:
        yt_dlp_bin = shutil.which("yt-dlp")
        if not yt_dlp_bin:
            raise FileNotFoundError("yt-dlp not found")

        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return 1, "任务不存在。", []
            url = job["url"]
            created_at = str(job.get("created_at") or _utc_now_iso())
            output_token = str(job.get("output_token") or created_at.replace(":", "").replace("-", "").replace("Z", ""))
            allow_playlist = bool(self._config.get("allow_playlist", False))
            cookie_file = str(job.get("cookie_file") or "")
            cookie_match_mode = str(job.get("cookie_match_mode") or "none")

        output_template = str(self.media_root / f"%(title).180B [%(id)s] {output_token}.%(ext)s")

        cmd = [
            yt_dlp_bin,
            "--newline",
            "--restrict-filenames",
            "--merge-output-format",
            "mp4",
            "--continue",
            "--retries",
            "10",
            "--fragment-retries",
            "10",
            "--file-access-retries",
            "5",
            "--socket-timeout",
            "30",
            "-o",
            output_template,
        ]
        if not allow_playlist:
            cmd.append("--no-playlist")

        if cookie_file and cookie_match_mode in {"auto", "manual"}:
            cookie_path, error = self._resolve_cookie_path(cookie_file)
            if error:
                return 1, error, []
            cmd.extend(["--cookies", str(cookie_path)])

        cmd.append(url)

        process = sp.Popen(
            cmd,
            stdout=sp.PIPE,
            stderr=sp.STDOUT,
            text=True,
            bufsize=1,
        )

        with self._lock:
            self._processes[job_id] = process

        cancel_event = self._cancel_events.get(job_id)
        output_path_abs = ""
        error_message = ""

        stream = process.stdout
        if stream is not None:
            for raw_line in stream:
                line = raw_line.strip()
                if not line:
                    continue

                progress = self._parse_progress(line)
                if progress:
                    self._update_progress(job_id, progress)

                found_path = self._parse_output_path(line)
                if found_path:
                    output_path_abs = found_path

                extracted_error = self._extract_error_line(line)
                if extracted_error:
                    error_message = extracted_error

                if cancel_event and cancel_event.is_set():
                    self._terminate_process(process)

        return_code = process.wait()
        if not error_message and return_code != 0:
            error_message = f"yt-dlp exited with code {return_code}."

        output_rel = self._to_media_relative(output_path_abs)
        return return_code, error_message, [output_rel] if output_rel else []

    def _execute_download_gallery_dl(self, job_id: str) -> tuple[int, str, list[str]]:
        gallery_dl_bin = shutil.which("gallery-dl")
        if not gallery_dl_bin:
            raise FileNotFoundError("gallery-dl not found")

        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return 1, "任务不存在。", []
            url = str(job.get("url") or "")
            cookie_file = str(job.get("cookie_file") or "")
            cookie_match_mode = str(job.get("cookie_match_mode") or "none")
            archive_enabled = bool(self._config.get("gallery_archive_enabled", True))
            archive_file_text = str(self._config.get("gallery_archive_file", DEFAULT_DOWNLOAD_CONFIG["gallery_archive_file"])).strip()

        temp_dir = (self.media_root / ".tiklocal-download-tmp" / job_id).resolve()
        temp_dir.mkdir(parents=True, exist_ok=True)
        log_file = temp_dir / "gallery-dl.log"

        cmd = [
            gallery_dl_bin,
            "--no-colors",
            "--directory",
            str(temp_dir),
            "--retries",
            "10",
            "--http-timeout",
            "30",
            "--sleep-429",
            "8",
        ]

        if archive_enabled:
            archive_path = self._expand_user_path(archive_file_text)
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            cmd.extend(["--download-archive", str(archive_path)])

        if cookie_file and cookie_match_mode in {"auto", "manual"}:
            cookie_path, error = self._resolve_cookie_path(cookie_file)
            if error:
                shutil.rmtree(temp_dir, ignore_errors=True)
                return 1, error, []
            cmd.extend(["--cookies", str(cookie_path)])

        cmd.extend(["--write-log", str(log_file), url])

        process = sp.Popen(
            cmd,
            stdout=sp.PIPE,
            stderr=sp.STDOUT,
            text=True,
            bufsize=1,
        )

        with self._lock:
            self._processes[job_id] = process

        cancel_event = self._cancel_events.get(job_id)
        error_message = ""

        stream = process.stdout
        if stream is not None:
            for raw_line in stream:
                line = raw_line.strip()
                if not line:
                    continue

                extracted_error = self._extract_error_line(line)
                if extracted_error:
                    error_message = extracted_error

                if cancel_event and cancel_event.is_set():
                    self._terminate_process(process)

        return_code = process.wait()

        try:
            if return_code != 0:
                if not error_message:
                    error_message = f"gallery-dl exited with code {return_code}."
                return return_code, error_message, []

            outputs = self._collect_gallery_outputs(temp_dir, excluded={log_file.resolve()})
            moved_outputs = [self._move_file_to_media_root(path) for path in outputs]
            moved_outputs = [path for path in moved_outputs if path]
            if not moved_outputs:
                return 1, "gallery-dl 未下载到可用文件。", []
            return 0, "", moved_outputs
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _update_progress(self, job_id: str, progress: dict[str, Any]) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job["status"] != "running":
                return

            if progress.get("percent") is not None:
                job["progress_percent"] = progress["percent"]
            if progress.get("eta_sec") is not None:
                job["eta_sec"] = progress["eta_sec"]

            self._persist_locked()

    def _persist_locked(self) -> None:
        jobs = [dict(self._jobs[job_id]) for job_id in self._job_order if job_id in self._jobs]
        self.history_store.save(jobs)

    def _mark_canceled_locked(self, job: dict[str, Any]) -> None:
        job["status"] = "canceled"
        job["finished_at"] = _utc_now_iso()
        job["error_message"] = "已取消。"
        job["eta_sec"] = None
        self._persist_locked()

    def _terminate_process(self, process: sp.Popen[str]) -> None:
        if process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=2)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def _parse_progress(self, line: str) -> dict[str, Any] | None:
        percent = None
        eta_sec = None

        percent_match = _PROGRESS_RE.search(line)
        if percent_match:
            try:
                percent = float(percent_match.group("percent"))
            except (TypeError, ValueError):
                percent = None

        eta_match = _ETA_RE.search(line)
        if eta_match:
            eta_sec = self._parse_eta_to_seconds(eta_match.group("eta"))

        if percent is None and eta_sec is None:
            return None

        return {"percent": percent, "eta_sec": eta_sec}

    def _parse_output_path(self, line: str) -> str:
        for pattern in _DESTINATION_PATTERNS:
            match = pattern.search(line)
            if match:
                path = match.group("path").strip().strip('"')
                return path
        return ""

    def _to_media_relative(self, path_text: str) -> str:
        if not path_text:
            return ""
        try:
            absolute = Path(path_text).resolve()
            media_root = self.media_root.resolve()
            if str(absolute).startswith(str(media_root)):
                return str(absolute.relative_to(media_root))
        except Exception:
            return ""
        return ""

    def _parse_eta_to_seconds(self, value: str) -> int | None:
        parts = value.split(":")
        if not parts:
            return None
        try:
            nums = [int(part) for part in parts]
        except ValueError:
            return None

        if len(nums) == 2:
            return nums[0] * 60 + nums[1]
        if len(nums) == 3:
            return nums[0] * 3600 + nums[1] * 60 + nums[2]
        return None

    def _normalize_execute_result(self, result: Any) -> tuple[int, str, list[str]]:
        if not isinstance(result, tuple):
            return 1, "下载器返回结果格式错误。", []

        return_code = _to_int(result[0]) if len(result) >= 1 else 1
        if return_code is None:
            return_code = 1
        error_message = str(result[1] or "") if len(result) >= 2 else ""
        raw_output = result[2] if len(result) >= 3 else ""

        if isinstance(raw_output, str):
            outputs = [raw_output] if raw_output else []
        elif isinstance(raw_output, list):
            outputs = [str(item).strip() for item in raw_output if str(item).strip()]
        else:
            outputs = []
        return return_code, error_message, outputs

    def _probe_binary(self, command: str) -> tuple[str | None, str]:
        binary_path = shutil.which(command)
        if not binary_path:
            return None, ""
        try:
            out = sp.check_output([binary_path, "--version"], text=True, timeout=3)
            return binary_path, (out or "").strip().splitlines()[0]
        except Exception:
            return binary_path, ""

    def _extract_error_line(self, line: str) -> str:
        lowered = line.lower()
        if "error:" in lowered:
            return line
        return ""

    def _expand_user_path(self, path_text: str) -> Path:
        return Path(path_text).expanduser()

    def _collect_gallery_outputs(self, temp_dir: Path, *, excluded: set[Path]) -> list[Path]:
        outputs: list[Path] = []
        for entry in temp_dir.rglob("*"):
            if not entry.is_file():
                continue
            resolved = entry.resolve()
            if resolved in excluded:
                continue
            if resolved.name.endswith(".part"):
                continue
            outputs.append(resolved)
        outputs.sort(key=lambda p: str(p))
        return outputs

    def _move_file_to_media_root(self, source_path: Path) -> str:
        if not source_path.exists() or not source_path.is_file():
            return ""

        target_name = source_path.name
        target = (self.media_root / target_name).resolve()
        target = self._next_available_path(target)
        try:
            source_path.replace(target)
        except OSError:
            shutil.move(str(source_path), str(target))
        return self._to_media_relative(str(target))

    def _next_available_path(self, path: Path) -> Path:
        if not path.exists():
            return path
        stem = path.stem
        suffix = path.suffix
        parent = path.parent
        idx = 1
        while True:
            candidate = parent / f"{stem} ({idx}){suffix}"
            if not candidate.exists():
                return candidate
            idx += 1

    def _resolve_cookie_choice(self, *, url: str, cookie_mode: str, cookie_file: str) -> tuple[str, str, str | None]:
        with self._lock:
            cookie_enabled = bool(self._config.get("cookie_enabled", True))
            cookie_dir_text = str(self._config.get("cookie_dir", DEFAULT_DOWNLOAD_CONFIG["cookie_dir"])).strip()

        if not cookie_enabled:
            return "", "none", None
        if cookie_mode == "none":
            return "", "none", None

        info = self.list_cookie_files()
        files = info.get("files") or []
        cookie_dir = self._expand_cookie_dir(cookie_dir_text)
        if not files:
            if cookie_mode == "manual":
                return "", "none", f"未找到 cookie 文件目录或文件: {cookie_dir}"
            return "", "none", None

        if cookie_mode == "manual":
            if not cookie_file:
                return "", "none", "手动模式缺少 cookie_file。"
            if cookie_file not in files:
                return "", "none", f"cookie 文件不存在: {cookie_file}"
            return cookie_file, "manual", None

        parsed = urlparse(url)
        host = (parsed.hostname or "").strip().lower()
        if not host:
            return "", "none", None

        lowered_files = {name.lower(): name for name in files}
        for candidate in _domain_candidates(host):
            hits = [lowered_files[key] for key in lowered_files if candidate in key]
            if hits:
                hits.sort(key=lambda item: (len(item), item.lower()))
                return hits[0], "auto", None
        return "", "none", None

    def _expand_cookie_dir(self, cookie_dir_text: str) -> Path:
        return Path(cookie_dir_text).expanduser()

    def _cookie_dir_path(self) -> Path:
        with self._lock:
            cookie_dir_text = str(self._config.get("cookie_dir", DEFAULT_DOWNLOAD_CONFIG["cookie_dir"])).strip()
        cookie_dir = self._expand_cookie_dir(cookie_dir_text)
        cookie_dir.mkdir(parents=True, exist_ok=True)
        return cookie_dir

    def _resolve_cookie_path(self, cookie_file: str) -> tuple[Path | None, str | None]:
        info = self.list_cookie_files()
        cookie_dir = Path(info["cookie_dir"]).expanduser().resolve()
        if cookie_file not in info.get("files", []):
            return None, f"cookie 文件不存在: {cookie_file}"
        path = (cookie_dir / cookie_file).resolve()
        try:
            path.relative_to(cookie_dir)
        except ValueError:
            return None, "cookie 文件路径非法。"
        if not path.exists() or not path.is_file():
            return None, f"cookie 文件不可用: {cookie_file}"
        return path, None
