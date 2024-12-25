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
from waitress import serve
# from PIL import Image

app = Flask(__name__)
app.secret_key = b'8af3e391e6cbba8c812a6d3942b12f758a3'

parser = argparse.ArgumentParser(
    prog='TikLocal',
    description='像Tiktok和Pinterest一样浏览您的媒体库',
    epilog='Contact: chan.mo@outlook.com'
)

parser.add_argument('media_folder')
parser.add_argument('--port', type=int, default=8000)

args = parser.parse_args()
media_folder = Path(args.media_folder)

if not media_folder.exists() or not media_folder.is_dir():
    sys.exit('Error: The media root does not exist or is not a directory.')


@app.route("/delete2", methods=['POST', 'GET'])
def delete2_view():
    target = media_folder / unquote(request.args.get('uri'))
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
    target = media_folder / unquote(request.args.get('uri'))
    return send_from_directory(target.parent, target.name)


@app.route('/image')
def image_view():
    uri = request.args.get('uri')
    target = media_folder / unquote(uri)
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
    directory = media_folder / subdir
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
    files = get_files(media_folder)
    files = sorted(files, key=lambda row:row.stat().st_ctime, reverse=True)
    count = len(files)
    page = int(request.args.get('page', 1))
    length = 20
    offset = length * (page - 1)
    res = files[offset:offset + length]
    # res = []
    # for f in files[offset:offset + length]:
    #     f = Path(f)
    #     if not f.exists():
    #         continue
    #     try:
    #         stdout = sp.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'json', str(f)], check=True, capture_output=True)
    #         stdout = json.loads(stdout.stdout.decode('utf8'))
    #         width = stdout['streams'][0]['width']
    #         height = stdout['streams'][0]['height']
    #         res.append({
    #             'file': f,
    #             'width': width,
    #             'height': height,
    #             'horizontal': width > height
    #         })
    #     except Exception as e:
    #         print(e)

    return render_template(
        'browse.html',
        page = page,
        count = count,
        length = length,
        files = res,
        menu = 'browse',
        has_previous = page > 1,
        has_next = len(files[offset+length:])>1,
        theme = session.get('theme', 'light')
    )


@app.route('/')
def tiktok():
    res = os.scandir(media_folder)
    #res = sorted(files, key=lambda row:row.stat().st_mtime, reverse=True)
    #res = random.shuffle(files)
    files = []
    count = 0
    for file in res:
        if not os.path.isfile(os.path.join(media_folder, file)):
            continue
        file_extension = os.path.splitext(file)[-1]
        mime_type = mimetypes.guess_type(file)[0]
        if mime_type and mime_type.startswith('video'):
            files.append(file)

    res = []
    if len(files) > 80:
        newest = files[0:10]
        others = files[11:]
        random.shuffle(others)
        res = newest + others[0:70]
        random.shuffle(res)
    else:
        res = files
        random.shuffle(res)

    return render_template(
        'tiktok.html',
        files=res,
        menu = 'index',
        theme = session.get('theme', 'light')
    )


@app.route('/settings')
def settings_view():
    theme = request.args.get('theme', session.get('theme', 'light'))
    session['theme'] = theme
    return render_template(
        'settings.html',
        menu = 'settings',
        theme = theme,
        videos = len(get_files(media_folder))
    )

@app.route('/detail/<name>')
def detail_view(name):
    #subdir = request.args.get('subdir', '/')
    f = media_folder / name
    files = get_files(media_folder)
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
        os.unlink(media_folder / name)
        return redirect('/browse')

    return render_template(
        'delete_confirm.html',
        file = name,
        theme = session.get('theme', 'light')
    )

@app.route("/media/<name>")
def video_view(name):
    subdir = request.args.get('subdir', '/')
    return send_from_directory(media_folder / subdir, name)

@app.route('/favorite')
def favorite_view():
    db = media_folder / 'favorite.json'
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
    db = media_folder / 'favorite.json'
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


def main():
    serve(app, host='0.0.0.0', port=args.port)

if __name__ == '__main__':
    main()
