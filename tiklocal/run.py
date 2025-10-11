import os
import sys
import argparse
from pathlib import Path
from waitress import serve
from tiklocal.app import create_app

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

    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description='TikLocal - 本地媒体服务器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  tiklocal                           # 使用配置文件或环境变量
  tiklocal /path/to/media            # 指定媒体目录
  tiklocal --port 9000               # 使用指定端口
  tiklocal /path/to/media --port 9000
        '''
    )

    parser.add_argument(
        'media_root',
        nargs='?',
        help='媒体文件根目录路径'
    )
    parser.add_argument(
        '--host',
        default=None,
        help='服务器监听地址 (默认: 0.0.0.0)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=None,
        help='服务器端口 (默认: 8000)'
    )

    args = parser.parse_args()

    # 配置优先级: 命令行参数 > 环境变量 > 配置文件 > 默认值
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
    print(f"访问地址: http://{host}:{port}")

    serve(create_app(), host=host, port=port)


if __name__ == '__main__':
    main()
