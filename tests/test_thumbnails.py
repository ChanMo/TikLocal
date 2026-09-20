import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from tiklocal.app import create_app
from tiklocal.thumbs import clean_thumbnails, generate_thumbnails, verify_thumbnails


@pytest.mark.parametrize('legacy_cache', [False, True])
def test_cli_cache_is_reused_by_web_and_isolated_between_sources(tmp_path, monkeypatch, legacy_cache):
    main, extra = tmp_path / 'main', tmp_path / 'extra'
    for root in (main, extra):
        root.mkdir()
        (root / 'same # clip.Mp4').write_bytes(b'video')
    captures = []

    def capture(command, **kwargs):
        if command[0] == 'ffmpeg':
            source = Path(command[command.index('-i') + 1])
            captures.append(source)
            Image.new('RGB', (32, 24), 'red' if source.parent == main else 'blue').save(command[-1])
        return subprocess.CompletedProcess(command, 0, stdout='{}' if kwargs.get('text') else b'10')

    monkeypatch.setattr(subprocess, 'run', capture)
    assert generate_thumbnails(main, show_progress=False)['generated'] == 1
    data_dir = tmp_path / 'tiklocal-data'
    cache = next((data_dir / 'thumbnails').glob('*.jpg'))
    expected = cache.read_bytes()
    if legacy_cache:
        legacy = cache.with_name(hashlib.sha1(b'same # clip.Mp4').hexdigest() + '.jpg')
        cache.rename(legacy)
    assert generate_thumbnails(main, show_progress=False)['skipped'] == 1
    assert verify_thumbnails(main)['missing'] == 0
    app = create_app({'TESTING': True, 'MEDIA_ROOT': main, 'MEDIA_SOURCES': [
        {'id': 'extra', 'path': str(extra)},
    ]})
    client = app.test_client()
    primary = client.get('/thumb', query_string={'uri': '@default/same # clip.Mp4'})
    assert primary.status_code == 200
    assert primary.data == expected
    assert len(captures) == 1
    other = client.get('/thumb', query_string={'uri': '@extra/same # clip.Mp4'})
    assert other.mimetype == 'image/jpeg'
    assert other.data != expected
    assert len(captures) == 2
    monkeypatch.setattr(subprocess, 'run', lambda command, **kwargs: subprocess.CompletedProcess(command, 1, stdout=b''))
    assert generate_thumbnails(main, overwrite=True, show_progress=False)['failed'] == 1
    assert client.get('/thumb', query_string={'uri': '@default/same # clip.Mp4'}).data == expected

    mapping_path = data_dir / 'thumbs.json'
    mapping = json.loads(mapping_path.read_text())
    mapping['@extra/same # clip.Mp4'] = {'ts': None}
    mapping_path.write_text(json.dumps(mapping))
    (main / 'same # clip.Mp4').unlink()
    assert clean_thumbnails(main, show_progress=False)['removed'] == 1
    assert client.get('/thumb', query_string={'uri': '@extra/same # clip.Mp4'}).data == other.data
    assert '@extra/same # clip.Mp4' in json.loads(mapping_path.read_text())

    assert client.get('/api/library/stats').get_json()['cache_count'] == 1
    cleared = client.post('/api/cache/clear').get_json()
    assert cleared['success'] and cleared['deleted_count'] == 1
    assert client.get('/api/library/stats').get_json()['cache_count'] == 0
    assert (extra / 'same # clip.Mp4').read_bytes() == b'video'
    assert '@extra/same # clip.Mp4' in json.loads(mapping_path.read_text())
