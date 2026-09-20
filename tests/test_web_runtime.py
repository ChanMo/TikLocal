import sys

import pytest

from tiklocal.app import app_version, create_app
from tiklocal.run import main


def test_browser_cache_policy_and_media_range(tmp_path):
    (tmp_path / 'clip.mp4').write_bytes(b'0123456789')
    client = create_app({'TESTING': True, 'MEDIA_ROOT': tmp_path}).test_client()
    versioned = client.get('/static/csrf_fetch.js', query_string={'v': app_version})
    plain = client.get('/static/csrf_fetch.js')
    media = client.get('/media/clip.mp4', headers={'Range': 'bytes=2-5'})
    assert versioned.headers['Cache-Control'] == 'public, max-age=31536000, immutable'
    assert plain.headers['Cache-Control'] == 'public, max-age=0, must-revalidate'
    assert client.get('/api/library/stats').headers['Cache-Control'] == 'private, no-store'
    assert media.status_code == 206 and media.data == b'2345'
    assert media.headers['Cache-Control'] == 'private, no-cache'
    assert media.headers['Content-Range'] == 'bytes 2-5/10'
    assert client.get('/install').status_code == 404
    assert client.get('/app.webmanifest').status_code == 404


def test_retirement_worker_is_available_before_login(tmp_path, monkeypatch):
    monkeypatch.setenv('TIKLOCAL_AUTH_PASSWORD', 'test-only-password')
    client = create_app({'TESTING': True, 'MEDIA_ROOT': tmp_path, 'AUTH_ENABLED': True}).test_client()
    worker = client.get('/service-worker.js?v=old-version')
    assert worker.status_code == 200
    assert worker.mimetype == 'application/javascript'
    assert worker.headers['Service-Worker-Allowed'] == '/'
    assert worker.headers['Cache-Control'] == 'no-cache, no-store, must-revalidate'


@pytest.mark.parametrize('key,value', [
    ('https', True), ('tls_cert', 'cert.pem'), ('tls_key', 'key.pem'), ('hostnames', ['studio.local']),
])
def test_old_tls_config_does_not_silently_start_http(monkeypatch, capsys, key, value):
    monkeypatch.setattr('tiklocal.run.load_config', lambda: {key: value})
    monkeypatch.setattr(sys, 'argv', ['tiklocal'])
    with pytest.raises(SystemExit) as stopped:
        main()
    assert stopped.value.code == 2
    assert '内置 HTTPS 已移除' in capsys.readouterr().err
