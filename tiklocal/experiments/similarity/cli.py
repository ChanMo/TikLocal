import os
import sys
from pathlib import Path

from tiklocal.config import normalize_media_sources
from tiklocal.paths import get_database_path
from tiklocal.services.database import AppDatabase
from tiklocal.services.library import LibraryService, build_media_sources, normalize_source_id
from . import DEFAULT_SIMILARITY_SCAN_LIMIT
from .config import resolve_embedding_config
from .embedding import ImageVectorService, OpenAICompatibleImageEmbeddingClient, SQLiteImageVectorStore
from .groups import ImageSimilarityService, SQLiteSimilarityGroupStore


def run_vectorize(config, args, parser):
    media_root = args.media_root or os.environ.get('MEDIA_ROOT') or config.get('media_root')
    media_sources = normalize_media_sources(config, getattr(args, 'media_source', None), media_root=media_root)
    if not media_root and not media_sources:
        parser.error('Specify a media directory:\n  - tiklocal vectorize /path/to/media\n  - or configure media_root/media_sources')

    media_path = Path(media_root).expanduser() if media_root else Path(media_sources[0]['path']).expanduser()
    for source in media_sources:
        source_path = Path(str(source.get('path') or '')).expanduser()
        if not source_path.exists() or not source_path.is_dir():
            print(f"Error: Media source unavailable {source.get('id')}: {source_path}", file=sys.stderr)
            sys.exit(1)

    try:
        embedding_config = resolve_embedding_config(config, args)
    except ValueError as exc:
        parser.error(str(exc))

    if not bool(embedding_config.get('enabled')):
        parser.error('Set embedding.enabled: true in config.yaml first')

    library = LibraryService(media_path, media_sources=build_media_sources(media_path, media_sources or None))
    app_database = AppDatabase(get_database_path())
    app_database.migrate()
    vector_index = SQLiteImageVectorStore(app_database)
    vector_service = ImageVectorService(library, vector_index)

    if args.cleanup:
        result = vector_service.cleanup_missing()
        print(f"Removed stale vectors: {result['deleted']}")
        if not args.continue_after_cleanup:
            return

    source_id = normalize_source_id(args.source) if args.source else None
    plan = vector_service.plan_records(
        config=embedding_config,
        limit=max(int(args.limit or 0), 0),
        order=args.order,
        source_id=source_id,
        force=bool(args.force),
    )

    print("TikLocal image vectorization")
    print("Media sources:")
    for source in library.sources:
        print(f"  @{source.id}: {source.path}")
    print("Config:")
    print(f"  model: {embedding_config.get('model_name')}")
    print(f"  dimensions: {embedding_config.get('dimensions')}")
    print(f"  image_max_size: {embedding_config.get('image_max_size')}")
    print(f"  image_quality: {embedding_config.get('image_quality')}")
    print("Images:")
    print(f"  total: {plan['total_images']}")
    print(f"  indexed current: {plan['indexed_current']}")
    print(f"  missing: {plan['missing']}")
    print(f"  stale: {plan['stale']}")
    print(f"  selected this run: {plan['selected_count']}")
    print(f"  order: {plan['order']}")
    if plan.get('source_id'):
        print(f"  source: @{plan['source_id']}")

    if args.dry_run:
        return
    if plan['selected_count'] == 0:
        print("There are no images to vectorize.")
        return
    if not args.yes:
        answer = input("Proceed? [y/N] ").strip().lower()
        if answer not in {'y', 'yes'}:
            print("Canceled.")
            return

    client = OpenAICompatibleImageEmbeddingClient(
        model=str(embedding_config.get('model_name') or ''),
        base_url=str(embedding_config.get('base_url') or ''),
        dimensions=int(embedding_config.get('dimensions') or 768),
        image_max_size=int(embedding_config.get('image_max_size') or 512),
        image_quality=int(embedding_config.get('image_quality') or 82),
    )

    def report(index, total, record, status, error_text):
        uri = str(record.get('uri') or '')
        if status == 'indexed':
            print(f"[{index}/{total}] {uri} indexed")
        else:
            print(f"[{index}/{total}] {uri} failed: {error_text}", file=sys.stderr)

    result = vector_service.index_missing_or_stale(
        config=embedding_config,
        client=client,
        limit=int(args.limit or 0),
        order=args.order,
        source_id=source_id,
        force=bool(args.force),
        progress_callback=report,
    )
    print("Done:")
    print(f"  indexed: {result['indexed']}")
    print(f"  failed: {result['failed']}")


def run_analyze_similar(config, args, parser):
    media_root = args.media_root or os.environ.get('MEDIA_ROOT') or config.get('media_root')
    media_sources = normalize_media_sources(config, getattr(args, 'media_source', None), media_root=media_root)
    if not media_root and not media_sources:
        parser.error('Specify a media directory:\n  - tiklocal analyze-similar /path/to/media\n  - or configure media_root/media_sources')

    media_path = Path(media_root).expanduser() if media_root else Path(media_sources[0]['path']).expanduser()
    for source in media_sources:
        source_path = Path(str(source.get('path') or '')).expanduser()
        if not source_path.exists() or not source_path.is_dir():
            print(f"Error: Media source unavailable {source.get('id')}: {source_path}", file=sys.stderr)
            sys.exit(1)

    library = LibraryService(media_path, media_sources=build_media_sources(media_path, media_sources or None))
    app_database = AppDatabase(get_database_path())
    app_database.migrate()
    vector_index = SQLiteImageVectorStore(app_database)
    similarity_service = ImageSimilarityService(library, vector_index)
    group_store = SQLiteSimilarityGroupStore(app_database)

    scan_limit = max(50, min(int(args.limit or DEFAULT_SIMILARITY_SCAN_LIMIT), 5000))
    threshold = max(0.5, min(float(args.threshold), 0.99))
    min_group_size = max(2, min(int(args.min_group_size), 12))
    max_group_size = max(2, min(int(args.max_group_size), 16))
    if max_group_size < min_group_size:
        max_group_size = min_group_size

    if args.clear:
        deleted = group_store.clear()
        print(f"Removed similar-image groups: {deleted}")
        if not args.continue_after_clear:
            return

    vectors = similarity_service.load_vectors(scan_limit=scan_limit)
    comparisons = max(0, len(vectors) * (len(vectors) - 1) // 2)
    candidate_pairs = similarity_service.count_candidate_pairs(vectors, threshold=threshold)
    payload = similarity_service.build_groups(
        offset=0,
        limit=5000,
        threshold=threshold,
        min_group_size=min_group_size,
        max_group_size=max_group_size,
        scan_limit=scan_limit,
    )
    groups = payload.get('items') or []
    grouped_images = sum(len(group.get('items') or []) for group in groups)

    print("TikLocal similar image analysis")
    print("Media sources:")
    for source in library.sources:
        print(f"  @{source.id}: {source.path}")
    print("Analysis:")
    print(f"  vectors loaded: {len(vectors)}")
    print(f"  scan limit: {scan_limit}")
    print(f"  threshold: {threshold}")
    print(f"  min group size: {min_group_size}")
    print(f"  max group size: {max_group_size}")
    print(f"  pair comparisons: {comparisons}")
    print(f"  candidate pairs: {candidate_pairs}")
    print(f"  groups found: {len(groups)}")
    print(f"  grouped images: {grouped_images}")
    print(f"  singleton images: {max(0, len(vectors) - grouped_images)}")

    if args.profile:
        print("Threshold profile:")
        for item in similarity_service.profile_thresholds(
            scan_limit=scan_limit,
            min_group_size=min_group_size,
            max_group_size=max_group_size,
        ):
            print(
                f"  {item['threshold']:.2f}: "
                f"groups {item['groups']}, pairs {item['candidate_pairs']}, grouped {item['grouped_images']}"
            )

    if args.dry_run:
        return
    if not groups:
        print("There are no similar-image groups to save.")
        return
    if not args.yes:
        answer = input("Save groups to SQLite? [y/N] ").strip().lower()
        if answer not in {'y', 'yes'}:
            print("Canceled.")
            return

    saved = group_store.save_groups(
        groups,
        threshold=threshold,
        min_group_size=min_group_size,
        max_group_size=max_group_size,
        exclusive=True,
    )
    print("Done:")
    print(f"  saved groups: {saved}")

