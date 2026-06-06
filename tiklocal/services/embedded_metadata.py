from __future__ import annotations

from pathlib import Path
from typing import Any


JPEG_SOI = b"\xff\xd8"
JPEG_SOS = 0xDA
JPEG_EOI = 0xD9
JPEG_COM = 0xFE


def _decode_comment(data: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(encoding).strip("\x00\r\n\t ")
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace").strip("\x00\r\n\t ")


def read_jpeg_comments(path: Path) -> list[str]:
    comments: list[str] = []
    try:
        data = path.read_bytes()
    except OSError:
        return comments
    if not data.startswith(JPEG_SOI):
        return comments

    idx = 2
    size = len(data)
    while idx + 4 <= size:
        if data[idx] != 0xFF:
            idx += 1
            continue
        while idx < size and data[idx] == 0xFF:
            idx += 1
        if idx >= size:
            break

        marker = data[idx]
        idx += 1
        if marker in {JPEG_SOS, JPEG_EOI} or 0xD0 <= marker <= 0xD7:
            break
        if idx + 2 > size:
            break

        segment_length = int.from_bytes(data[idx:idx + 2], "big")
        if segment_length < 2:
            break
        segment_start = idx + 2
        segment_end = segment_start + segment_length - 2
        if segment_end > size:
            break

        if marker == JPEG_COM:
            comment = _decode_comment(data[segment_start:segment_end])
            if comment:
                comments.append(comment)
        idx = segment_end
    return comments


def parse_prompt_model_comment(comment: str) -> dict[str, str] | None:
    text = str(comment or "").strip()
    if not text.startswith("Prompt:"):
        return None

    model_marker = " | Model:"
    model_at = text.find(model_marker)
    if model_at < 0:
        prompt = text[len("Prompt:"):].strip()
        return {"prompt": prompt, "model": ""} if prompt else None

    prompt = text[len("Prompt:"):model_at].strip()
    rest = text[model_at + len(model_marker):]
    next_marker_at = len(rest)
    for marker in (" | GeneratedBy:", " | GeneratedAt:", " | "):
        found = rest.find(marker)
        if found >= 0:
            next_marker_at = min(next_marker_at, found)
    model = rest[:next_marker_at].strip()
    if not prompt and not model:
        return None
    return {"prompt": prompt, "model": model}


def read_embedded_generation(path: Path) -> dict[str, Any] | None:
    if path.suffix.lower() not in {".jpg", ".jpeg"}:
        return None
    for comment in read_jpeg_comments(path):
        parsed = parse_prompt_model_comment(comment)
        if parsed:
            return {
                "source_format": "jpeg_comment",
                "prompt": parsed.get("prompt", ""),
                "model": parsed.get("model", ""),
            }
    return None
