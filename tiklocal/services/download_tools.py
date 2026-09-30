"""Command lines and output parsing for the external download tools."""
import re
import shutil
import subprocess as sp
from pathlib import Path
from typing import Any

_PROGRESS_RE = re.compile(r"\[download\]\s+(?P<percent>\d+(?:\.\d+)?)%")
_ETA_RE = re.compile(r"ETA\s+(?P<eta>[0-9:]+)")
_DESTINATION_PATTERNS = [
    re.compile(r"^\[download\] Destination: (?P<path>.+)$"),
    re.compile(r'^\[Merger\] Merging formats into "(?P<path>.+)"$'),
    re.compile(r'^\[ExtractAudio\] Destination: (?P<path>.+)$'),
]
# Keeps the fields source_from_filename reads back when no source was recorded.
YT_DLP_OUTPUT_TEMPLATE = (
    "%(extractor_key|na)s__%(uploader_id|na).24B__%(display_id|na)s__%(id|na)s__%(upload_date|na)s__%(autonumber)02d.%(ext)s"
)


def yt_dlp_command(binary: str, media_root: Path, url: str, *, allow_playlist: bool,
                   cookie_path: Path | None) -> list[str]:
    cmd = [
        binary,
        "--newline",
        "--restrict-filenames",
        "--merge-output-format", "mp4",
        "--write-info-json",
        "--continue",
        "--retries", "10",
        "--fragment-retries", "10",
        "--file-access-retries", "5",
        "--socket-timeout", "30",
        "-o", str(media_root / YT_DLP_OUTPUT_TEMPLATE),
    ]
    if not allow_playlist:
        cmd.append("--no-playlist")
    if cookie_path:
        cmd.extend(["--cookies", str(cookie_path)])
    cmd.append(url)
    return cmd


def gallery_dl_command(binary: str, temp_dir: Path, log_file: Path, url: str, *,
                       archive_path: Path | None, cookie_path: Path | None) -> list[str]:
    cmd = [
        binary,
        "--no-colors",
        "--directory", str(temp_dir),
        "--retries", "10",
        "--http-timeout", "30",
        "--sleep-429", "8",
    ]
    if archive_path:
        cmd.extend(["--download-archive", str(archive_path)])
    if cookie_path:
        cmd.extend(["--cookies", str(cookie_path)])
    cmd.extend(["--write-log", str(log_file), url])
    return cmd


def parse_eta_seconds(value: str) -> int | None:
    try:
        nums = [int(part) for part in value.split(":")]
    except ValueError:
        return None
    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    if len(nums) == 3:
        return nums[0] * 3600 + nums[1] * 60 + nums[2]
    return None


def parse_progress(line: str) -> dict[str, Any] | None:
    percent_match = _PROGRESS_RE.search(line)
    percent = float(percent_match.group("percent")) if percent_match else None
    eta_match = _ETA_RE.search(line)
    eta_sec = parse_eta_seconds(eta_match.group("eta")) if eta_match else None
    if percent is None and eta_sec is None:
        return None
    return {"percent": percent, "eta_sec": eta_sec}


def parse_output_path(line: str) -> str:
    for pattern in _DESTINATION_PATTERNS:
        match = pattern.search(line)
        if match:
            return match.group("path").strip().strip('"')
    return ""


def error_line(line: str) -> str:
    return line if "error:" in line.lower() else ""


def probe_binary(command: str) -> tuple[str | None, str]:
    binary_path = shutil.which(command)
    if not binary_path:
        return None, ""
    try:
        out = sp.check_output([binary_path, "--version"], text=True, timeout=3)
        return binary_path, (out or "").strip().splitlines()[0]
    except Exception:
        return binary_path, ""


def collect_gallery_outputs(temp_dir: Path, *, excluded: set[Path]) -> list[Path]:
    outputs = []
    for entry in temp_dir.rglob("*"):
        if not entry.is_file():
            continue
        resolved = entry.resolve()
        if resolved not in excluded and not resolved.name.endswith(".part"):
            outputs.append(resolved)
    outputs.sort(key=lambda p: str(p))
    return outputs


def next_available_path(path: Path) -> Path:
    idx = 1
    candidate = path
    while candidate.exists():
        candidate = path.parent / f"{path.stem} ({idx}){path.suffix}"
        idx += 1
    return candidate
