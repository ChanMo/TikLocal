import hashlib
import sys
from pathlib import Path
from tiklocal.services.library import VIDEO_EXTENSIONS, IMAGE_EXTENSIONS


def compute_file_hash(path: Path, algorithm='sha256', chunk_size=8192) -> str | None:
    """Calculate a file hash incrementally to support large files."""
    try:
        hasher = hashlib.new(algorithm)
        with path.open('rb') as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        print(f"Error: Unable to read {path}: {e}", file=sys.stderr)
        return None


def _get_file_extensions(file_type: str) -> set[str]:
    """Return the file extensions for a media type."""
    if file_type == 'video':
        return VIDEO_EXTENSIONS
    elif file_type == 'image':
        return IMAGE_EXTENSIONS
    else:  # 'all'
        return VIDEO_EXTENSIONS | IMAGE_EXTENSIONS


def _scan_files(root: Path, extensions: set[str]) -> list[Path]:
    """Recursively scan for files with the requested extensions."""
    files = []
    for ext in extensions:
        files.extend(root.glob(f'**/*{ext}'))
        files.extend(root.glob(f'**/*{ext.upper()}'))
    return files


def _print_progress(current: int, total: int, prefix: str = '') -> None:
    """Display a progress bar."""
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
    Find duplicate files.
    Return {hash: [path1, path2, ...]} for duplicate groups only.
    """
    extensions = _get_file_extensions(file_type)
    files = _scan_files(media_root, extensions)
    total = len(files)

    if show_progress:
        print(f'Found {total} files. Calculating hashes...')

    hash_map = {}  # {hash: [path1, path2, ...]}
    processed = 0

    for file_path in files:
        file_hash = compute_file_hash(file_path, algorithm)
        if file_hash:
            hash_map.setdefault(file_hash, []).append(file_path)

        processed += 1
        if show_progress:
            _print_progress(processed, total, prefix='Hashing ')

    if show_progress:
        print()

    # Return groups with at least two files.
    duplicates = {h: paths for h, paths in hash_map.items() if len(paths) > 1}
    return duplicates


def select_files_to_keep(
    duplicate_groups: dict[str, list[Path]],
    strategy: str = 'oldest'
) -> tuple[list[Path], list[Path]]:
    """
    Select the files to keep and delete.
    Return (to_keep, to_delete).
    """
    to_keep = []
    to_delete = []

    for file_hash, paths in duplicate_groups.items():
        if strategy == 'oldest':
            # Keep the oldest mtime.
            sorted_paths = sorted(paths, key=lambda p: p.stat().st_mtime)
        elif strategy == 'newest':
            # Keep the newest file.
            sorted_paths = sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True)
        elif strategy == 'shortest_path':
            # Keep the shortest path, which is usually closest to the root.
            sorted_paths = sorted(paths, key=lambda p: len(str(p)))
        else:
            sorted_paths = paths

        # Keep the first file and delete the rest.
        to_keep.append(sorted_paths[0])
        to_delete.extend(sorted_paths[1:])

    return to_keep, to_delete


def format_size(size_bytes: int) -> str:
    """Format a file size."""
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
    """Delete files."""
    total = len(files)
    deleted = 0
    failed = 0
    total_size = sum(f.stat().st_size for f in files if f.exists())

    if dry_run:
        if show_progress:
            print(f'\n[DRY RUN] The following {total} files would be deleted ({format_size(total_size)} total):')
            for f in files:
                size = format_size(f.stat().st_size) if f.exists() else '0 B'
                print(f'  - {f} ({size})')
        return {'deleted': 0, 'failed': 0, 'total': total, 'size_freed': 0}

    if show_progress:
        print(f'\nDeleting {total} files...')

    processed = 0
    for f in files:
        try:
            if f.exists():
                f.unlink()
                deleted += 1
        except Exception as e:
            failed += 1
            if show_progress:
                print(f"\nWarning: Failed to delete {f}: {e}", file=sys.stderr)

        processed += 1
        if show_progress:
            _print_progress(processed, total, prefix='Deleting ')

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
    Run duplicate detection and cleanup.
    """
    # 1. Find duplicates.
    print(f"Scanning directory: {media_root}")
    print(f"File type: {file_type}  |  Hash algorithm: {algorithm}  |  Keep strategy: {keep_strategy}")

    duplicates = find_duplicates(media_root, file_type, algorithm, show_progress=True)

    if not duplicates:
        print("\n✓ No duplicate files found")
        return {'duplicates': 0, 'deleted': 0}

    # 2. Summarize the results.
    total_duplicates = sum(len(paths) - 1 for paths in duplicates.values())
    total_groups = len(duplicates)
    print(f"\nFound {total_groups} duplicate groups with {total_duplicates} extra copies")

    # 3. Select files for deletion.
    to_keep, to_delete = select_files_to_keep(duplicates, keep_strategy)

    # 4. Show details.
    print("\nDuplicate file details:")
    for file_hash, paths in list(duplicates.items())[:5]:  # Show the first five groups.
        print(f"\n  Hash: {file_hash[:16]}... ({len(paths)} files)")
        for p in paths:
            status = "✓ Keep" if p in to_keep else "✗ Delete"
            size = format_size(p.stat().st_size) if p.exists() else '0 B'
            print(f"    [{status}] {p} ({size})")

    if len(duplicates) > 5:
        print(f"\n  ... {len(duplicates) - 5} more groups not shown")

    # 5. Delete files.
    if dry_run:
        stats = delete_files(to_delete, dry_run=True, show_progress=True)
        print("\nTip: Use --execute to delete these files")
    else:
        if not auto_confirm:
            print(f"\nWarning: {len(to_delete)} files are about to be deleted!")
            confirm = input("Continue? (yes/no): ").strip().lower()
            if confirm not in ('yes', 'y'):
                print("Operation canceled")
                return {'duplicates': total_duplicates, 'deleted': 0}

        stats = delete_files(to_delete, dry_run=False, show_progress=True)
        print(f"\n✓ Deleted {stats['deleted']} files and freed {format_size(stats['size_freed'])}")
        if stats['failed'] > 0:
            print(f"  Failed: {stats['failed']} files", file=sys.stderr)

    return {
        'duplicates': total_duplicates,
        'deleted': stats.get('deleted', 0),
        'failed': stats.get('failed', 0)
    }
