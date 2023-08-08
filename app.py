import os
import io
import mimetypes
from pathlib import Path
from flask import Flask, render_template, send_from_directory, request
# from PIL import Image

app = Flask(__name__)

media_folder = Path(os.environ.get('FLASK_MEDIA', '.'))

@app.route('/')
def index():
    subdir = request.args.get('subdir', '')
    directory = media_folder / subdir
    print(directory)
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
        directories=directories,
        recent=files,
        media_type = media_type,
        subdir = subdir,
        subdirs = subdir.split('/')
    )


@app.route("/media/<name>")
def video_view(name):
    subdir = request.args.get('subdir', '/')
    return send_from_directory(media_folder / subdir, name)
