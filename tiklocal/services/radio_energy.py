"""Loudness envelopes that let Radio visuals breathe with the music.

An envelope is a track's short-term loudness sampled every ``HOP_SECONDS``, scaled to
0..255 against the track's own loud passages: choruses sit near the top and quiet
intros near the bottom, whatever the mastering level. A five-minute track is about
1,200 values. Envelopes are computed once and cached as small JSON files, invalidated
when the source file changes.

Audio is decoded with ffmpeg when it is installed; plain WAV files are read with the
standard library, so the feature degrades to "no envelope" rather than failing.
"""

from __future__ import annotations

import array
import hashlib
import json
import math
import os
import shutil
import subprocess as sp
import sys
import tempfile
import wave
from pathlib import Path
from typing import Callable, Iterator

from tiklocal.paths import get_data_dir

HOP_SECONDS = 0.25
DECODE_RATE = 4000
WINDOW_DB = 24.0
LOUD_PERCENTILE = 0.95
MAX_HOPS = 4 * 60 * 60 * 4
FORMAT_VERSION = 1


class RadioEnergyService:
    def __init__(self, library_service, cache_dir: Path | None = None):
        self.library = library_service
        self.cache_dir = cache_dir or get_data_dir() / 'radio_energy'

    def get_envelope(self, uri: str) -> dict | None:
        """Return ``{'hop': seconds, 'values': [0..255, ...]}`` or None when unavailable."""
        source = self.library.resolve_path(uri)
        if source is None or not source.is_file():
            return None
        cache = self._cache_path(uri)
        cached = self._read_cache(cache, source)
        if cached is not None:
            return cached
        powers = decode_powers(source)
        if not powers:
            return None
        envelope = {'version': FORMAT_VERSION, 'hop': HOP_SECONDS, 'values': envelope_values(powers)}
        self._write_cache(cache, envelope)
        return envelope

    def _cache_path(self, uri: str) -> Path:
        key = self.library.canonicalize_uri(uri)
        return self.cache_dir / (hashlib.sha1(key.encode('utf-8')).hexdigest() + '.json')

    @staticmethod
    def _read_cache(cache: Path, source: Path) -> dict | None:
        try:
            if cache.stat().st_mtime_ns < source.stat().st_mtime_ns:
                return None
            payload = json.loads(cache.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None
        if not isinstance(payload, dict) or payload.get('version') != FORMAT_VERSION:
            return None
        return payload

    def _write_cache(self, cache: Path, envelope: dict) -> None:
        # Publish atomically so a concurrent reader never sees a partial file.
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(dir=self.cache_dir, suffix='.tmp')
        except OSError:
            return
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
                json.dump(envelope, handle, separators=(',', ':'))
            os.replace(temporary, cache)
        except OSError:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def envelope_values(powers: list[float]) -> list[int]:
    """Map mean-square powers to 0..255 within a fixed dB window below the loud level."""
    levels = [10 * math.log10(power) if power > 1e-10 else None for power in powers]
    audible = sorted(level for level in levels if level is not None)
    if not audible:
        return [0] * len(powers)
    loud = audible[min(len(audible) - 1, int(len(audible) * LOUD_PERCENTILE))]
    floor = loud - WINDOW_DB
    values = []
    for level in levels:
        if level is None:
            values.append(0)
            continue
        scaled = (level - floor) / WINDOW_DB
        values.append(round(min(1.0, max(0.0, scaled)) * 255))
    return values


def decode_powers(source: Path) -> list[float] | None:
    """Mean-square power per hop, from ffmpeg when available, else from a WAV file."""
    if shutil.which('ffmpeg'):
        powers = _ffmpeg_powers(source)
        if powers:
            return powers
    if source.suffix.lower() == '.wav':
        return _wav_powers(source)
    return None


def _ffmpeg_powers(source: Path) -> list[float] | None:
    command = [
        'ffmpeg', '-v', 'error', '-nostdin', '-i', str(source),
        '-vn', '-ac', '1', '-ar', str(DECODE_RATE), '-f', 's16le', '-acodec', 'pcm_s16le', '-',
    ]
    try:
        process = sp.Popen(command, stdout=sp.PIPE, stderr=sp.DEVNULL)
    except OSError:
        return None
    hop_bytes = int(DECODE_RATE * HOP_SECONDS) * 2
    try:
        powers = _hop_powers(lambda: process.stdout.read(hop_bytes), stride=1)
        process.stdout.close()
        process.wait(timeout=60)
    except (OSError, sp.SubprocessError):
        process.kill()
        return None
    return powers if process.returncode == 0 else None


def _wav_powers(source: Path) -> list[float] | None:
    try:
        with wave.open(str(source), 'rb') as handle:
            if handle.getsampwidth() != 2:
                return None
            rate = handle.getframerate()
            channels = handle.getnchannels()
            frames_per_hop = max(1, int(rate * HOP_SECONDS))
            # Power is estimated from a subsample of roughly DECODE_RATE values per second.
            stride = max(1, round(rate * channels / DECODE_RATE))
            return _hop_powers(lambda: handle.readframes(frames_per_hop), stride=stride)
    except (OSError, EOFError, wave.Error):
        return None


def _hop_powers(read: Callable[[], bytes], stride: int) -> list[float]:
    powers = []
    for samples in _chunks(read):
        picked = samples[::stride] if stride > 1 else samples
        if not picked:
            continue
        powers.append(sum(value * value for value in picked) / (len(picked) * 32768.0 * 32768.0))
        if len(powers) >= MAX_HOPS:
            break
    return powers


def _chunks(read: Callable[[], bytes]) -> Iterator[array.array]:
    while True:
        data = read()
        if not data:
            return
        if len(data) % 2:
            data = data[:-1]
        samples = array.array('h', data)
        if sys.byteorder == 'big':
            samples.byteswap()
        yield samples
