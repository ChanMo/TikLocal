import os
import sys
import argparse
from pathlib import Path
from waitress import serve
from tiklocal.app import create_app
from tiklocal.thumbs import generate_thumbnails
from tiklocal.paths import get_data_dir

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
        elif len(argv) == 0 or argv[0] not in ('serve', 'thumbs', 'dedupe'):
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
        '''
    )

    subparsers = parser.add_subparsers(dest='command')

    # serve 子命令
    serve_parser = subparsers.add_parser('serve', help='启动服务器')
    serve_parser.add_argument('media_root', nargs='?', help='媒体文件根目录路径')
    serve_parser.add_argument('--host', default=None, help='服务器监听地址 (默认: 0.0.0.0)')
    serve_parser.add_argument('--port', type=int, default=None, help='服务器端口 (默认: 8000)')
    serve_parser.add_argument('--dev', action='store_true', help='开发模式（启用热重载和调试）')

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

    # serve 路径
    media_root = args.media_root or os.environ.get('MEDIA_ROOT') or config.get('media_root')
    host = args.host or os.environ.get('TIKLOCAL_HOST') or config.get('host', '0.0.0.0')
    port = args.port or int(os.environ.get('TIKLOCAL_PORT', 0)) or config.get('port', 8000)

    # 验证媒体目录
    if not media_root:
        parser.error('必须指定媒体目录:\n  - 通过命令行参数: tiklocal /path/to/media\n  - 通过环境变量: MEDIA_ROOT=/path/to/media\n  - 通过配置文件: ~/.config/tiklocal/config.yaml')

    media_path = Path(media_root)
    if not media_path.exists():
        print(f"错误: 媒体目录不存在: {media_root}", file=sys.stderr)
        sys.exit(1)

    if not media_path.is_dir():
        print(f"错误: 路径不是目录: {media_root}", file=sys.stderr)
        sys.exit(1)

    # 设置环境变量供 Flask 使用
    os.environ['MEDIA_ROOT'] = str(media_path.absolute())

    # 启动服务器
    print(f"启动 TikLocal 服务器...")
    print(f"媒体目录: {media_path.absolute()}")
    print(f"数据目录: {get_data_dir()}")
    print(f"访问地址: http://{host}:{port}")

    app = create_app()
    if getattr(args, 'dev', False):
        # 开发模式：使用Flask内置服务器
        print("⚠️  开发模式已启用（不要在生产环境使用）")
        app.run(host=host, port=port, debug=True, use_reloader=True)
    else:
        # 生产模式：使用Waitress
        serve(app, host=host, port=port)


if __name__ == '__main__':
    main()
