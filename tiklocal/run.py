import os
import sys
import argparse
from pathlib import Path
from waitress import serve
from tiklocal.app import create_app
from tiklocal.thumbs import generate_thumbnails
from tiklocal.paths import get_data_dir, get_database_path
from tiklocal.services import LibraryService, build_media_sources, normalize_source_id
from tiklocal.services.embedding import (
    ImageVectorService,
    OpenAICompatibleImageEmbeddingClient,
    SQLiteImageVectorStore,
    get_default_embedding_config,
    merge_embedding_config,
    validate_embedding_config,
)
from tiklocal.services.database import AppDatabase
from tiklocal.services.similarity import (
    DEFAULT_SIMILARITY_MAX_GROUP_SIZE,
    DEFAULT_SIMILARITY_MIN_GROUP_SIZE,
    DEFAULT_SIMILARITY_SCAN_LIMIT,
    DEFAULT_SIMILARITY_THRESHOLD,
    ImageSimilarityService,
    SQLiteSimilarityGroupStore,
)

try:
    import yaml
except ImportError:
    yaml = None


def load_config():
    """从配置文件加载配置"""
    config = {}

    # 尝试读取配置文件
    config_paths = [
        Path.home() / '.config' / 'tiklocal' / 'config.yaml',
        Path.home() / '.tiklocal' / 'config.yaml',
    ]

    for config_path in config_paths:
        if config_path.exists():
            if yaml is None:
                print(f"警告: 找到配置文件 {config_path} 但未安装 PyYAML，跳过配置文件", file=sys.stderr)
                break
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f) or {}
                break
            except Exception as e:
                print(f"警告: 读取配置文件 {config_path} 失败: {e}", file=sys.stderr)

    return config


def normalize_media_sources(config, cli_sources=None, media_root=None):
    raw_sources = cli_sources or config.get('media_sources') or []
    sources = []
    if isinstance(raw_sources, dict):
        raw_sources = [{'id': key, 'path': value, 'name': key} for key, value in raw_sources.items()]
    if isinstance(raw_sources, list):
        for item in raw_sources:
            if not isinstance(item, dict):
                continue
            source_id = normalize_source_id(item.get('id') or item.get('name'))
            path = str(item.get('path') or '').strip()
            if not path:
                continue
            sources.append({
                'id': source_id,
                'name': str(item.get('name') or source_id).strip() or source_id,
                'path': path,
            })
    if media_root and all(item.get('id') != 'default' for item in sources):
        sources.insert(0, {'id': 'default', 'name': 'Default', 'path': str(media_root)})
    return sources


def parse_cli_media_source(value):
    text = str(value or '').strip()
    if '=' not in text:
        raise argparse.ArgumentTypeError('格式必须是 id=/path/to/media')
    source_id, path = text.split('=', 1)
    source_id = normalize_source_id(source_id)
    path = path.strip()
    if not path:
        raise argparse.ArgumentTypeError('媒体目录不能为空')
    return {'id': source_id, 'name': source_id, 'path': path}


def resolve_embedding_config(config, args=None):
    effective = get_default_embedding_config()
    file_config, error = validate_embedding_config(config.get('embedding') or config.get('embedding_config') or {}, partial=True)
    if error:
        file_config = {}
    effective = merge_embedding_config(effective, file_config)

    if args is not None:
        overrides = {}
        if getattr(args, 'max_size', None):
            overrides['image_max_size'] = args.max_size
        if getattr(args, 'quality', None):
            overrides['image_quality'] = args.quality
        if getattr(args, 'dimensions', None):
            overrides['dimensions'] = args.dimensions
        if overrides:
            validated, error = validate_embedding_config(overrides, partial=True)
            if error:
                raise ValueError(error)
            effective = merge_embedding_config(effective, validated)
    return effective


def run_vectorize(config, args, parser):
    media_root = args.media_root or os.environ.get('MEDIA_ROOT') or config.get('media_root')
    media_sources = normalize_media_sources(config, getattr(args, 'media_source', None), media_root=media_root)
    if not media_root and not media_sources:
        parser.error('必须指定媒体目录:\n  - tiklocal vectorize /path/to/media\n  - 或设置 media_root/media_sources')

    media_path = Path(media_root).expanduser() if media_root else Path(media_sources[0]['path']).expanduser()
    for source in media_sources:
        source_path = Path(str(source.get('path') or '')).expanduser()
        if not source_path.exists() or not source_path.is_dir():
            print(f"错误: 媒体源不可用 {source.get('id')}: {source_path}", file=sys.stderr)
            sys.exit(1)

    try:
        embedding_config = resolve_embedding_config(config, args)
    except ValueError as exc:
        parser.error(str(exc))

    if not bool(embedding_config.get('enabled')):
        parser.error('请先在 config.yaml 中设置 embedding.enabled: true')

    library = LibraryService(media_path, media_sources=build_media_sources(media_path, media_sources or None))
    app_database = AppDatabase(get_database_path())
    app_database.migrate()
    vector_index = SQLiteImageVectorStore(app_database)
    vector_service = ImageVectorService(library, vector_index)

    if args.cleanup:
        result = vector_service.cleanup_missing()
        print(f"已清理失效向量: {result['deleted']}")
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
        print("没有需要向量化的图片。")
        return
    if not args.yes:
        answer = input("Proceed? [y/N] ").strip().lower()
        if answer not in {'y', 'yes'}:
            print("已取消。")
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
        parser.error('必须指定媒体目录:\n  - tiklocal analyze-similar /path/to/media\n  - 或设置 media_root/media_sources')

    media_path = Path(media_root).expanduser() if media_root else Path(media_sources[0]['path']).expanduser()
    for source in media_sources:
        source_path = Path(str(source.get('path') or '')).expanduser()
        if not source_path.exists() or not source_path.is_dir():
            print(f"错误: 媒体源不可用 {source.get('id')}: {source_path}", file=sys.stderr)
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
        print(f"已清理相似图片组: {deleted}")
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
        print("没有可保存的相似图片组。")
        return
    if not args.yes:
        answer = input("Save groups to SQLite? [y/N] ").strip().lower()
        if answer not in {'y', 'yes'}:
            print("已取消。")
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


def main():
    # 读取配置文件
    config = load_config()

    # 预处理 argv，支持以下形式：
    # 1) tiklocal                      -> serve
    # 2) tiklocal /path                -> serve /path
    # 3) tiklocal --port 9000          -> serve --port 9000
    # 4) tiklocal thumbs /path         -> thumbs /path
    # 5) tiklocal /path thumbs         -> thumbs /path
    argv = sys.argv[1:]
    if '-h' not in argv and '--help' not in argv:
        if 'thumbs' in argv:
            idx = argv.index('thumbs')
            if idx != 0:
                argv.pop(idx)
                argv.insert(0, 'thumbs')
        elif len(argv) == 0 or argv[0] not in ('serve', 'thumbs', 'dedupe', 'vectorize', 'analyze-similar'):
            # 默认回退 serve（空参数或第一个不是已知子命令）
            argv.insert(0, 'serve')

    # 解析命令行参数（支持子命令）
    parser = argparse.ArgumentParser(
        description='TikLocal - 本地媒体服务器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  tiklocal                                 # 启动服务（默认）
  tiklocal /path/to/media                  # 指定媒体目录
  tiklocal --port 9000                     # 使用指定端口
  tiklocal serve /path --port 9000         # 显式使用 serve 子命令
  tiklocal thumbs /path --overwrite        # 批量生成缩略图
  tiklocal dedupe /path --dry-run          # 查找重复文件（预演）
  tiklocal dedupe /path --execute          # 删除重复，保留最早文件
  tiklocal vectorize /path --limit 200     # 按最新时间向量化前 200 张
  tiklocal analyze-similar /path --yes     # 预生成相似图片组
        '''
    )

    subparsers = parser.add_subparsers(dest='command')

    # serve 子命令
    serve_parser = subparsers.add_parser('serve', help='启动服务器')
    serve_parser.add_argument('media_root', nargs='?', help='媒体文件根目录路径')
    serve_parser.add_argument('--host', default=None, help='服务器监听地址 (默认: 0.0.0.0)')
    serve_parser.add_argument('--port', type=int, default=None, help='服务器端口 (默认: 8000)')
    serve_parser.add_argument('--dev', action='store_true', help='开发模式（启用热重载和调试）')
    serve_parser.add_argument('--media-source', action='append', type=parse_cli_media_source,
                              help='添加媒体源，格式 id=/path/to/media，可重复')
    serve_parser.add_argument('--download-source', default=None, help='下载保存到的媒体源 id')

    # thumbs 子命令
    thumbs_parser = subparsers.add_parser('thumbs', help='批量生成视频缩略图')
    thumbs_parser.add_argument('media_root', nargs='?', help='媒体文件根目录路径（可省略以使用环境变量/配置文件）')
    thumbs_parser.add_argument('--overwrite', action='store_true', help='存在时覆盖重建')
    thumbs_parser.add_argument('--limit', type=int, default=0, help='最多处理多少个（0 表示全部）')

    # dedupe 子命令
    dedupe_parser = subparsers.add_parser('dedupe', help='检测并清理重复文件')
    dedupe_parser.add_argument('media_root', nargs='?', help='媒体文件根目录路径')
    dedupe_parser.add_argument('--type', choices=['video', 'image', 'all'], default='all',
                              help='文件类型（默认：all）')
    dedupe_parser.add_argument('--algorithm', choices=['md5', 'sha256'], default='sha256',
                              help='哈希算法（默认：sha256，更安全）')
    dedupe_parser.add_argument('--keep', choices=['oldest', 'newest', 'shortest_path'], default='oldest',
                              help='保留策略：oldest=最早文件，newest=最新文件，shortest_path=路径最短（默认：oldest）')
    dedupe_parser.add_argument('--dry-run', action='store_true', default=True,
                              help='预演模式，仅显示将删除的文件（默认开启）')
    dedupe_parser.add_argument('--execute', action='store_true',
                              help='执行实际删除（关闭 dry-run）')
    dedupe_parser.add_argument('--auto-confirm', action='store_true',
                              help='自动确认删除，跳过确认提示（危险）')

    # vectorize 子命令
    vectorize_parser = subparsers.add_parser('vectorize', help='批量生成图片向量索引')
    vectorize_parser.add_argument('media_root', nargs='?', help='媒体文件根目录路径（可省略以使用环境变量/配置文件）')
    vectorize_parser.add_argument('--media-source', action='append', type=parse_cli_media_source,
                                  help='添加媒体源，格式 id=/path/to/media，可重复')
    vectorize_parser.add_argument('--source', default=None, help='只处理指定媒体源 id')
    vectorize_parser.add_argument('--limit', type=int, default=0, help='最多处理多少张（0 表示全部）')
    vectorize_parser.add_argument('--order', choices=['latest', 'oldest', 'path'], default='latest',
                                  help='处理顺序（默认：latest）')
    vectorize_parser.add_argument('--dry-run', action='store_true', help='只显示计划，不调用模型')
    vectorize_parser.add_argument('--force', action='store_true', help='忽略已有向量，强制重建')
    vectorize_parser.add_argument('--cleanup', action='store_true', help='清理本地不存在文件对应的向量')
    vectorize_parser.add_argument('--continue-after-cleanup', action='store_true', help='清理后继续执行向量化')
    vectorize_parser.add_argument('--max-size', type=int, default=None, help='覆盖 embedding.image_max_size')
    vectorize_parser.add_argument('--quality', type=int, default=None, help='覆盖 embedding.image_quality')
    vectorize_parser.add_argument('--dimensions', type=int, default=None, help='覆盖 embedding.dimensions')
    vectorize_parser.add_argument('--yes', action='store_true', help='跳过确认提示')

    # analyze-similar 子命令
    analyze_parser = subparsers.add_parser('analyze-similar', help='基于已有图片向量预生成相似图片组')
    analyze_parser.add_argument('media_root', nargs='?', help='媒体文件根目录路径（可省略以使用环境变量/配置文件）')
    analyze_parser.add_argument('--media-source', action='append', type=parse_cli_media_source,
                                help='添加媒体源，格式 id=/path/to/media，可重复')
    analyze_parser.add_argument('--limit', type=int, default=DEFAULT_SIMILARITY_SCAN_LIMIT,
                                help=f'分析最近多少张已有向量的图片（默认：{DEFAULT_SIMILARITY_SCAN_LIMIT}）')
    analyze_parser.add_argument('--threshold', type=float, default=DEFAULT_SIMILARITY_THRESHOLD,
                                help=f'相似度阈值（默认：{DEFAULT_SIMILARITY_THRESHOLD}）')
    analyze_parser.add_argument('--min-group-size', type=int, default=DEFAULT_SIMILARITY_MIN_GROUP_SIZE,
                                help=f'最小成组图片数（默认：{DEFAULT_SIMILARITY_MIN_GROUP_SIZE}）')
    analyze_parser.add_argument('--max-group-size', type=int, default=DEFAULT_SIMILARITY_MAX_GROUP_SIZE,
                                help=f'每组最多保存图片数（默认：{DEFAULT_SIMILARITY_MAX_GROUP_SIZE}）')
    analyze_parser.add_argument('--profile', action='store_true', help='同时输出多个阈值下的分组概况')
    analyze_parser.add_argument('--dry-run', action='store_true', help='只显示分析结果，不写入数据库')
    analyze_parser.add_argument('--clear', action='store_true', help='清理已有相似图片组')
    analyze_parser.add_argument('--continue-after-clear', action='store_true', help='清理后继续重新分析')
    analyze_parser.add_argument('--yes', action='store_true', help='跳过确认提示')

    args = parser.parse_args(argv)

    # 判断命令类型（无子命令时视为 serve）
    cmd = args.command or 'serve'

    if cmd == 'thumbs':
        media_root = args.media_root or os.environ.get('MEDIA_ROOT') or config.get('media_root')
        if not media_root:
            parser.error('必须指定媒体目录:\n  - tiklocal thumbs /path/to/media\n  - 或设置环境变量: MEDIA_ROOT=/path/to/media')
        media_path = Path(media_root)
        if not media_path.exists() or not media_path.is_dir():
            print(f"错误: 媒体目录不可用: {media_root}", file=sys.stderr)
            sys.exit(1)
        print(f"数据目录: {get_data_dir()}")
        stats = generate_thumbnails(media_path, overwrite=getattr(args, 'overwrite', False), limit=getattr(args, 'limit', 0), show_progress=True)
        # 完成后退出
        return

    if cmd == 'dedupe':
        from tiklocal.dedupe import run_dedupe

        media_root = args.media_root or os.environ.get('MEDIA_ROOT') or config.get('media_root')
        if not media_root:
            parser.error('必须指定媒体目录:\n  - tiklocal dedupe /path/to/media\n  - 或设置环境变量: MEDIA_ROOT=/path/to/media')

        media_path = Path(media_root)
        if not media_path.exists() or not media_path.is_dir():
            print(f"错误: 媒体目录不可用: {media_root}", file=sys.stderr)
            sys.exit(1)

        # --execute 标志会关闭 dry-run
        dry_run = not getattr(args, 'execute', False)

        stats = run_dedupe(
            media_root=media_path,
            file_type=getattr(args, 'type', 'all'),
            algorithm=getattr(args, 'algorithm', 'sha256'),
            keep_strategy=getattr(args, 'keep', 'oldest'),
            dry_run=dry_run,
            auto_confirm=getattr(args, 'auto_confirm', False)
        )
        return

    if cmd == 'vectorize':
        run_vectorize(config, args, parser)
        return

    if cmd == 'analyze-similar':
        run_analyze_similar(config, args, parser)
        return

    # serve 路径
    media_root = args.media_root or os.environ.get('MEDIA_ROOT') or config.get('media_root')
    host = args.host or os.environ.get('TIKLOCAL_HOST') or config.get('host', '0.0.0.0')
    port = args.port or int(os.environ.get('TIKLOCAL_PORT', 0)) or config.get('port', 8000)
    media_sources = normalize_media_sources(config, getattr(args, 'media_source', None), media_root=media_root)
    download_source = args.download_source or config.get('download_source') or 'default'
    vision_config = config.get('vision') or config.get('vision_config') or None
    embedding_config = config.get('embedding') or config.get('embedding_config') or None

    # 验证媒体目录
    if not media_root and not media_sources:
        parser.error('必须指定媒体目录:\n  - 通过命令行参数: tiklocal /path/to/media\n  - 通过环境变量: MEDIA_ROOT=/path/to/media\n  - 通过配置文件: ~/.config/tiklocal/config.yaml')

    if media_root:
        media_path = Path(media_root).expanduser()
        if not media_path.exists():
            print(f"错误: 媒体目录不存在: {media_root}", file=sys.stderr)
            sys.exit(1)

        if not media_path.is_dir():
            print(f"错误: 路径不是目录: {media_root}", file=sys.stderr)
            sys.exit(1)
    else:
        media_path = Path(media_sources[0]['path'])

    unavailable_sources = []
    for source in media_sources:
        source_path = Path(str(source.get('path') or '')).expanduser()
        if not source_path.exists() or not source_path.is_dir():
            unavailable_sources.append((source.get('id'), source_path))

    if media_sources and len(unavailable_sources) == len(media_sources):
        print("错误: 所有媒体源均不可用", file=sys.stderr)
        for source_id, source_path in unavailable_sources:
            print(f"  @{source_id}: {source_path}", file=sys.stderr)
        sys.exit(1)
    if not media_root and unavailable_sources:
        unavailable_ids = {source_id for source_id, _ in unavailable_sources}
        first_available = next(
            source for source in media_sources if source.get('id') not in unavailable_ids
        )
        media_path = Path(str(first_available['path'])).expanduser()
    for source_id, source_path in unavailable_sources:
        print(f"警告: 媒体源不可用，启动时将保留原索引 @{source_id}: {source_path}", file=sys.stderr)

    # 设置环境变量供 Flask 使用
    os.environ['MEDIA_ROOT'] = str(media_path.absolute())

    # 启动服务器
    print(f"启动 TikLocal 服务器...")
    if media_sources:
        print("媒体源:")
        for source in media_sources:
            marker = " (下载)" if normalize_source_id(download_source) == source.get('id') else ""
            print(f"  @{source.get('id')}: {Path(str(source.get('path'))).expanduser().absolute()}{marker}")
    else:
        print(f"媒体目录: {media_path.absolute()}")
    print(f"数据目录: {get_data_dir()}")
    print(f"访问地址: http://{host}:{port}")

    app = create_app({
        "MEDIA_ROOT": media_path,
        "MEDIA_SOURCES": media_sources or None,
        "DOWNLOAD_SOURCE": normalize_source_id(download_source),
        "VISION_CONFIG": vision_config,
        "EMBEDDING_CONFIG": embedding_config,
    })
    if getattr(args, 'dev', False):
        # 开发模式：使用Flask内置服务器
        print("⚠️  开发模式已启用（不要在生产环境使用）")
        app.run(host=host, port=port, debug=True, use_reloader=True)
    else:
        # 生产模式：使用Waitress
        serve(app, host=host, port=port)


if __name__ == '__main__':
    main()
