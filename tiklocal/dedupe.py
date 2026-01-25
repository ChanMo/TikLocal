import hashlib
import sys
from pathlib import Path
from tiklocal.services import VIDEO_EXTENSIONS, IMAGE_EXTENSIONS


def compute_file_hash(path: Path, algorithm='sha256', chunk_size=8192) -> str | None:
    """计算文件哈希（支持大文件增量计算）"""
    try:
        hasher = hashlib.new(algorithm)
        with path.open('rb') as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        print(f"错误: 无法读取文件 {path}: {e}", file=sys.stderr)
        return None


def _get_file_extensions(file_type: str) -> set[str]:
    """根据类型返回文件扩展名集合"""
    if file_type == 'video':
        return VIDEO_EXTENSIONS
    elif file_type == 'image':
        return IMAGE_EXTENSIONS
    else:  # 'all'
        return VIDEO_EXTENSIONS | IMAGE_EXTENSIONS


def _scan_files(root: Path, extensions: set[str]) -> list[Path]:
    """递归扫描指定扩展名的文件"""
    files = []
    for ext in extensions:
        files.extend(root.glob(f'**/*{ext}'))
        files.extend(root.glob(f'**/*{ext.upper()}'))
    return files


def _print_progress(current: int, total: int, prefix: str = '') -> None:
    """进度条显示"""
    width = 28
    filled = int(width * current / total) if total else width
    bar = '█' * filled + '─' * (width - filled)
    percent = (current / total * 100) if total else 100
    sys.stdout.write(f"\r{prefix}[{bar}] {current}/{total} {percent:5.1f}%")
    sys.stdout.flush()


def find_duplicates(
    media_root: Path,
    file_type: str = 'all',
    algorithm: str = 'sha256',
    show_progress: bool = True
) -> dict[str, list[Path]]:
    """
    查找重复文件
    返回：{hash: [path1, path2, ...]}，只包含有重复的组
    """
    extensions = _get_file_extensions(file_type)
    files = _scan_files(media_root, extensions)
    total = len(files)

    if show_progress:
        print(f'扫描到 {total} 个文件，开始计算哈希值...')

    hash_map = {}  # {hash: [path1, path2, ...]}
    processed = 0

    for file_path in files:
        file_hash = compute_file_hash(file_path, algorithm)
        if file_hash:
            hash_map.setdefault(file_hash, []).append(file_path)

        processed += 1
        if show_progress:
            _print_progress(processed, total, prefix='计算中 ')

    if show_progress:
        print()  # 换行

    # 只返回有重复的组（至少2个文件）
    duplicates = {h: paths for h, paths in hash_map.items() if len(paths) > 1}
    return duplicates


def select_files_to_keep(
    duplicate_groups: dict[str, list[Path]],
    strategy: str = 'oldest'
) -> tuple[list[Path], list[Path]]:
    """
    选择要保留和删除的文件
    返回：(to_keep, to_delete)
    """
    to_keep = []
    to_delete = []

    for file_hash, paths in duplicate_groups.items():
        if strategy == 'oldest':
            # 按 mtime 排序，保留最早的
            sorted_paths = sorted(paths, key=lambda p: p.stat().st_mtime)
        elif strategy == 'newest':
            # 保留最新的
            sorted_paths = sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True)
        elif strategy == 'shortest_path':
            # 保留路径最短的（通常在根目录）
            sorted_paths = sorted(paths, key=lambda p: len(str(p)))
        else:
            sorted_paths = paths

        # 第一个保留，其余删除
        to_keep.append(sorted_paths[0])
        to_delete.extend(sorted_paths[1:])

    return to_keep, to_delete


def format_size(size_bytes: int) -> str:
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def delete_files(
    files: list[Path],
    dry_run: bool = True,
    show_progress: bool = True
) -> dict:
    """删除文件"""
    total = len(files)
    deleted = 0
    failed = 0
    total_size = sum(f.stat().st_size for f in files if f.exists())

    if dry_run:
        if show_progress:
            print(f'\n【预演模式】将删除以下 {total} 个文件（共 {format_size(total_size)}）：')
            for f in files:
                size = format_size(f.stat().st_size) if f.exists() else '0 B'
                print(f'  - {f} ({size})')
        return {'deleted': 0, 'failed': 0, 'total': total, 'size_freed': 0}

    if show_progress:
        print(f'\n开始删除 {total} 个文件...')

    processed = 0
    for f in files:
        try:
            if f.exists():
                f.unlink()
                deleted += 1
        except Exception as e:
            failed += 1
            if show_progress:
                print(f"\n警告: 删除失败 {f}: {e}", file=sys.stderr)

        processed += 1
        if show_progress:
            _print_progress(processed, total, prefix='删除中 ')

    if show_progress:
        print()

    return {
        'deleted': deleted,
        'failed': failed,
        'total': total,
        'size_freed': total_size
    }


def run_dedupe(
    media_root: Path,
    file_type: str = 'all',
    algorithm: str = 'sha256',
    keep_strategy: str = 'oldest',
    dry_run: bool = True,
    auto_confirm: bool = False
) -> dict:
    """
    重复文件检测与清理的主流程
    """
    # 1. 查找重复文件
    print(f"开始扫描目录: {media_root}")
    print(f"文件类型: {file_type}  |  哈希算法: {algorithm}  |  保留策略: {keep_strategy}")

    duplicates = find_duplicates(media_root, file_type, algorithm, show_progress=True)

    if not duplicates:
        print("\n✓ 未发现重复文件")
        return {'duplicates': 0, 'deleted': 0}

    # 2. 统计信息
    total_duplicates = sum(len(paths) - 1 for paths in duplicates.values())
    total_groups = len(duplicates)
    print(f"\n发现 {total_groups} 组重复文件，共 {total_duplicates} 个重复副本")

    # 3. 选择要删除的文件
    to_keep, to_delete = select_files_to_keep(duplicates, keep_strategy)

    # 4. 显示详细信息
    print(f"\n重复文件详情：")
    for file_hash, paths in list(duplicates.items())[:5]:  # 只显示前5组
        print(f"\n  哈希: {file_hash[:16]}... ({len(paths)} 个文件)")
        for p in paths:
            status = "✓ 保留" if p in to_keep else "✗ 删除"
            size = format_size(p.stat().st_size) if p.exists() else '0 B'
            print(f"    [{status}] {p} ({size})")

    if len(duplicates) > 5:
        print(f"\n  ... 还有 {len(duplicates) - 5} 组未显示")

    # 5. 删除文件
    if dry_run:
        stats = delete_files(to_delete, dry_run=True, show_progress=True)
        print(f"\n提示: 使用 --execute 参数执行实际删除")
    else:
        if not auto_confirm:
            print(f"\n警告: 即将删除 {len(to_delete)} 个文件!")
            confirm = input("确认继续？(yes/no): ").strip().lower()
            if confirm not in ('yes', 'y'):
                print("操作已取消")
                return {'duplicates': total_duplicates, 'deleted': 0}

        stats = delete_files(to_delete, dry_run=False, show_progress=True)
        print(f"\n✓ 删除完成: {stats['deleted']} 个文件，释放 {format_size(stats['size_freed'])} 空间")
        if stats['failed'] > 0:
            print(f"  失败: {stats['failed']} 个文件", file=sys.stderr)

    return {
        'duplicates': total_duplicates,
        'deleted': stats.get('deleted', 0),
        'failed': stats.get('failed', 0)
    }
