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

from pathlib import Path
from flask import Flask, render_template, send_from_directory, request, session, redirect


try:
    app_version = version("tiklocal")
except PackageNotFoundError:
    app_version = '1.0.0'


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
        random.shuffle(videos)
        res = []

        for row in videos[:20]:
            res.append(str(row.relative_to(root)))

        return json.dumps(res)


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
        db = Path(app.config["MEDIA_ROOT"]) / 'favorite.json'
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
            db = Path(app.config["MEDIA_ROOT"]) / 'favorite.json'
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
