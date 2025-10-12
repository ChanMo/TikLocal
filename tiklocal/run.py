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
        elif len(argv) == 0 or argv[0] not in ('serve', 'thumbs'):
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
        '''
    )

    subparsers = parser.add_subparsers(dest='command')

    # serve 子命令
    serve_parser = subparsers.add_parser('serve', help='启动服务器')
    serve_parser.add_argument('media_root', nargs='?', help='媒体文件根目录路径')
    serve_parser.add_argument('--host', default=None, help='服务器监听地址 (默认: 0.0.0.0)')
    serve_parser.add_argument('--port', type=int, default=None, help='服务器端口 (默认: 8000)')

    # thumbs 子命令
    thumbs_parser = subparsers.add_parser('thumbs', help='批量生成视频缩略图')
    thumbs_parser.add_argument('media_root', nargs='?', help='媒体文件根目录路径（可省略以使用环境变量/配置文件）')
    thumbs_parser.add_argument('--overwrite', action='store_true', help='存在时覆盖重建')
    thumbs_parser.add_argument('--limit', type=int, default=0, help='最多处理多少个（0 表示全部）')

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

    serve(create_app(), host=host, port=port)


if __name__ == '__main__':
    main()
