import json
import re
import stat
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlsplit

import pytest

from tiklocal.app import app_version, create_app
from tiklocal.services.auth import AuthStore
from tiklocal.services.device_auth import DeviceAuthStore
from tiklocal.services.pairing_grants import PairingGrantStore


PASSWORD = "private-radio-password"


@pytest.fixture
def radio_client_app(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    media_root.mkdir()
    (media_root / "song-a.mp3").write_bytes(b"a" * 512)
    (media_root / "song-b.m4a").write_bytes(b"b" * 512)
    (media_root / "not-audio.txt").write_text("private", encoding="utf-8")

    data_root = tmp_path / "tiklocal-data"
    auth_path = data_root / "auth.json"
    device_auth_path = data_root / "radio_devices.json"
    monkeypatch.setenv("TIKLOCAL_INSTANCE", str(data_root))
    AuthStore(auth_path).ensure(PASSWORD)

    app = create_app({
        "TESTING": True,
        "MEDIA_ROOT": media_root,
        "AUTH_ENABLED": True,
        "AUTH_PATH": auth_path,
        "DEVICE_AUTH_PATH": device_auth_path,
        "INSTANCE_NAME": "Studio Mac",
    })
    return app, auth_path, device_auth_path


def _pair(client, *, password=PASSWORD, device_name="Chen's iPhone"):
    return client.post("/api/v1/pair", json={
        "password": password,
        "device_name": device_name,
    })


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _login_browser(client):
    page = client.get("/login")
    csrf = re.search(rb'name="_csrf_token" value="([^"]+)"', page.data)
    assert csrf
    return client.post("/login", data={
        "_csrf_token": csrf.group(1).decode(),
        "password": PASSWORD,
    })


def test_device_auth_store_only_persists_token_hash(tmp_path):
    path = tmp_path / "radio_devices.json"
    store = DeviceAuthStore(path)

    credential = store.issue("Bedroom Radio", auth_revision=3)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert credential.token.startswith("tlr_")
    assert credential.token not in path.read_text(encoding="utf-8")
    assert payload["devices"][0]["name"] == "Bedroom Radio"
    assert payload["devices"][0]["auth_revision"] == 3
    assert store.verify(credential.token, auth_revision=3)
    assert not store.verify(credential.token, auth_revision=4)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    assert store.revoke(credential.device_id)
    assert not store.verify(credential.token, auth_revision=3)


def test_pairing_grant_is_hashed_single_use_and_expires():
    now = [1_000.0]
    store = PairingGrantStore(ttl_seconds=30, clock=lambda: now[0])

    grant = store.issue(auth_revision=3)

    assert grant.token.startswith("tlpg_")
    assert grant.token not in repr(store._grants)
    assert grant.expires_in == 30
    assert not store.consume(grant.token + "a", auth_revision=3)
    assert store.consume(grant.token, auth_revision=3)
    assert not store.consume(grant.token, auth_revision=3)

    expired = store.issue(auth_revision=3)
    now[0] += 31
    assert not store.consume(expired.token, auth_revision=3)


def test_pairing_grant_can_only_be_consumed_once_under_concurrency():
    store = PairingGrantStore()
    grant = store.issue(auth_revision=1)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(
            lambda _: store.consume(grant.token, auth_revision=1),
            range(8),
        ))

    assert results.count(True) == 1
    assert results.count(False) == 7


def test_pairing_issues_device_token_and_never_accepts_browser_session(radio_client_app):
    app, _, device_auth_path = radio_client_app
    client = app.test_client()

    unauthorized = client.get("/api/v1/radio/stations")
    assert _login_browser(client).status_code == 302
    browser_session_only = client.get("/api/v1/radio/stations")
    rejected = _pair(client, password="wrong-password")
    paired = _pair(client)
    data = paired.get_json()["data"]
    token = data["device"]["token"]

    assert unauthorized.status_code == 401
    assert unauthorized.get_json()["error"]["code"] == "authentication_required"
    assert browser_session_only.status_code == 401
    assert rejected.status_code == 401
    assert rejected.get_json()["error"]["code"] == "invalid_password"
    assert paired.status_code == 201
    assert data["server"] == {
        "name": "Studio Mac",
        "server_version": app_version,
        "api_version": 1,
        "auth_required": True,
    }
    assert data["device"]["name"] == "Chen's iPhone"
    assert token.startswith("tlr_")
    assert token not in device_auth_path.read_text(encoding="utf-8")

    stations = client.get("/api/v1/radio/stations", headers=_bearer(token))
    assert stations.status_code == 200
    assert [item["id"] for item in stations.get_json()["data"]["stations"]] == [
        "default",
        "recent",
        "favorites",
    ]


def test_pairing_is_rate_limited(radio_client_app):
    app, _, _ = radio_client_app
    client = app.test_client()

    for _ in range(5):
        assert _pair(client, password="wrong-password").status_code == 401

    limited = _pair(client)
    assert limited.status_code == 429
    assert limited.get_json()["error"]["code"] == "too_many_attempts"
    assert int(limited.headers["Retry-After"]) > 0


def test_browser_creates_single_use_pairing_link_and_native_claims_it(
    radio_client_app,
):
    app, _, device_auth_path = radio_client_app
    browser = app.test_client()
    native = app.test_client()

    assert browser.post("/api/radio/pairing-grants", json={
        "server_url": "https://studio.local:8443",
    }).status_code == 401
    assert _login_browser(browser).status_code == 302
    assert browser.post("/api/radio/pairing-grants", json={
        "server_url": "https://studio.local:8443",
    }).status_code == 403
    with browser.session_transaction() as session:
        csrf = session["_csrf_token"]

    created = browser.post(
        "/api/radio/pairing-grants",
        headers={"X-CSRF-Token": csrf},
        json={"server_url": "https://studio.local:8443"},
    )
    data = created.get_json()["data"]
    pairing_uri = urlsplit(data["pairing_uri"])
    query = parse_qs(pairing_uri.query)

    assert created.status_code == 201
    assert created.headers["Cache-Control"] == "private, no-store"
    assert pairing_uri.scheme == "tiklocal-radio"
    assert pairing_uri.netloc == "pair"
    assert query["server"] == ["https://studio.local:8443"]
    assert query["v"] == ["1"]
    assert query["grant"][0].startswith("tlpg_")
    assert data["qr_data_uri"].startswith("data:image/svg+xml")
    assert query["grant"][0] not in data["qr_data_uri"]
    assert data["expires_in"] == 120
    assert query["grant"][0] not in (
        device_auth_path.read_text(encoding="utf-8")
        if device_auth_path.exists()
        else ""
    )

    claimed = native.post("/api/v1/pair/claim", json={
        "grant": query["grant"][0],
        "device_name": "Scanned iPhone",
    })
    credential = claimed.get_json()["data"]["device"]

    assert claimed.status_code == 201
    assert credential["name"] == "Scanned iPhone"
    assert credential["token"].startswith("tlr_")
    assert credential["token"] not in device_auth_path.read_text(encoding="utf-8")
    assert native.get(
        "/api/v1/radio/stations",
        headers=_bearer(credential["token"]),
    ).status_code == 200

    reused = native.post("/api/v1/pair/claim", json={
        "grant": query["grant"][0],
        "device_name": "Second phone",
    })
    assert reused.status_code == 401
    assert reused.get_json()["error"]["code"] == "invalid_pairing_grant"


def test_pairing_link_validates_server_url_and_password_revision(radio_client_app):
    app, auth_path, _ = radio_client_app
    browser = app.test_client()
    native = app.test_client()
    assert _login_browser(browser).status_code == 302
    with browser.session_transaction() as session:
        headers = {"X-CSRF-Token": session["_csrf_token"]}

    invalid = browser.post(
        "/api/radio/pairing-grants",
        headers=headers,
        json={"server_url": "https://user:secret@studio.local/path"},
    )
    assert invalid.status_code == 400
    assert invalid.get_json()["error"]["code"] == "invalid_server_url"

    created = browser.post(
        "/api/radio/pairing-grants",
        headers=headers,
        json={"server_url": "http://studio.local:8443"},
    )
    grant = parse_qs(
        urlsplit(created.get_json()["data"]["pairing_uri"]).query
    )["grant"][0]
    AuthStore(auth_path).set_password("replacement-radio-password")

    expired = native.post("/api/v1/pair/claim", json={
        "grant": grant,
        "device_name": "Late phone",
    })
    assert expired.status_code == 401
    assert expired.get_json()["error"]["code"] == "invalid_pairing_grant"


def test_native_radio_tune_media_range_and_artwork(radio_client_app):
    app, _, _ = radio_client_app
    client = app.test_client()
    token = _pair(client).get_json()["data"]["device"]["token"]
    headers = _bearer(token)

    tuned = client.get(
        "/api/v1/radio/tune?station=default&limit=2&seed=fixed",
        headers=headers,
    )
    assert tuned.status_code == 200
    items = tuned.get_json()["data"]["items"]
    assert len(items) == 2
    assert all(item["uri"].startswith("@default/") for item in items)
    assert all(item["media_path"].startswith("/api/v1/radio/media?uri=") for item in items)

    media = client.get(items[0]["media_path"], headers={
        **headers,
        "Range": "bytes=0-7",
    })
    assert media.status_code == 206
    assert media.headers["Content-Range"].startswith("bytes 0-7/")
    assert media.headers["Accept-Ranges"] == "bytes"
    assert len(media.data) == 8

    artwork = client.get(items[0]["artwork_path"], headers=headers)
    assert artwork.status_code == 200
    assert artwork.mimetype == "image/png"
    assert artwork.data.startswith(b"\x89PNG")

    traversal = client.get(
        "/api/v1/radio/media?uri=../../not-audio.txt",
        headers=headers,
    )
    assert traversal.status_code == 404
    assert traversal.get_json()["error"]["code"] == "audio_not_found"


def test_native_radio_tune_exposes_empty_library_contract(radio_client_app):
    app, _, _ = radio_client_app
    for path in app.config["MEDIA_ROOT"].iterdir():
        if path.suffix.lower() in {".mp3", ".m4a"}:
            path.unlink()

    client = app.test_client()
    token = _pair(client).get_json()["data"]["device"]["token"]
    tuned = client.get(
        "/api/v1/radio/tune?station=default",
        headers=_bearer(token),
    )

    assert tuned.status_code == 200
    data = tuned.get_json()["data"]
    assert data["station"]["id"] == "default"
    assert data["total"] == 0
    assert data["available"] == 0
    assert data["items"] == []


def test_native_favorite_is_idempotent_and_feedback_is_recorded(
    radio_client_app,
    tmp_path,
):
    app, _, _ = radio_client_app
    client = app.test_client()
    token = _pair(client).get_json()["data"]["device"]["token"]
    headers = _bearer(token)
    uri = "@default/song-a.mp3"

    for _ in range(2):
        favorited = client.put(
            "/api/v1/radio/favorite",
            headers=headers,
            json={"uri": uri, "favorite": True},
        )
        assert favorited.status_code == 200
        assert favorited.get_json()["data"]["is_favorite"] is True

    feedback = client.post(
        "/api/v1/radio/feedback",
        headers=headers,
        json={"uri": uri, "event": "complete", "ratio": 0.94},
    )
    assert feedback.status_code == 200
    assert feedback.get_json()["data"]["profile"]["completes"] == 1

    favorites = json.loads(
        (tmp_path / "tiklocal-data" / "favorites.json").read_text(encoding="utf-8")
    )
    assert favorites == [uri]


def test_password_change_invalidates_native_device_token(radio_client_app):
    app, auth_path, _ = radio_client_app
    client = app.test_client()
    token = _pair(client).get_json()["data"]["device"]["token"]

    assert client.get(
        "/api/v1/radio/stations",
        headers=_bearer(token),
    ).status_code == 200

    AuthStore(auth_path).set_password("replacement-radio-password")

    expired = client.get("/api/v1/radio/stations", headers=_bearer(token))
    assert expired.status_code == 401
    assert expired.get_json()["error"]["code"] == "authentication_required"


def test_device_can_revoke_its_own_token(radio_client_app):
    app, _, _ = radio_client_app
    client = app.test_client()
    token = _pair(client).get_json()["data"]["device"]["token"]
    headers = _bearer(token)

    revoked = client.delete("/api/v1/device", headers=headers)

    assert revoked.status_code == 200
    assert revoked.get_json()["data"]["revoked"] is True
    assert client.get("/api/v1/radio/stations", headers=headers).status_code == 401


def test_browser_admin_can_list_and_revoke_devices(radio_client_app):
    app, _, _ = radio_client_app
    native_client = app.test_client()
    first = _pair(native_client, device_name="Kitchen iPad").get_json()["data"]["device"]
    second = _pair(native_client, device_name="Desk Android").get_json()["data"]["device"]

    browser = app.test_client()
    assert _login_browser(browser).status_code == 302
    settings = browser.get("/settings/")
    listed = browser.get("/api/radio/devices")
    devices = listed.get_json()["data"]["devices"]

    assert settings.status_code == 200
    assert b'radio-device-list' in settings.data
    assert b'open-radio-pairing' in settings.data
    assert b'pairing-server-url' in settings.data
    assert b'/api/radio/pairing-grants' in settings.data
    assert b'/api/radio/devices' in settings.data
    assert listed.status_code == 200
    assert [device["name"] for device in devices] == ["Desk Android", "Kitchen iPad"]
    assert all(device["active"] for device in devices)
    assert "token_hash" not in json.dumps(devices)

    rejected = browser.delete(f"/api/radio/devices/{first['id']}")
    assert rejected.status_code == 403

    with browser.session_transaction() as session:
        csrf = session["_csrf_token"]
    removed = browser.delete(
        f"/api/radio/devices/{first['id']}",
        headers={"X-CSRF-Token": csrf},
    )
    assert removed.status_code == 200
    assert native_client.get(
        "/api/v1/radio/stations",
        headers=_bearer(first["token"]),
    ).status_code == 401
    assert native_client.get(
        "/api/v1/radio/stations",
        headers=_bearer(second["token"]),
    ).status_code == 200
