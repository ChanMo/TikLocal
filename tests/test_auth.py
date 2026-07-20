import json
import re
import stat

import pytest

from tiklocal.app import create_app
from tiklocal.services.auth import AuthStore


PASSWORD = 'private-screening-room'


@pytest.fixture
def authenticated_app(tmp_path, monkeypatch):
    media_root = tmp_path / 'media'
    media_root.mkdir()
    (media_root / 'clip.mp4').write_bytes(b'private-video')
    auth_path = tmp_path / 'auth.json'
    monkeypatch.setenv('TIKLOCAL_INSTANCE', str(tmp_path / 'tiklocal-data'))
    AuthStore(auth_path).ensure(PASSWORD)
    app = create_app({
        'TESTING': True,
        'MEDIA_ROOT': media_root,
        'AUTH_ENABLED': True,
        'AUTH_PATH': auth_path,
    })
    return app, auth_path


def _csrf_from(response) -> str:
    match = re.search(rb'name="_csrf_token" value="([^"]+)"', response.data)
    assert match
    return match.group(1).decode()


def _login(client, password=PASSWORD, next_url='/'):
    login_page = client.get('/login', query_string={'next': next_url})
    csrf_token = _csrf_from(login_page)
    return client.post('/login', data={
        '_csrf_token': csrf_token,
        'password': password,
        'next': next_url,
        'remember': '1',
    })


def test_auth_store_hashes_password_and_increments_revision(tmp_path):
    auth_path = tmp_path / 'auth.json'
    store = AuthStore(auth_path)

    bootstrap = store.ensure(PASSWORD)
    data = json.loads(auth_path.read_text(encoding='utf-8'))

    assert bootstrap.created is True
    assert bootstrap.generated_password is None
    assert PASSWORD not in auth_path.read_text(encoding='utf-8')
    assert data['password_hash'].startswith('scrypt:')
    assert store.verify(PASSWORD)
    assert stat.S_IMODE(auth_path.stat().st_mode) == 0o600

    previous_secret = store.secret_key
    store.set_password('another-private-password')
    assert store.revision == 2
    assert store.secret_key == previous_secret
    assert not store.verify(PASSWORD)
    assert store.verify('another-private-password')


def test_first_start_generates_a_recoverable_password(tmp_path):
    store = AuthStore(tmp_path / 'auth.json')
    bootstrap = store.ensure()

    assert bootstrap.created is True
    assert bootstrap.generated_password
    assert len(bootstrap.generated_password.split('-')) == 4
    assert store.verify(bootstrap.generated_password)


def test_authentication_protects_pages_apis_and_media(authenticated_app):
    app, _ = authenticated_app
    client = app.test_client()

    page = client.get('/')
    api = client.get('/api/library/stats')
    media = client.get('/media/clip.mp4')
    static_asset = client.get('/static/csrf_fetch.js')

    assert page.status_code == 302
    assert page.headers['Location'].endswith('/login?next=/')
    assert api.status_code == 401
    assert api.get_json()['error'] == 'Authentication required'
    assert media.status_code == 401
    assert static_asset.status_code == 200


def test_login_is_polished_safe_and_creates_a_secure_session(authenticated_app):
    app, _ = authenticated_app
    client = app.test_client()

    login_page = client.get('/login', query_string={'next': '/flow'})
    assert login_page.status_code == 200
    assert b'PRIVATE FREQUENCY' in login_page.data
    assert b'no-store' in login_page.headers['Cache-Control'].encode()
    assert login_page.headers['X-Frame-Options'] == 'SAMEORIGIN'

    failed = _login(client, password='incorrect-password')
    assert failed.status_code == 401
    assert '访问密码不正确'.encode() in failed.data

    logged_in = _login(client, next_url='/flow')
    assert logged_in.status_code == 302
    assert logged_in.headers['Location'].endswith('/flow')
    cookie = logged_in.headers['Set-Cookie']
    assert 'HttpOnly' in cookie
    assert 'SameSite=Lax' in cookie
    assert 'Expires=' in cookie
    assert client.get('/').status_code == 200
    assert client.get('/media/clip.mp4').data == b'private-video'


def test_login_rejects_external_redirects(authenticated_app):
    app, _ = authenticated_app
    client = app.test_client()

    response = _login(client, next_url='https://example.com/steal-session')

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/')


def test_csrf_and_logout_are_enforced(authenticated_app):
    app, _ = authenticated_app
    client = app.test_client()
    _login(client)

    rejected = client.post('/api/activity', json={'events': []})
    with client.session_transaction() as auth_session:
        csrf_token = auth_session['_csrf_token']
    accepted = client.post(
        '/api/activity',
        json={'events': [], '_csrf_token': csrf_token},
    )
    rejected_logout = client.post('/logout')
    logged_out = client.post('/logout', data={'_csrf_token': csrf_token})

    assert rejected.status_code == 403
    assert accepted.status_code == 200
    assert rejected_logout.status_code == 403
    assert logged_out.status_code == 302
    assert client.get('/api/library/stats').status_code == 401


def test_cli_password_change_invalidates_running_sessions(authenticated_app):
    app, auth_path = authenticated_app
    client = app.test_client()
    _login(client)
    assert client.get('/').status_code == 200

    AuthStore(auth_path).set_password('replacement-private-password')

    response = client.get('/')
    assert response.status_code == 302
    assert '/login?' in response.headers['Location']
