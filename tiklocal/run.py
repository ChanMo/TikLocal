import os
import sys
import signal
import argparse
import getpass
from pathlib import Path
from waitress import serve
from tiklocal.app import create_app
from tiklocal.thumbs import generate_thumbnails
from tiklocal.paths import get_data_dir
from tiklocal.paths import get_auth_path
from tiklocal.services.auth import AuthStore
from tiklocal.services.library import normalize_source_id
from tiklocal.config import normalize_media_sources, similarity_enabled
from tiklocal.experiments.similarity import (
    DEFAULT_SIMILARITY_MAX_GROUP_SIZE, DEFAULT_SIMILARITY_MIN_GROUP_SIZE,
    DEFAULT_SIMILARITY_SCAN_LIMIT, DEFAULT_SIMILARITY_THRESHOLD,
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
        elif len(argv) == 0 or argv[0] not in ('serve', 'thumbs', 'dedupe', 'vectorize', 'analyze-similar', 'auth'):
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
  tiklocal auth set-password               # 设置新的访问密码
        '''
    )

    subparsers = parser.add_subparsers(dest='command')

    # serve 子命令
    serve_parser = subparsers.add_parser('serve', help='启动服务器')
    serve_parser.add_argument('media_root', nargs='?', help='媒体文件根目录路径')
    serve_parser.add_argument('--host', default=None, help='服务器监听地址 (默认: 0.0.0.0)')
    serve_parser.add_argument('--port', type=int, default=None, help='服务器端口 (默认: 8000)')
    serve_parser.add_argument('--dev', action='store_true', help='开发模式（启用热重载和调试）')
    serve_parser.add_argument('--name', default=None, help='当前实例的显示名称')
    serve_parser.add_argument('--media-source', action='append', type=parse_cli_media_source,
                              help='添加媒体源，格式 id=/path/to/media，可重复')
    serve_parser.add_argument('--download-source', default=None, help='下载保存到的媒体源 id')

    auth_parser = subparsers.add_parser('auth', help='管理访问认证')
    auth_parser.add_argument('action', choices=['set-password', 'status'], help='认证操作')

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

    if cmd in {'vectorize', 'analyze-similar'}:
        try:
            enabled = similarity_enabled(config.get('experiments'), config.get('embedding') or config.get('embedding_config'))
        except ValueError as exc:
            parser.error(str(exc))
        if not enabled:
            parser.error('相似图片实验已关闭；请设置 experiments.similarity.enabled: true')

    if cmd == 'vectorize':
        from tiklocal.experiments.similarity.cli import run_vectorize
        run_vectorize(config, args, parser)
        return

    if cmd == 'analyze-similar':
        from tiklocal.experiments.similarity.cli import run_analyze_similar
        run_analyze_similar(config, args, parser)
        return

    if cmd == 'auth':
        auth_store = AuthStore(get_auth_path())
        if args.action == 'status':
            try:
                bootstrap = auth_store.ensure(os.environ.get('TIKLOCAL_AUTH_PASSWORD'))
            except ValueError as exc:
                parser.error(str(exc))
            print(f"认证状态: 已启用")
            print(f"认证文件: {auth_store.path}")
            if bootstrap.generated_password:
                print(f"首次访问密码: {bootstrap.generated_password}")
            return

        env_password = str(os.environ.get('TIKLOCAL_AUTH_PASSWORD') or '')
        if env_password:
            password = env_password
        else:
            password = getpass.getpass('新的访问密码: ')
            confirmation = getpass.getpass('再次输入密码: ')
            if password != confirmation:
                parser.error('两次输入的密码不一致')
        try:
            auth_store.set_password(password)
        except ValueError as exc:
            parser.error(str(exc))
        print('访问密码已更新，所有已登录设备需要重新登录。')
        return

    # serve 路径
    media_root = args.media_root or os.environ.get('MEDIA_ROOT') or config.get('media_root')
    host = args.host or os.environ.get('TIKLOCAL_HOST') or config.get('host', '0.0.0.0')
    if any(config.get(key) for key in ('https', 'tls_cert', 'tls_key', 'hostnames')):
        parser.error('内置 HTTPS 已移除；请删除旧 TLS 配置，并由外部反向代理提供 HTTPS。')
    configured_port = int(os.environ.get('TIKLOCAL_PORT', 0)) or config.get('port')
    port = args.port or configured_port or 8000
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

    try:
        app = create_app({
            "MEDIA_ROOT": media_path,
            "MEDIA_SOURCES": media_sources or None,
            "DOWNLOAD_SOURCE": normalize_source_id(download_source),
            "VISION_CONFIG": vision_config,
            "EMBEDDING_CONFIG": embedding_config,
            "EXPERIMENTS": config.get('experiments'),
            "INSTANCE_NAME": args.name or config.get('name') or os.environ.get('TIKLOCAL_NAME'),
        })
    except ValueError as exc:
        parser.error(str(exc))
    bootstrap = app.extensions.get('auth_bootstrap')
    print("访问认证: 已启用")
    if bootstrap and bootstrap.generated_password:
        print("┌────────────────────────────────────────────┐")
        print("│ 首次启动访问密码                           │")
        print(f"│ {bootstrap.generated_password:<42} │")
        print("│ 请保存；可用 tiklocal auth set-password 更改 │")
        print("└────────────────────────────────────────────┘")
    download_manager = app.extensions['download_manager']
    previous_sigterm = signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        if not args.dev or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
            download_manager.start()
        if getattr(args, 'dev', False):
            # 开发模式：使用Flask内置服务器
            print("⚠️  开发模式已启用（不要在生产环境使用）")
            app.run(host=host, port=port, debug=True, use_reloader=True)
        else:
            # 生产模式：使用Waitress
            serve(app, host=host, port=port)
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)
        download_manager.close()


if __name__ == '__main__':
    main()
