import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from tiklocal.paths import get_thumbs_map_path, get_data_dir
from tiklocal.services.library import LibraryService, VIDEO_EXTENSIONS
from tiklocal.services.thumbnail import ThumbnailService


def _load_map() -> dict:
    p = get_thumbs_map_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding='utf-8'))
        except Exception:
            return {}
    return {}


def _save_map(data: dict) -> None:
    p = get_thumbs_map_path()
    p.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')


def _print_progress(current: int, total: int, prefix: str = '') -> None:
    width = 28
    filled = int(width * current / total) if total else width
    bar = '█' * filled + '─' * (width - filled)
    percent = (current / total * 100) if total else 100
    sys.stdout.write(f"\r{prefix}[{bar}] {current}/{total} {percent:5.1f}%")
    sys.stdout.flush()


def generate_thumbnails(media_root: str | Path, overwrite: bool = False, limit: int = 0, show_progress: bool = True) -> dict:
    library = LibraryService(media_root)
    service = ThumbnailService(library.media_root, library)
    mapping = _load_map()
    videos = library.scan_videos()
    stats = {'total': len(videos), 'generated': 0, 'skipped': 0, 'failed': 0}
    if show_progress:
        print(f'数据目录: {get_data_dir()}')
        print(f'发现视频 {len(videos)} 个，缩略图目录：{service.thumb_dir}')
    for index, path in enumerate(videos[:limit] if limit > 0 else videos, start=1):
        uri = library.get_relative_path(path)
        if not overwrite and service.cached_thumbnail(uri):
            stats['skipped'] += 1
        else:
            previous = mapping.get(uri) or mapping.get(library.relative_path_for_uri(uri)) or {}
            timestamp = previous.get('ts')
            generated = service.generate_thumbnail(uri, timestamp=timestamp, auto_timestamp=True)
            if generated:
                mapping[uri] = {'ts': timestamp, 'updated_at': datetime.datetime.now().isoformat(timespec='seconds')}
                stats['generated'] += 1
            else:
                stats['failed'] += 1
        if show_progress:
            _print_progress(index, len(videos), prefix='生成中 ')
    _save_map(mapping)
    if show_progress:
        print(f"\n完成：生成 {stats['generated']}，跳过 {stats['skipped']}，失败 {stats['failed']}，总计 {stats['total']}")
    return stats


def clean_thumbnails(media_root: str | Path, show_progress: bool = True) -> dict:
    library = LibraryService(media_root)
    service = ThumbnailService(library.media_root, library)
    mapping = _load_map()
    total, removed = len(mapping), 0
    for index, uri in enumerate(list(mapping), start=1):
        source = library.source_for_uri(uri)
        # A single-root CLI invocation cannot clean another source or an offline source.
        if source is None or not source.path.is_dir():
            continue
        target = library.resolve_path(uri)
        if target is None or not target.is_file() or target.suffix.lower() not in VIDEO_EXTENSIONS:
            service.delete_thumbnail(uri)
            mapping.pop(uri)
            removed += 1
        if show_progress:
            _print_progress(index, total, prefix='清理中 ')
    _save_map(mapping)
    if show_progress:
        print(f'\n清理完成：保留 {total - removed}，移除 {removed}，总计 {total}')
    return {'kept': total - removed, 'removed': removed, 'total': total}


def verify_thumbnails(media_root: str | Path) -> dict:
    library = LibraryService(media_root)
    service = ThumbnailService(library.media_root, library)
    mapping = _load_map()
    videos = {library.get_relative_path(path) for path in library.scan_videos()}
    cached = {uri for uri in videos if service.cached_thumbnail(uri)}
    invalid = sum(library.canonicalize_uri(uri) not in cached for uri in mapping if library.source_for_uri(uri))
    print(f"视频总数: {len(videos)}  | 已有缩略图: {len(cached)}  | 异常映射: {invalid}  | 待生成: {len(videos - cached)}")
    return {'videos': len(videos), 'mapped': len(cached), 'invalid': invalid, 'missing': len(videos - cached)}


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
