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

from pathlib import Path
from flask import Flask, render_template, send_from_directory, request, session, redirect
#from waitress import serve
# from PIL import Image

# parser = argparse.ArgumentParser(
#     prog='TikLocal',
#     description='像Tiktok和Pinterest一样浏览您的媒体库',
#     epilog='Contact: chan.mo@outlook.com'
# )
#
# parser.add_argument('media_folder')
# parser.add_argument('--port', type=int, default=8000)
#
# args = parser.parse_args()
# media_folder = Path(args.media_folder)
#
# if not media_folder.exists() or not media_folder.is_dir():
#     sys.exit('Error: The media root does not exist or is not a directory.')


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_prefixed_env()
    app.config.from_mapping(
        SECRET_KEY = 'dev',
        #MEDIA_ROOT = Path('/home/chen/Videos')
    )
    app.config.from_pyfile('config.py', silent=True)
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass


    @app.route("/delete2", methods=['POST', 'GET'])
    def delete2_view():
        target = Path(app.config["MEDIA_ROOT"]) / unquote(request.args.get('uri'))
        if request.method == 'POST':
            target.unlink()
            return redirect('/browse')

        return render_template(
            'delete_confirm.html',
            theme = session.get('theme', 'light'),
            target = target,
            file = target.name
        )

    @app.route("/media2")
    def media_view():
        target = Path(app.config["MEDIA_ROOT"]) / unquote(request.args.get('uri'))
        return send_from_directory(target.parent, target.name)


    @app.route('/image')
    def image_view():
        uri = request.args.get('uri')
        target = Path(app.config["MEDIA_ROOT"]) / unquote(uri)
        return render_template(
            'image_detail.html',
            theme = session.get('theme', 'light'),
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
            theme = session.get('theme', 'light'),
            uri = uri
        )


    def get_files(directory, media_type='video'):
        files = []
        for file in os.scandir(directory):
            if file.is_dir():
                files += get_files(file)
            if os.path.isfile(os.path.join(directory, file)):
                file_extension = os.path.splitext(file)[-1]
                mime_type = mimetypes.guess_type(file)[0]
                if mime_type and mime_type.startswith(media_type):
                    files.append(file)
        return files

    @app.route('/browse')
    def browse():
        root = Path(app.config["MEDIA_ROOT"])
        videos = root.glob('**/*.mp4')
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
            has_next = len(videos[offset+length:])>1,
            theme = session.get('theme', 'light')
        )


    @app.route('/')
    def tiktok():
        """ Render the Tiktok-like page """
        root = Path(app.config["MEDIA_ROOT"])
        videos = list(root.glob('**/*.mp4'))
        random.shuffle(videos)
        res = []

        for row in videos:
            res.append(row.relative_to(root))

        return render_template(
            'tiktok.html',
            files=res,
            menu = 'index',
        )


    @app.route('/settings')
    def settings_view():
        theme = request.args.get('theme', session.get('theme', 'light'))
        session['theme'] = theme
        return render_template(
            'settings.html',
            menu = 'settings',
            theme = theme,
            videos = len(get_files(Path(app.config["MEDIA_ROOT"])))
        )

    @app.route('/detail/<name>')
    def detail_view(name):
        f = Path(app.config["MEDIA_ROOT"]) / name
        files = get_files(Path(app.config["MEDIA_ROOT"]))
        files = sorted(files, key=lambda row:row.stat().st_ctime, reverse=True)
        files = [i.name for i in files]
        index = files.index(name)
        previous_item = files[index-1] if index > 0 else None
        next_item = files[index+1] if index < len(files) else None
        return render_template(
            'detail.html',
            file = name,
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(f)).strftime('%Y-%m-%d %H:%M'),
            size = os.path.getsize(f),
            theme = session.get('theme', 'light'),
            previous_item = previous_item,
            next_item = next_item
        )

    @app.route("/delete/<name>", methods=['POST', 'GET'])
    def delete_view(name):
        subdir = request.args.get('subdir', '/')
        if request.method == 'POST':
            os.unlink(Path(app.config["MEDIA_ROOT"]) / name)
            return redirect('/browse')

        return render_template(
            'delete_confirm.html',
            file = name,
            theme = session.get('theme', 'light')
        )


    @app.route("/media")
    def media_detail_view():
        uri = Path(request.args.get('uri'))
        return send_from_directory(Path(app.config["MEDIA_ROOT"]) / uri.parent, uri.name)

    @app.route("/media/<name>")
    def video_view(name):
        subdir = request.args.get('subdir', '/')
        return send_from_directory(Path(app.config["MEDIA_ROOT"]) / subdir, name)

    @app.route('/favorite')
    def favorite_view():
        db = Path(app.config["MEDIA_ROOT"]) / 'favorite.json'
        text = []
        if db.exists():
            with db.open() as f:
                text = json.loads(f.read())

        return render_template(
            'favorite.html',
            theme = session.get('theme', 'light'),
            files = text
        )


    @app.route('/api/favorite/<name>', methods=['GET', 'POST'])
    def favorite_api(name):
        #name = request.get_json().get('value')
        db = Path(app.config["MEDIA_ROOT"]) / 'favorite.json'
        text = []
        if db.exists():
            with db.open() as f:
                text = json.loads(f.read())
        if request.method == 'GET':
            return {'favorite': name in text}

        if name not in text:
            text.append(name)
        else:
            text.remove(name)

        with db.open(mode='w') as f:
            f.write(json.dumps(text))
        return {'success':True}


    return app

#def main():
#    serve(app, host='0.0.0.0', port=args.port)
#
#if __name__ == '__main__':
#    main()
