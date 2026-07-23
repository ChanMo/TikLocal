"""Submit a one-off OpenRouter image-to-video job and save the MP4 locally."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests


API_URL = "https://openrouter.ai/api/v1/videos"
DEFAULT_MODEL = "x-ai/grok-imagine-video-1.5"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a short video from a first-frame image via OpenRouter. "
            "The image URL must be a provider-accessible HTTPS URL."
        )
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--image-url", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--output", default="outputs/grok-image-to-video.mp4")
    parser.add_argument("--duration", type=int, default=4)
    parser.add_argument("--resolution", default="720p")
    parser.add_argument(
        "--aspect-ratio",
        help="Optional provider-supported ratio. Omit to follow the first frame.",
    )
    parser.add_argument("--poll-interval", type=int, default=30)
    parser.add_argument("--max-polls", type=int, default=60)
    parser.add_argument("--generate-audio", action="store_true")
    return parser.parse_args()


def request_json(
    method: str,
    url: str,
    headers: dict[str, str],
    **kwargs: Any,
) -> dict[str, Any]:
    response = requests.request(method, url, headers=headers, timeout=60, **kwargs)
    if not response.ok:
        raise RuntimeError(f"{method} {url} failed: {response.status_code} {response.text}")
    return response.json()


def submit_job(args: argparse.Namespace, headers: dict[str, str]) -> dict[str, Any]:
    payload = {
        "model": args.model,
        "prompt": args.prompt,
        "duration": args.duration,
        "resolution": args.resolution,
        "generate_audio": args.generate_audio,
        "frame_images": [
            {
                "type": "image_url",
                "image_url": {"url": args.image_url},
                "frame_type": "first_frame",
            }
        ],
    }
    if args.aspect_ratio:
        payload["aspect_ratio"] = args.aspect_ratio
    return request_json("POST", API_URL, headers, json=payload)


def wait_for_completion(
    job: dict[str, Any],
    headers: dict[str, str],
    poll_interval: int,
    max_polls: int,
) -> dict[str, Any]:
    current = job
    terminal_failures = {"failed", "cancelled", "expired"}

    for attempt in range(max_polls + 1):
        status = current.get("status")
        print(f"status[{attempt}]: {status}", flush=True)

        if status == "completed":
            return current
        if status in terminal_failures:
            raise RuntimeError(f"Video generation ended with {status}: {current}")

        polling_url = current.get("polling_url")
        if not polling_url:
            raise RuntimeError(f"Video job did not include polling_url: {current}")

        if attempt == max_polls:
            break

        time.sleep(poll_interval)
        current = request_json("GET", polling_url, headers)

    raise TimeoutError(f"Video generation did not complete after {max_polls} polls.")


def download_video(job: dict[str, Any], output_path: Path, headers: dict[str, str]) -> None:
    video_url = (job.get("unsigned_urls") or [None])[0]
    if not video_url:
        video_url = f"{API_URL}/{job['id']}/content?index=0"

    request_headers = headers if video_url.startswith("https://openrouter.ai/api/") else {}
    response = requests.get(video_url, headers=request_headers, timeout=180)
    if not response.ok:
        raise RuntimeError(
            f"Download failed: {response.status_code} {response.text[:500]}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(response.content)
    print(f"saved: {output_path} ({len(response.content)} bytes)", flush=True)


def main() -> int:
    args = parse_args()
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("OPENROUTER_API_KEY is not set.", file=sys.stderr)
        return 2

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    job = submit_job(args, headers)
    print(f"submitted: {job.get('id')} ({job.get('status')})", flush=True)
    completed = wait_for_completion(job, headers, args.poll_interval, args.max_polls)
    download_video(completed, Path(args.output), headers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
