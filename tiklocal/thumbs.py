import argparse
import datetime
import hashlib
import json
import os
import subprocess as sp
import sys
from pathlib import Path
import mimetypes
from tiklocal.paths import get_thumbnails_dir, get_thumbs_map_path, get_data_dir


def _thumb_key(rel_path: str) -> str:
    return hashlib.sha1(rel_path.encode('utf-8', errors='ignore')).hexdigest() + '.jpg'


def _thumb_path(rel_path: str) -> Path:
    return get_thumbnails_dir() / _thumb_key(rel_path)


def _map_path() -> Path:
    return get_thumbs_map_path()


def _load_map() -> dict:
    p = _map_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding='utf-8'))
        except Exception:
            return {}
    return {}


def _save_map(data: dict) -> None:
    p = _map_path()
    p.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')


def _probe_duration(path: Path) -> float | None:
    # 尝试用 ffprobe 获取时长（秒）
    cmd = [
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1', str(path)
    ]
    try:
        out = sp.check_output(cmd, stderr=sp.DEVNULL, timeout=10)
        val = float(out.decode().strip())
        if val > 0:
            return val
    except Exception:
        return None
    return None


def _ffmpeg_capture(input_path: Path, output_path: Path, ts: float | None) -> bool:
    candidates: list[float]
    if ts is not None and ts >= 0:
        candidates = [ts]
    else:
        dur = _probe_duration(input_path)
        if dur and dur > 1:
            t = max(1.0, min(dur - 1.0, dur * 0.2))
            candidates = [t, 5.0, 1.0, 0.1]
        else:
            candidates = [5.0, 1.0, 0.1]

    for t in candidates:
        cmd = [
            'ffmpeg', '-y', '-ss', str(max(0.0, float(t))), '-i', str(input_path),
            '-frames:v', '1', '-vf', 'scale=-1:360:force_original_aspect_ratio=decrease',
            '-q:v', '3', str(output_path)
        ]
        try:
            sp.run(cmd, stdout=sp.DEVNULL, stderr=sp.DEVNULL, timeout=30)
            if output_path.exists() and output_path.stat().st_size > 0:
                return True
        except Exception:
            continue
    return False


VIDEO_EXTS = {'.mp4', '.webm', '.mov', '.mkv', '.avi', '.m4v'}


def _is_video(path: Path) -> bool:
    suf = path.suffix.lower()
    if suf in VIDEO_EXTS:
        return True
    try:
        mime = mimetypes.guess_type(path.name)[0] or ''
    except Exception:
        mime = ''
    return mime.startswith('video/')


def _iter_videos(root: Path) -> list[Path]:
    videos: list[Path] = []
    # 先按扩展名快速匹配，再做 mimetype 二次校验
    for pattern in ('*.mp4', '*.webm', '*.mov', '*.mkv', '*.avi', '*.m4v',
                    '*.MP4', '*.WEBM', '*.MOV', '*.MKV', '*.AVI', '*.M4V'):
        for p in root.glob(f'**/{pattern}'):
            if _is_video(p):
                videos.append(p)
    return videos


def _print_progress(current: int, total: int, prefix: str = '') -> None:
    width = 28
    filled = int(width * current / total) if total else width
    bar = '█' * filled + '─' * (width - filled)
    percent = (current / total * 100) if total else 100
    sys.stdout.write(f"\r{prefix}[{bar}] {current}/{total} {percent:5.1f}%")
    sys.stdout.flush()


def generate_thumbnails(media_root: str | Path, overwrite: bool = False, limit: int = 0, show_progress: bool = True) -> dict:
    root = Path(media_root)
    mapping = _load_map()
    videos = _iter_videos(root)
    total = len(videos)
    done = 0
    skipped = 0
    failed = 0
    limit_left = limit if limit and limit > 0 else None

    if show_progress:
        print(f'数据目录: {get_data_dir()}')
        print(f'发现视频 {total} 个，缩略图目录：{get_thumbnails_dir()}')

    processed = 0
    for vp in videos:
        rel = str(vp.relative_to(root))
        out = _thumb_path(rel)
        # 二次校验，防御性判断
        if not _is_video(vp):
            skipped += 1
            processed += 1
            if show_progress:
                _print_progress(processed, total, prefix='生成中 ')
            continue

        if out.exists() and not overwrite:
            skipped += 1
            processed += 1
            if show_progress:
                _print_progress(processed, total, prefix='生成中 ')
            if limit_left is not None:
                limit_left -= 1
                if limit_left <= 0:
                    break
            continue

        ok = _ffmpeg_capture(vp, out, mapping.get(rel, {}).get('ts'))
        if ok:
            mapping[rel] = {
                'ts': mapping.get(rel, {}).get('ts'),
                'updated_at': datetime.datetime.now().isoformat(timespec='seconds')
            }
            done += 1
        else:
            failed += 1

        processed += 1
        if show_progress:
            _print_progress(processed, total, prefix='生成中 ')

        if limit_left is not None:
            limit_left -= 1
            if limit_left <= 0:
                break

    _save_map(mapping)
    if show_progress:
        print()  # 换行
        print(f'完成：生成 {done}，跳过 {skipped}，失败 {failed}，总计 {total}')
    return {
        'total': total,
        'generated': done,
        'skipped': skipped,
        'failed': failed,
    }


def clean_thumbnails(media_root: str | Path, show_progress: bool = True) -> dict:
    root = Path(media_root)
    mapping = _load_map()
    keys = list(mapping.keys())
    total = len(keys)
    removed = 0
    kept = 0

    if show_progress:
        print(f'开始清理：映射 {total} 条')

    for i, rel in enumerate(keys, start=1):
        target = (root / rel)
        thumb = _thumb_path(rel)
        invalid = (not target.exists()) or (not _is_video(target))
        if invalid:
            try:
                if thumb.exists():
                    thumb.unlink()
            except Exception:
                pass
            mapping.pop(rel, None)
            removed += 1
        else:
            kept += 1
        if show_progress:
            _print_progress(i, total, prefix='清理中 ')

    _save_map(mapping)
    if show_progress:
        print()  # 换行
        print(f'清理完成：保留 {kept}，移除 {removed}，总计 {total}')
    return {'kept': kept, 'removed': removed, 'total': total}


def verify_thumbnails(media_root: str | Path) -> dict:
    root = Path(media_root)
    mapping = _load_map()
    videos = _iter_videos(root)
    video_set = {str(p.relative_to(root)) for p in videos}

    mapped = 0
    invalid = 0
    missing = 0

    for rel, meta in mapping.items():
        thumb = _thumb_path(rel)
        if rel in video_set and thumb.exists():
            mapped += 1
        else:
            invalid += 1

    for rel in video_set:
        if not _thumb_path(rel).exists():
            missing += 1

    print(f"视频总数: {len(video_set)}  | 已有缩略图: {mapped}  | 异常映射: {invalid}  | 待生成: {missing}")
    return {
        'videos': len(video_set),
        'mapped': mapped,
        'invalid': invalid,
        'missing': missing,
    }


def main():
    parser = argparse.ArgumentParser(description='TikLocal 缩略图工具')
    parser.add_argument('media_root', nargs='?', help='媒体根目录（可省略以使用环境变量 MEDIA_ROOT）')
    parser.add_argument('--overwrite', action='store_true', help='已存在时覆盖重建')
    parser.add_argument('--limit', type=int, default=0, help='最多处理多少个（0 表示全部）')
    parser.add_argument('--clean', action='store_true', help='清理非视频/孤儿缩略图与映射')
    parser.add_argument('--verify', action='store_true', help='仅校验覆盖率与异常，不修改')
    args = parser.parse_args()

    media_root = args.media_root or os.environ.get('MEDIA_ROOT')
    if not media_root:
        parser.error('必须指定媒体目录：位置参数或环境变量 MEDIA_ROOT')

    root = Path(media_root)
    if not root.exists() or not root.is_dir():
        parser.error(f'媒体目录不可用：{media_root}')

    if args.clean:
        clean_thumbnails(root, show_progress=True)
        return
    if args.verify:
        verify_thumbnails(root)
        return
    generate_thumbnails(root, overwrite=args.overwrite, limit=args.limit, show_progress=True)


if __name__ == '__main__':
    main()
