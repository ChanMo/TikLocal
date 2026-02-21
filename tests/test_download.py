import time
from io import BytesIO

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

    data_root = tmp_path / "tiklocal-data"
    monkeypatch.setenv("MEDIA_ROOT", str(media_root))
    monkeypatch.setenv("TIKLOCAL_INSTANCE", str(data_root))
    monkeypatch.setenv("TIKLOCAL_COOKIE_DIR", str(cookie_root))

    def fake_execute_download(self, job_id):  # noqa: ARG001
        return 0, "", "mock-output.mp4"

    monkeypatch.setattr("tiklocal.services.downloader.DownloadManager._execute_download", fake_execute_download)

    app = create_app({"TESTING": True, "MEDIA_ROOT": media_root})
    return app.test_client()


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
    return job


def test_download_config_api(client):
    res = client.get("/api/download/config")
    data = res.get_json()
    assert res.status_code == 200
    assert data["success"] is True
    assert data["data"]["effective"]["max_concurrent"] == 2
    assert data["data"]["effective"]["gallery_archive_enabled"] is True
    assert "gallery_archive_file" in data["data"]["effective"]

    res = client.post(
        "/api/download/config",
        json={
            "enabled": True,
            "default_to_root": True,
            "allow_playlist": False,
            "max_concurrent": 0,
        },
    )
    data = res.get_json()
    assert res.status_code == 200
    assert data["success"] is True
    assert data["data"]["effective"]["max_concurrent"] == 0


def test_download_config_validation(client):
    res = client.post(
        "/api/download/config",
        json={
            "enabled": True,
            "default_to_root": True,
            "allow_playlist": False,
            "max_concurrent": -1,
        },
    )
    data = res.get_json()
    assert res.status_code == 400
    assert data["success"] is False
    assert "max_concurrent" in data["error"]


def test_create_download_job_success(client):
    res = client.post("/api/download/jobs", json={"url": "https://example.com/video"})
    data = res.get_json()
    assert res.status_code == 200
    assert data["success"] is True
    job_id = data["data"]["job"]["id"]

    final_job = _wait_for_job(client, job_id)
    assert final_job["status"] == "success"
    assert final_job["output_path_rel"] == "mock-output.mp4"
    assert final_job["output_files_rel"] == ["mock-output.mp4"]
    assert final_job["file_count"] == 1
    assert final_job["engine"] == "yt-dlp"
    assert final_job["cookie_match_mode"] == "none"


def test_create_download_job_with_gallery_engine(client):
    res = client.post("/api/download/jobs", json={"url": "https://example.com/post", "engine": "gallery-dl"})
    data = res.get_json()
    assert res.status_code == 200
    assert data["success"] is True
    final_job = _wait_for_job(client, data["data"]["job"]["id"])
    assert final_job["status"] == "success"
    assert final_job["engine"] == "gallery-dl"


def test_create_download_job_rejects_invalid_engine(client):
    res = client.post("/api/download/jobs", json={"url": "https://example.com/video", "engine": "wget"})
    data = res.get_json()
    assert res.status_code == 400
    assert data["success"] is False
    assert "engine" in data["error"]


def test_detail_route_redirects_image_to_image_view(client):
    media_root = client.application.config["MEDIA_ROOT"]
    image_file = media_root / "from-download.JPG"
    image_file.write_bytes(b"\x89PNG\r\n")

    res = client.get("/detail/from-download.JPG", follow_redirects=False)
    assert res.status_code in {301, 302, 308}
    location = res.headers.get("Location", "")
    assert location.startswith("/image?uri=")
    assert "from-download.JPG" in location


def test_create_download_job_validation(client):
    res = client.post("/api/download/jobs", json={"url": "file:///tmp/a.mp4"})
    data = res.get_json()
    assert res.status_code == 400
    assert data["success"] is False
    assert "http/https" in data["error"]


def test_cancel_download_job(client, monkeypatch):
    def slow_execute_download(self, job_id):  # noqa: ARG001
        time.sleep(0.25)
        return 0, "", "mock-output.mp4"

    monkeypatch.setattr("tiklocal.services.downloader.DownloadManager._execute_download", slow_execute_download)

    res = client.post("/api/download/jobs", json={"url": "https://example.com/video2"})
    data = res.get_json()
    assert res.status_code == 200
    job_id = data["data"]["job"]["id"]

    cancel_res = client.post(f"/api/download/jobs/{job_id}/cancel")
    cancel_data = cancel_res.get_json()
    assert cancel_res.status_code == 200
    assert cancel_data["success"] is True

    final_job = _wait_for_job(client, job_id)
    assert final_job["status"] in {"canceled", "success"}


def test_download_probe_api(client):
    res = client.post("/api/download/probe")
    data = res.get_json()
    assert res.status_code == 200
    assert data["success"] is True
    assert "yt_dlp_available" in data["data"]
    assert "gallery_dl_available" in data["data"]
    assert "ffmpeg_available" in data["data"]


def test_download_cookie_files_api(client):
    res = client.get("/api/download/cookies")
    data = res.get_json()
    assert res.status_code == 200
    assert data["success"] is True
    assert "x.com.txt" in data["data"]["files"]
    assert "youtube.com.cookies" in data["data"]["files"]


def test_download_job_auto_cookie_match(client):
    res = client.post("/api/download/jobs", json={"url": "https://m.x.com/video/123"})
    data = res.get_json()
    assert res.status_code == 200
    assert data["success"] is True
    job = data["data"]["job"]
    assert job["cookie_match_mode"] == "auto"
    assert job["cookie_file"] == "x.com.txt"


def test_download_job_manual_cookie_file(client):
    res = client.post(
        "/api/download/jobs",
        json={"url": "https://example.com/private", "cookie_mode": "manual", "cookie_file": "youtube.com.cookies"},
    )
    data = res.get_json()
    assert res.status_code == 200
    assert data["success"] is True
    job = data["data"]["job"]
    assert job["cookie_match_mode"] == "manual"
    assert job["cookie_file"] == "youtube.com.cookies"


def test_download_job_rejects_invalid_cookie_file(client):
    res = client.post(
        "/api/download/jobs",
        json={"url": "https://example.com/private", "cookie_mode": "manual", "cookie_file": "../secrets.txt"},
    )
    data = res.get_json()
    assert res.status_code == 400
    assert data["success"] is False
    assert "cookie_file" in data["error"]


def test_upload_cookie_file_and_replace(client):
    res = client.post(
        "/api/download/cookies/upload",
        data={"file": (BytesIO(b"# Netscape HTTP Cookie File\n"), "instagram.com.txt")},
        content_type="multipart/form-data",
    )
    data = res.get_json()
    assert res.status_code == 200
    assert data["success"] is True
    assert data["data"]["filename"] == "instagram.com.txt"

    res = client.post(
        "/api/download/cookies/upload",
        data={"file": (BytesIO(b"# Netscape HTTP Cookie File\n"), "instagram.com.txt")},
        content_type="multipart/form-data",
    )
    data = res.get_json()
    assert res.status_code == 200
    assert data["success"] is True


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
    assert clear_data["data"]["deleted"] >= 0
