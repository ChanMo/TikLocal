import sqlite3
import os
import sys
import threading
import time
from io import BytesIO
from threading import Event

import pytest

from tiklocal.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    cookie_root = tmp_path / "cookies"
    cookie_root.mkdir(parents=True, exist_ok=True)
    (cookie_root / "x.com.txt").write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    (cookie_root / "youtube.com.cookies").write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")

    monkeypatch.setenv("MEDIA_ROOT", str(media_root))
    monkeypatch.setenv("TIKLOCAL_COOKIE_DIR", str(cookie_root))

    def fake_execute_download(self, job_id):  # noqa: ARG001
        (self.media_root / "mock-output.mp4").write_bytes(b"video")
        return 0, "", "mock-output.mp4"

    monkeypatch.setattr("tiklocal.services.downloader.DownloadManager._execute_download", fake_execute_download)

    app = create_app({"TESTING": True, "MEDIA_ROOT": media_root})
    manager = app.extensions['download_manager']
    manager.start()
    try:
        yield app.test_client()
    finally:
        manager.close()


def _wait_for_job(client, job_id, timeout=2.0):
    end = time.time() + timeout
    while time.time() < end:
        res = client.get(f"/api/download/jobs/{job_id}")
        assert res.status_code == 200
        data = res.get_json()
        job = data["data"]["job"]
        if job["status"] in {"success", "failed", "canceled"}:
            return job
        time.sleep(0.05)
    pytest.fail(f'任务未在 {timeout} 秒内完成: {job}')


@pytest.mark.parametrize('limit,status', [(0, 200), (-1, 400)])
def test_download_concurrency_config_validation(client, limit, status):
    response = client.post('/api/download/config', json={'max_concurrent': limit})
    assert response.status_code == status
    if status == 200:
        assert client.get('/api/download/config').json['data']['effective']['max_concurrent'] == limit
    else:
        assert 'max_concurrent' in response.json['error']


@pytest.mark.parametrize('engine,limit', [('yt-dlp', 2), ('gallery-dl', 0)])
def test_create_download_job_success(client, engine, limit):
    client.post('/api/download/config', json={'max_concurrent': limit})
    res = client.post("/api/download/jobs", json={"url": "https://example.com/video", "engine": engine})
    data = res.get_json()
    assert res.status_code == 200
    assert data["success"] is True
    job_id = data["data"]["job"]["id"]

    final_job = _wait_for_job(client, job_id)
    assert final_job["status"] == "success"
    assert final_job["output_path_rel"] == "@default/mock-output.mp4"
    assert final_job["output_files_rel"] == ["@default/mock-output.mp4"]
    assert final_job["file_count"] == 1
    assert final_job["engine"] == engine
    assert final_job["cookie_match_mode"] == "none"
    indexed = client.get("/api/library/items?scope=all&q=mock-output&offset=0&limit=20")
    assert [item["name"] for item in indexed.get_json()["data"]["items"]] == [
        "@default/mock-output.mp4"
    ]


def test_detail_route_redirects_image_to_image_view(client):
    media_root = client.application.config["MEDIA_ROOT"]
    image_file = media_root / "from-download.JPG"
    image_file.write_bytes(b"\x89PNG\r\n")

    res = client.get("/detail/from-download.JPG", follow_redirects=False)
    assert res.status_code in {301, 302, 308}
    location = res.headers.get("Location", "")
    assert location.startswith("/image?uri=")
    assert "from-download.JPG" in location


@pytest.mark.parametrize('payload,error', [
    ({'url': 'file:///tmp/a.mp4'}, 'http/https'),
    ({'url': 'https://example.com/video', 'engine': 'wget'}, 'engine'),
    ({'url': 'https://example.com/private', 'cookie_mode': 'manual', 'cookie_file': '../secrets.txt'}, 'cookie_file'),
])
def test_create_download_rejects_invalid_input(client, payload, error):
    response = client.post('/api/download/jobs', json=payload)
    assert response.status_code == 400 and error in response.json['error']
    assert client.get('/api/download/jobs').json['data']['jobs'] == []

def test_cancel_download_job(client, monkeypatch):
    started, release = Event(), Event()

    def slow_execute_download(self, job_id):  # noqa: ARG001
        started.set()
        assert release.wait(5)
        return 0, "", "mock-output.mp4"

    monkeypatch.setattr("tiklocal.services.downloader.DownloadManager._execute_download", slow_execute_download)

    res = client.post("/api/download/jobs", json={"url": "https://example.com/video2"})
    data = res.get_json()
    assert res.status_code == 200
    job_id = data["data"]["job"]["id"]

    try:
        assert started.wait(2)
        cancel_res = client.post(f"/api/download/jobs/{job_id}/cancel")
        assert cancel_res.status_code == 200
        assert cancel_res.get_json()["success"] is True
    finally:
        release.set()

    final_job = _wait_for_job(client, job_id)
    assert final_job["status"] == "canceled"


@pytest.mark.parametrize('remove_output', [False, True])
def test_index_failure_retains_output_and_never_redownloads_on_retry(client, tmp_path, remove_output):
    database_path = tmp_path / 'tiklocal-data' / 'tiklocal.sqlite3'
    with sqlite3.connect(database_path) as db:
        db.execute("CREATE TRIGGER deny_index BEFORE INSERT ON media_items BEGIN SELECT RAISE(ABORT, 'index unavailable'); END")
    job = client.post('/api/download/jobs', json={'url': 'https://example.com/video'}).get_json()['data']['job']
    failed = _wait_for_job(client, job['id'])
    assert failed['status'] == 'failed'
    assert failed['failure_stage'] == 'index'
    assert failed['output_files_rel'] == ['@default/mock-output.mp4']
    output = tmp_path / 'media' / 'mock-output.mp4'
    assert output.read_bytes() == b'video'
    with sqlite3.connect(database_path) as db:
        db.execute('DROP TRIGGER deny_index')
    if remove_output:
        output.unlink()
    else:
        output.write_bytes(b'keep existing output')

    retry = client.post(f"/api/download/jobs/{job['id']}/retry")
    if remove_output:
        assert retry.status_code == 400
        assert not output.exists()
    else:
        assert retry.status_code == 200
        assert retry.get_json()['data']['job']['id'] == job['id']
        assert _wait_for_job(client, job['id'])['status'] == 'success'
        assert output.read_bytes() == b'keep existing output'
        items = client.get('/api/library/items?q=mock-output').get_json()['data']['items']
        assert [item['name'] for item in items] == failed['output_files_rel']


@pytest.mark.parametrize('url,mode,filename', [
    ('https://m.x.com/video/123', 'auto', 'x.com.txt'),
    ('https://example.com/private', 'manual', 'youtube.com.cookies'),
])
def test_download_cookie_selection(client, url, mode, filename):
    response = client.post('/api/download/jobs', json={
        'url': url, 'cookie_mode': mode, 'cookie_file': filename if mode == 'manual' else '',
    })
    assert response.status_code == 200
    job = response.json['data']['job']
    assert job['cookie_match_mode'] == mode and job['cookie_file'] == filename


def test_upload_cookie_file_replaces_content(client):
    for content in (b'first cookie', b'updated cookie'):
        response = client.post('/api/download/cookies/upload', data={
            'file': (BytesIO(content), 'instagram.com.txt'),
        }, content_type='multipart/form-data')
        assert response.status_code == 200
        assert (client.application.config['MEDIA_ROOT'].parent / 'cookies/instagram.com.txt').read_bytes() == content
    assert 'instagram.com.txt' in client.get('/api/download/cookies').json['data']['files']

def test_retry_failed_job(client, monkeypatch):
    def fail_execute(self, job_id):  # noqa: ARG001
        return 1, "network", ""

    monkeypatch.setattr("tiklocal.services.downloader.DownloadManager._execute_download", fail_execute)
    res = client.post("/api/download/jobs", json={"url": "https://example.com/fail", "engine": "gallery-dl"})
    data = res.get_json()
    assert res.status_code == 200
    failed_job = _wait_for_job(client, data["data"]["job"]["id"])
    assert failed_job["status"] == "failed"

    def ok_execute(self, job_id):  # noqa: ARG001
        (self.media_root / "retry-ok.mp4").write_bytes(b"video")
        return 0, "", "retry-ok.mp4"

    monkeypatch.setattr("tiklocal.services.downloader.DownloadManager._execute_download", ok_execute)
    retry_res = client.post(f"/api/download/jobs/{failed_job['id']}/retry")
    retry_data = retry_res.get_json()
    assert retry_res.status_code == 200
    new_job_id = retry_data["data"]["job"]["id"]
    assert new_job_id != failed_job["id"]
    assert retry_data["data"]["job"]["retry_of"] == failed_job["id"]
    assert retry_data["data"]["job"]["engine"] == "gallery-dl"
    final = _wait_for_job(client, new_job_id)
    assert final["status"] == "success"


def test_delete_and_clear_history(client):
    res1 = client.post("/api/download/jobs", json={"url": "https://example.com/a"})
    res2 = client.post("/api/download/jobs", json={"url": "https://example.com/b"})
    j1 = _wait_for_job(client, res1.get_json()["data"]["job"]["id"])
    _wait_for_job(client, res2.get_json()["data"]["job"]["id"])

    del_res = client.delete(f"/api/download/jobs/{j1['id']}")
    del_data = del_res.get_json()
    assert del_res.status_code == 200
    assert del_data["success"] is True

    check_res = client.get(f"/api/download/jobs/{j1['id']}")
    assert check_res.status_code == 404

    clear_res = client.post("/api/download/jobs/clear")
    clear_data = clear_res.get_json()
    assert clear_res.status_code == 200
    assert clear_data["success"] is True
    assert clear_data["data"]["deleted"] == 1
    assert client.get("/api/download/jobs").json["data"]["jobs"] == []
    assert (client.application.config["MEDIA_ROOT"] / "mock-output.mp4").exists()


def test_source_map_survives_history_clear(client):
    url = 'https://x.com/i/web/status/1234567890123456789?utm_source=test'
    job = client.post('/api/download/jobs', json={'url': url}).json['data']['job']
    assert _wait_for_job(client, job['id'])['status'] == 'success'
    before = client.get('/api/source?file=mock-output.mp4').json['data']['source']
    assert before['resolved_by'] == 'map'
    assert before['source_url_display'] == url.split('?')[0]
    assert client.post('/api/download/jobs/clear').status_code == 200
    assert client.get('/api/source?file=mock-output.mp4').json['data']['source'] == before


@pytest.mark.parametrize('name,info,method,url', [
    ('fallback-info.mp4', '{"webpage_url":"https://www.youtube.com/watch?v=abc123&utm_source=mail"}',
     'infojson', 'https://www.youtube.com/watch?v=abc123'),
    ('twitter__alice__189111222333444555__189111222333444555__20260221__01.mp4', None,
     'filename', 'https://x.com/alice/status/189111222333444555'),
])
def test_source_fallback_preserves_clean_url(client, name, info, method, url):
    media = client.application.config['MEDIA_ROOT'] / name
    media.write_bytes(b'00')
    if info:
        media.with_suffix('.info.json').write_text(info)
    response = client.get('/api/source', query_string={'file': name})
    assert response.status_code == 200
    source = response.json['data']['source']
    assert source['resolved_by'] == method and source['source_url_display'] == url


def test_source_batch_api(client):
    media_root = client.application.config["MEDIA_ROOT"]
    media_file = media_root / "batch-fallback.mp4"
    media_file.write_bytes(b"00")
    (media_root / "batch-fallback.info.json").write_text(
        '{"webpage_url":"https://www.tiktok.com/@u/video/12345"}',
        encoding="utf-8",
    )

    res = client.post("/api/source/batch", json={"files": ["batch-fallback.mp4", "missing.mp4"]})
    data = res.get_json()
    assert res.status_code == 200
    assert data["success"] is True
    assert data["data"]["items"]["batch-fallback.mp4"]["source_domain"] == "www.tiktok.com"
    assert data["data"]["items"]["missing.mp4"] is None


def test_delete_file_also_deletes_source_map(client):
    media_root = client.application.config["MEDIA_ROOT"]
    media_file = media_root / "mock-output.mp4"
    media_file.write_bytes(b"00")

    res = client.post("/api/download/jobs", json={"url": "https://example.com/delete-source"})
    job_id = res.get_json()["data"]["job"]["id"]
    _wait_for_job(client, job_id)

    delete_res = client.post("/delete/mock-output.mp4", follow_redirects=False)
    assert delete_res.status_code in {301, 302, 303, 307, 308}

    source_res = client.get("/api/source", query_string={"file": "mock-output.mp4"})
    source_data = source_res.get_json()
    assert source_res.status_code == 200
    assert source_data["success"] is True
    assert source_data["data"]["source"] is None


def test_constructing_and_closing_apps_leaves_no_download_threads(tmp_path):
    before = set(threading.enumerate())
    for _ in range(3):
        app = create_app({'TESTING': True, 'MEDIA_ROOT': tmp_path})
        manager = app.extensions['download_manager']
        manager.update_config({'max_concurrent': 3})
        with pytest.raises(RuntimeError, match='尚未启动'):
            manager.enqueue('https://example.com/video')
        manager.start()
        manager.start()
        manager.close()
        manager.close()
        with pytest.raises(RuntimeError, match='关闭'):
            manager.enqueue('https://example.com/video')
    assert set(threading.enumerate()) == before


def test_reducing_concurrency_waits_for_running_jobs(client, monkeypatch):
    entered = [Event() for _ in range(3)]
    release = [Event() for _ in range(3)]

    def execute(self, job_id):
        index = int(self.get_job(job_id)['url'].rsplit('/', 1)[1])
        entered[index].set()
        assert release[index].wait(5)
        return 0, '', []

    monkeypatch.setattr('tiklocal.services.downloader.DownloadManager._execute_download', execute)
    client.post('/api/download/config', json={'max_concurrent': 2})
    jobs = [client.post('/api/download/jobs', json={'url': f'https://example.com/{i}'}).json['data']['job'] for i in range(3)]
    try:
        assert entered[0].wait(2) and entered[1].wait(2)
        client.post('/api/download/config', json={'max_concurrent': 1})
        release[0].set()
        assert _wait_for_job(client, jobs[0]['id'])['status'] == 'success'
        assert not entered[2].is_set()
        release[1].set()
        assert entered[2].wait(2)
    finally:
        for event in release:
            event.set()


@pytest.mark.skipif(os.name != 'posix', reason='POSIX executable and process-group lifecycle')
@pytest.mark.parametrize('engine,limit', [('yt-dlp', 1), ('gallery-dl', 0)])
def test_close_stops_silent_downloader_and_child_and_persists_cancellation(tmp_path, monkeypatch, engine, limit):
    ready = tmp_path / 'ready'
    tool = tmp_path / engine
    tool.write_text(f'#!{sys.executable}\n' + """
import os, subprocess, sys, time
from pathlib import Path
if '--version' in sys.argv:
    print('test-tool'); sys.exit()
subprocess.Popen([sys.executable, '-c', 'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)'])
Path(os.environ['DOWNLOAD_TEST_READY']).write_text(str(os.getpid()))
time.sleep(60)
""")
    tool.chmod(0o755)
    monkeypatch.setenv('PATH', str(tmp_path) + os.pathsep + os.environ['PATH'])
    monkeypatch.setenv('DOWNLOAD_TEST_READY', str(ready))
    manager = create_app({'TESTING': True, 'MEDIA_ROOT': tmp_path}).extensions['download_manager']
    manager.update_config({'max_concurrent': limit})
    manager.start()
    try:
        job = manager.enqueue('https://example.com/slow', engine=engine)
        deadline = time.monotonic() + 3
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(.02)
        assert ready.exists()
        queued = manager.enqueue('https://example.com/queued', engine=engine) if limit else None
    finally:
        manager.close()
    assert manager.get_job(job['id'])['status'] == 'canceled'
    if queued:
        assert manager.get_job(queued['id'])['status'] == 'canceled'
    assert not any(t.name.startswith('tiklocal-download-') for t in threading.enumerate())
    restored = create_app({'TESTING': True, 'MEDIA_ROOT': tmp_path}).extensions['download_manager']
    assert restored.get_job(job['id'])['status'] == 'canceled'
    restored.close()


@pytest.mark.parametrize('dev,child', [(False, False), (True, False), (True, True)])
def test_cli_owns_download_lifecycle_and_skips_reloader_parent(client, monkeypatch, dev, child):
    from tiklocal.run import main

    managers = []

    def server(app, **kwargs):
        assert app.config['SESSION_COOKIE_SECURE'] is True
        manager = app.extensions['download_manager']
        managers.append(manager)
        if dev and not child:
            with pytest.raises(RuntimeError, match='尚未启动'):
                manager.enqueue('https://example.com/video')
        else:
            manager.enqueue('https://example.com/video')
        raise RuntimeError('test server stopped')

    monkeypatch.setenv('FLASK_AUTH_COOKIE_SECURE', 'true')
    monkeypatch.setattr('tiklocal.run.load_config', lambda: {})
    monkeypatch.setattr('tiklocal.run.serve', server)
    monkeypatch.setattr('flask.Flask.run', server)
    monkeypatch.setenv('WERKZEUG_RUN_MAIN', 'true' if child else 'false')
    monkeypatch.setenv('TIKLOCAL_AUTH_PASSWORD', 'test-only-password')
    monkeypatch.setattr(sys, 'argv', ['tiklocal', str(client.application.config['MEDIA_ROOT']), *(['--dev'] if dev else [])])
    with pytest.raises(RuntimeError, match='test server stopped'):
        main()
    with pytest.raises(RuntimeError, match='关闭'):
        managers[0].enqueue('https://example.com/video')
    assert not any(t.name.startswith('tiklocal-download-') for t in threading.enumerate())
