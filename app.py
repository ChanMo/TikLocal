import os
import io
import mimetypes
import random
from pathlib import Path
from flask import Flask, render_template, send_from_directory, request, session
# from PIL import Image

app = Flask(__name__)
app.secret_key = b'8af3e391e6cbba8c812a6d3942b12f758a3'

media_folder = Path(os.environ.get('FLASK_MEDIA', '.'))

@app.route('/')
def index():
    theme = request.args.get('theme', session.get('theme', 'light'))
    session['theme'] = theme
    subdir = request.args.get('subdir', '')
    directory = media_folder / subdir
    media_type = request.args.get('media_type', 'image')
    files = os.scandir(directory)
    directories = []
    recent = []
    for row in files:
        if row.is_dir():
            directories.append(row)

    files = os.scandir(directory)
    res = sorted(files, key=lambda row:row.stat().st_mtime, reverse=True)
    #res = [i for i in res if not i.is_dir()]
    files = []
    for file in res:
        if os.path.isfile(os.path.join(directory, file)):
            file_extension = os.path.splitext(file)[-1]
            mime_type = mimetypes.guess_type(file)[0]
            if mime_type and mime_type.startswith(media_type):
                files.append(file)

    return render_template(
        'index.html',
        theme=theme,
        directories=directories,
        recent=files,
        media_type = media_type,
        subdir = subdir,
        subdirs = subdir.split('/')
    )


@app.route('/tiktok')
def tiktok():
    theme = request.args.get('theme', session.get('theme', 'light'))
    session['theme'] = theme
    res = os.scandir(media_folder)
    #res = sorted(files, key=lambda row:row.stat().st_mtime, reverse=True)
    #res = random.shuffle(files)
    files = []
    for file in res:
        if os.path.isfile(os.path.join(media_folder, file)):
            file_extension = os.path.splitext(file)[-1]
            mime_type = mimetypes.guess_type(file)[0]
            if mime_type and mime_type.startswith('video'):
                files.append(file)

    print(files)
    random.shuffle(files)

    return render_template(
        'tiktok.html',
        theme=theme,
        files=files
    )



@app.route("/media/<name>")
def video_view(name):
    subdir = request.args.get('subdir', '/')
    return send_from_directory(media_folder / subdir, name)
