import os
import io
import sys
import json
import argparse
import mimetypes
import random
import datetime
import subprocess as sp
from urllib.parse import quote, unquote
from importlib.metadata import version, PackageNotFoundError
import math
import hashlib

from pathlib import Path
from flask import Flask, render_template, send_from_directory, request, session, redirect, send_file
from tiklocal.paths import get_thumbnails_dir, get_thumbs_map_path


try:
    app_version = version("tiklocal")
except PackageNotFoundError:
    app_version = '1.0.0'

FAVORITE_FILENAME = 'favorite.json'
VIDEO_EXTENSIONS = {'.mp4', '.webm', '.mov', '.mkv', '.avi', '.m4v'}


def load_favorites(media_root: Path) -> set[str]:
    """Read favorite entries stored alongside the media library."""
    favorites_path = media_root / FAVORITE_FILENAME
    if not favorites_path.exists():
        return set()

    try:
        with favorites_path.open('r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                return {str(item) for item in data}
    except Exception as exc:
        print(f"读取收藏列表失败: {exc}", file=sys.stderr)
    return set()


def build_weighted_entries(files: list[Path], favorites: set[str], root: Path) -> list[tuple[str, float]]:
    """Assign a weight to each file based on recency and favorite status."""
    now = datetime.datetime.now()
    weighted: list[tuple[str, float]] = []
    for file_path in files:
        if not file_path.exists() or not file_path.is_file():
            continue

        try:
            mtime = file_path.stat().st_mtime
        except (FileNotFoundError, PermissionError):
            continue

        rel_path = str(file_path.relative_to(root))
        favorite_boost = 3.0 if rel_path in favorites else 1.0
        age_days = max((now - datetime.datetime.fromtimestamp(mtime)).total_seconds() / 86400, 0.0)
        time_weight = math.exp(-age_days / 90.0)
        weight = favorite_boost * (0.1 + time_weight)
        weighted.append((rel_path, weight))
    return weighted


def weighted_select(entries: list[tuple[str, float]], limit: int | None = None, rng: random.Random | None = None) -> list[str]:
    """Pick items without replacement using the provided weights."""
    if not entries:
        return []

    rng = rng or random
    pool = entries[:]
    target = len(pool) if limit is None else min(limit, len(pool))
    result: list[str] = []

    while pool and len(result) < target:
        total_weight = sum(weight for _, weight in pool)
        if total_weight <= 0:
            rng.shuffle(pool)
            result.extend([path for path, _ in pool][: target - len(result)])
            break

        pick = rng.random() * total_weight
        cumulative = 0.0
        for index, (path, weight) in enumerate(pool):
            cumulative += weight
            if cumulative >= pick:
                result.append(path)
                pool.pop(index)
                break

    if limit is None and pool:
        rng.shuffle(pool)
        result.extend([path for path, _ in pool])

    return result


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_prefixed_env()
    app.config.from_mapping(
        SECRET_KEY = 'dev',
        MEDIA_ROOT = Path(os.environ['MEDIA_ROOT'])
    )
    app.config.from_pyfile('config.py', silent=True)
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # 缩略图配置（统一使用全局数据目录 ~/.tiklocal 或 TIKLOCAL_INSTANCE）
    THUMB_DIR = get_thumbnails_dir()
    THUMB_MAP = get_thumbs_map_path()

    PLACEHOLDER_PNG = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0cIDAT\x08\x99c\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\x93\x8a\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    def _thumb_key(rel_path: str) -> str:
        return hashlib.sha1(rel_path.encode('utf-8', errors='ignore')).hexdigest() + '.jpg'

    def _thumb_path(rel_path: str) -> Path:
        return THUMB_DIR / _thumb_key(rel_path)

    def _load_thumb_map() -> dict:
        if THUMB_MAP.exists():
            try:
                with THUMB_MAP.open('r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except Exception as exc:
                print(f"读取缩略图映射失败: {exc}", file=sys.stderr)
        return {}

    def _save_thumb_map(data: dict) -> None:
        try:
            with THUMB_MAP.open('w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as exc:
            print(f"保存缩略图映射失败: {exc}", file=sys.stderr)

    def _ffmpeg_capture(input_path: Path, output_path: Path, ts: float | None) -> bool:
        """用 ffmpeg 截帧到 output_path，返回是否成功。"""
        candidates = []
        if ts is not None and ts >= 0:
            candidates = [ts]
        else:
            # 无时长信息时的保守候选
            candidates = [5.0, 1.0, 0.1]

        for t in candidates:
            cmd = [
                'ffmpeg',
                '-y',
                '-ss', str(max(0.0, float(t))),
                '-i', str(input_path),
                '-frames:v', '1',
                '-vf', 'scale=-1:360:force_original_aspect_ratio=decrease',
                '-q:v', '3',
                str(output_path)
            ]
            try:
                proc = sp.run(cmd, stdout=sp.DEVNULL, stderr=sp.DEVNULL, timeout=30)
                if output_path.exists() and output_path.stat().st_size > 0:
                    return True
            except FileNotFoundError:
                # 未安装 ffmpeg
                return False
            except sp.TimeoutExpired:
                continue
            except Exception as exc:
                print(f"ffmpeg 截帧错误: {exc}", file=sys.stderr)
                continue
        return False

    def _is_video(path: Path) -> bool:
        try:
            mime = mimetypes.guess_type(path.name)[0] or ''
        except Exception:
            mime = ''
        if path.suffix.lower() in VIDEO_EXTENSIONS:
            return True
        return mime.startswith('video/')

    @app.route('/thumb')
    def thumb_view():
        """按需返回或生成缩略图，不污染 MEDIA_ROOT。"""
        uri = request.args.get('uri')
        if not uri:
            return send_file(io.BytesIO(PLACEHOLDER_PNG), mimetype='image/png')

        # 解析并校验路径
        try:
            media_root: Path = Path(app.config["MEDIA_ROOT"])
            target = media_root / Path(unquote(uri))
            target = target.resolve()
            # 拒绝越权访问
            if not str(target).startswith(str(media_root.resolve())):
                return send_file(io.BytesIO(PLACEHOLDER_PNG), mimetype='image/png')
        except Exception:
            return send_file(io.BytesIO(PLACEHOLDER_PNG), mimetype='image/png')

        rel_path = str(Path(unquote(uri)))
        thumb_file = _thumb_path(rel_path)

        # 仅为视频生成缩略图
        if not _is_video(target):
            return send_file(io.BytesIO(PLACEHOLDER_PNG), mimetype='image/png')

        if not thumb_file.exists():
            # 生成缩略图（懒生成）
            ok = _ffmpeg_capture(target, thumb_file, None)
            if not ok:
                return send_file(io.BytesIO(PLACEHOLDER_PNG), mimetype='image/png')

        return send_from_directory(THUMB_DIR, thumb_file.name)

    @app.route('/api/thumbnail/<path:name>', methods=['POST'])
    def set_thumbnail(name):
        """将指定时间点设为缩略图。"""
        try:
            media_root: Path = Path(app.config["MEDIA_ROOT"])
            target = (media_root / name).resolve()
            if not target.exists() or not str(target).startswith(str(media_root.resolve())):
                return {'success': False, 'error': '文件不存在或非法路径'}, 400

            payload = request.get_json(silent=True) or {}
            ts = payload.get('time', None)
            try:
                ts_val = None if ts is None else max(0.0, float(ts))
            except (TypeError, ValueError):
                ts_val = None

            rel_path = str(Path(name))
            thumb_file = _thumb_path(rel_path)
            # 重新生成
            ok = _ffmpeg_capture(target, thumb_file, ts_val)
            if not ok:
                return {'success': False, 'error': '缩略图生成失败（可能未安装 ffmpeg）'}, 500

            # 记录映射
            mapping = _load_thumb_map()
            mapping[rel_path] = {
                'ts': ts_val if ts_val is not None else None,
                'updated_at': datetime.datetime.now().isoformat(timespec='seconds')
            }
            _save_thumb_map(mapping)

            return {
                'success': True,
                'url': f"/thumb?uri={quote(rel_path)}&v={int(datetime.datetime.now().timestamp())}"
            }
        except Exception as exc:
            print(f"设置缩略图错误: {exc}", file=sys.stderr)
            return {'success': False, 'error': '内部错误'}, 500

    # 添加自定义过滤器
    @app.template_filter('timestamp_to_date')
    def timestamp_to_date(timestamp):
        """将时间戳转换为可读的日期时间格式"""
        try:
            return datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
        except (ValueError, OSError):
            return '未知时间'

    @app.template_filter('filesizeformat')
    def filesizeformat(num_bytes):
        """将字节数转换为可读的文件大小格式"""
        if num_bytes is None:
            return '0 B'
        
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if num_bytes < 1024.0:
                if unit == 'B':
                    return f"{int(num_bytes)} {unit}"
                return f"{num_bytes:.1f} {unit}"
            num_bytes /= 1024.0
        return f"{num_bytes:.1f} PB"


    @app.route("/delete", methods=['POST', 'GET'])
    def delete_confirm_view():
        target = Path(app.config["MEDIA_ROOT"]) / unquote(request.args.get('uri'))
        if request.method == 'POST':
            target.unlink()
            return redirect('/browse')

        return render_template(
            'delete_confirm.html',
            target = target,
            file = target.name
        )

    @app.route("/media")
    def media_view():
        target = Path(app.config["MEDIA_ROOT"]) / unquote(request.args.get('uri'))
        return send_from_directory(target.parent, target.name)


    @app.route('/image')
    def image_view():
        uri = request.args.get('uri')
        target = Path(app.config["MEDIA_ROOT"]) / unquote(uri)
        return render_template(
            'image_detail.html',
            image = target,
            uri = uri,
            stat = target.stat()
        )


    @app.route('/gallery')
    def gallery():
        subdir = request.args.get('subdir', '')
        directory = Path(app.config["MEDIA_ROOT"]) / subdir
        uri = quote(subdir + '/') if subdir else ''
        media_type = 'image'
        files = os.scandir(directory)
        directories = []
        for row in files:
            if row.is_dir():
                directories.append(row)

        files = os.scandir(directory)
        res = sorted(files, key=lambda row:row.stat().st_mtime, reverse=True)
        #res = [i for i in res if not i.is_dir()]
        files = []
        for file in res:
            if os.path.isfile(os.path.join(directory, file)):
                mime_type = mimetypes.guess_type(file)[0]
                if mime_type and mime_type.startswith(media_type):
                    files.append(file)

        return render_template(
            'gallery.html',
            directories=directories,
            recent=files,
            media_type = media_type,
            subdir = subdir,
            subdirs = subdir.split('/'),
            menu = 'gallery',
            uri = uri
        )


    def get_files(directory, media_type='video'):
        files = []
        for file in os.scandir(directory):
            if file.is_dir():
                files += get_files(file.path)
            elif file.is_file():
                mime_type = mimetypes.guess_type(file.name)[0]
                if mime_type and mime_type.startswith(media_type):
                    files.append(file)
        return files

    @app.route('/browse')
    def browse():
        root = Path(app.config["MEDIA_ROOT"])
        videos = list(root.glob('**/*.mp4')) + list(root.glob('**/*.webm'))

        # 大文件快速筛选：通过 query 参数启用（size=big），默认阈值 50MB，可用 min_mb 调整
        size_mode = request.args.get('size', 'all')
        try:
            min_mb = int(request.args.get('min_mb', 50))
        except ValueError:
            min_mb = 50
        has_min_mb = request.args.get('min_mb') is not None

        if size_mode == 'big':
            threshold = min_mb * 1024 * 1024
            filtered = []
            for v in videos:
                try:
                    if v.stat().st_size >= threshold:
                        filtered.append(v)
                except (FileNotFoundError, PermissionError):
                    continue
            videos = filtered

        videos = sorted(videos, key=lambda row:row.stat().st_ctime, reverse=True)
        count = len(videos)
        page = int(request.args.get('page', 1))
        length = 20
        offset = length * (page - 1)
        #res = videos[offset:offset + length]
        res = []
        for row in videos[offset:offset + length]:
            res.append(row.relative_to(root))

        return render_template(
            'browse.html',
            page = page,
            count = count,
            length = length,
            files = res,
            menu = 'browse',
            size_mode = size_mode,
            min_mb = min_mb,
            has_min_mb = has_min_mb,
            has_previous = page > 1,
            has_next = len(videos[offset+length:])>1
        )


    @app.route('/')
    def tiktok():
        """ Render the Tiktok-like page """
        return render_template(
            'tiktok.html',
            menu = 'index',
        )

    @app.route('/api/videos')
    def api_videos():
        """ API to get random videos """
        root = Path(app.config["MEDIA_ROOT"])
        videos = list(root.glob('**/*.mp4')) + list(root.glob('**/*.webm'))
        favorites = load_favorites(root)
        weighted = build_weighted_entries(videos, favorites, root)
        selected = weighted_select(weighted, limit=20)
        return json.dumps(selected)

    @app.route('/api/random-images')
    def api_random_images():
        """ API to get random images with pagination """
        root = Path(app.config["MEDIA_ROOT"])
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('size', 30))

        # 获取所有图片文件
        images = []
        for ext in ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.webp', '*.bmp']:
            images.extend(root.glob(f'**/{ext}'))
            images.extend(root.glob(f'**/{ext.upper()}'))

        seed = request.args.get('seed')
        if seed is None:
            seed = str(random.randint(1, 999999))

        favorites = load_favorites(root)
        weighted = build_weighted_entries(images, favorites, root)
        rng = random.Random(seed)
        ordered = weighted_select(weighted, limit=len(weighted), rng=rng)

        # 分页
        total = len(ordered)
        start = (page - 1) * page_size
        end = start + page_size
        page_images = ordered[start:end]

        res = page_images

        return {
            'images': res,
            'page': page,
            'total': total,
            'has_more': end < total,
            'seed': seed
        }


    @app.route('/settings/')
    def settings_view():
        return render_template(
            'settings.html',
            menu = 'settings',
            version=app_version,
            videos = len(get_files(Path(app.config["MEDIA_ROOT"])))
        )

    @app.route('/detail/<name>')
    def detail_view(name):
        try:
            f = Path(app.config["MEDIA_ROOT"]) / name
            if not f.exists():
                return "视频文件不存在", 404
                
            files = get_files(Path(app.config["MEDIA_ROOT"]))
            files = sorted(files, key=lambda row:row.stat().st_ctime, reverse=True)
            files = [i.name for i in files]
            
            if name not in files:
                return "视频不在列表中", 404
                
            index = files.index(name)
            previous_item = files[index-1] if index > 0 else None
            next_item = files[index+1] if index < len(files) - 1 else None
            
            return render_template(
                'detail.html',
                file = name,
                mtime = datetime.datetime.fromtimestamp(os.path.getmtime(f)).strftime('%Y-%m-%d %H:%M'),
                size = os.path.getsize(f),
                previous_item = previous_item,
                next_item = next_item
            )
        except Exception as e:
            # 记录错误并返回友好的错误页面
            print(f"视频详情页错误: {e}")
            return f"加载视频详情时出错: {str(e)}", 500

    @app.route("/delete/<name>", methods=['POST', 'GET'])
    def delete_view(name):
        if request.method == 'POST':
            try:
                file_path = Path(app.config["MEDIA_ROOT"]) / name
                if file_path.exists():
                    os.unlink(file_path)
                # 清理缩略图及映射
                try:
                    rel_path = str(Path(name))
                    thumb_file = _thumb_path(rel_path)
                    if thumb_file.exists():
                        thumb_file.unlink(missing_ok=True)
                    mapping = _load_thumb_map()
                    if rel_path in mapping:
                        mapping.pop(rel_path, None)
                        _save_thumb_map(mapping)
                except Exception as _:
                    pass
                return redirect('/browse')
            except Exception as e:
                print(f"删除文件错误: {e}")
                return f"删除文件时出错: {str(e)}", 500

        return render_template(
            'delete_confirm.html',
            file = name
        )


    @app.route("/media")
    def media_detail_view():
        uri = request.args.get('uri')
        if not uri:
            return "缺少文件参数", 400
        try:
            uri_path = Path(uri)
            target = Path(app.config["MEDIA_ROOT"]) / uri_path
            if not target.exists():
                return "文件不存在", 404
            return send_from_directory(target.parent, target.name)
        except Exception as e:
            print(f"媒体文件访问错误: {e}")
            return f"访问文件时出错: {str(e)}", 500

    @app.route("/media/<name>")
    def video_view(name):
        try:
            # 直接在MEDIA_ROOT根目录查找文件
            target = Path(app.config["MEDIA_ROOT"]) / name
            if not target.exists():
                return f"视频文件不存在: {name}", 404
            return send_from_directory(app.config["MEDIA_ROOT"], name)
        except Exception as e:
            print(f"视频文件访问错误: {e}")
            return f"访问视频文件时出错: {str(e)}", 500

    @app.route('/favorite')
    def favorite_view():
        db = Path(app.config["MEDIA_ROOT"]) / FAVORITE_FILENAME
        text = []
        if db.exists():
            with db.open() as f:
                text = json.loads(f.read())

        return render_template(
            'favorite.html',
            files = text
        )


    @app.route('/api/favorite/<name>', methods=['GET', 'POST'])
    def favorite_api(name):
        try:
            db = Path(app.config["MEDIA_ROOT"]) / FAVORITE_FILENAME
            text = []
            if db.exists():
                with db.open() as f:
                    text = json.loads(f.read())
            
            if request.method == 'GET':
                return {'favorite': name in text}

            # POST method - toggle favorite
            if name not in text:
                text.append(name)
            else:
                text.remove(name)

            with db.open(mode='w') as f:
                f.write(json.dumps(text))
            return {'success': True, 'favorite': name in text}
        except Exception as e:
            print(f"收藏操作错误: {e}")
            return {'success': False, 'error': str(e)}, 500


    return app
