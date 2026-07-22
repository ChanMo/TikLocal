import io
import re

from PIL import Image
from cryptography import x509

from tiklocal.app import app_version, create_app
from tiklocal.services.auth import AuthStore
from tiklocal.services.tls import ensure_tls_material


PASSWORD = 'private-screening-room'


def _build_app(tmp_path, monkeypatch, *, auth_enabled=True, extra_config=None):
    media_root = tmp_path / 'media'
    media_root.mkdir()
    (media_root / 'clip.mp4').write_bytes(b'0123456789')
    data_dir = tmp_path / 'data'
    monkeypatch.setenv('TIKLOCAL_INSTANCE', str(data_dir))
    auth_path = data_dir / 'auth.json'
    if auth_enabled:
        AuthStore(auth_path).ensure(PASSWORD)
    config = {
        'TESTING': True,
        'MEDIA_ROOT': media_root,
        'AUTH_ENABLED': auth_enabled,
        'AUTH_PATH': auth_path,
        'INSTANCE_NAME': 'Studio Mac',
    }
    config.update(extra_config or {})
    app = create_app(config)
    return app


def _login(client):
    page = client.get('/login')
    token = re.search(rb'name="_csrf_token" value="([^"]+)"', page.data).group(1).decode()
    return client.post('/login', data={
        '_csrf_token': token,
        'password': PASSWORD,
        'remember': '1',
    })


def test_manifest_and_icons_are_public_and_instance_specific(tmp_path, monkeypatch):
    client = _build_app(tmp_path, monkeypatch).test_client()

    manifest_response = client.get('/app.webmanifest')
    manifest = manifest_response.get_json()

    assert manifest_response.status_code == 200
    assert manifest_response.mimetype == 'application/manifest+json'
    assert manifest_response.headers['Cache-Control'] == 'public, max-age=86400'
    assert manifest['name'] == 'TikLocal · Studio Mac'
    assert manifest['display'] == 'standalone'
    assert manifest['scope'] == '/'
    assert manifest['start_url'] == '/'
    assert {icon['sizes'] for icon in manifest['icons']} == {'192x192', '512x512'}

    icon_response = client.get('/pwa/icon-192.png')
    assert icon_response.status_code == 200
    assert icon_response.mimetype == 'image/png'
    with Image.open(io.BytesIO(icon_response.data)) as icon:
        assert icon.size == (192, 192)


def test_pages_expose_install_metadata_and_versioned_assets(tmp_path, monkeypatch):
    client = _build_app(tmp_path, monkeypatch).test_client()

    login_page = client.get('/login')
    assert b'rel="manifest" href="/app.webmanifest"' in login_page.data
    assert b'/pwa/icon-180.png' in login_page.data
    assert f'/static/pwa_install.js?v={app_version}'.encode() in login_page.data

    _login(client)
    home = client.get('/')
    settings = client.get('/settings/')

    assert f'/static/output.css?v={app_version}'.encode() in home.data
    assert f'/static/pwa_install.js?v={app_version}'.encode() in home.data
    assert b'private, no-cache' in home.headers['Cache-Control'].encode()
    assert '安装 TikLocal · Studio Mac'.encode() in settings.data
    assert b'id="install-app"' in settings.data


def test_cache_policy_keeps_private_data_out_of_public_caches(tmp_path, monkeypatch):
    client = _build_app(tmp_path, monkeypatch, auth_enabled=False).test_client()

    versioned_static = client.get('/static/pwa_install.js', query_string={'v': app_version})
    unversioned_static = client.get('/static/pwa_install.js')
    api = client.get('/api/library/stats')
    media = client.get('/media/clip.mp4', headers={'Range': 'bytes=2-5'})

    assert versioned_static.headers['Cache-Control'] == 'public, max-age=31536000, immutable'
    assert unversioned_static.headers['Cache-Control'] == 'public, max-age=0, must-revalidate'
    assert api.headers['Cache-Control'] == 'private, no-store'
    assert media.status_code == 206
    assert media.data == b'2345'
    assert media.headers['Cache-Control'] == 'private, no-cache'
    assert media.headers['Content-Range'] == 'bytes 2-5/10'


def test_service_worker_is_public_and_only_caches_public_assets(tmp_path, monkeypatch):
    client = _build_app(tmp_path, monkeypatch, auth_enabled=False).test_client()

    worker = client.get('/service-worker.js')
    install_script = client.get('/static/pwa_install.js')

    assert worker.status_code == 200
    assert worker.mimetype == 'application/javascript'
    assert worker.headers['Service-Worker-Allowed'] == '/'
    assert b"url.pathname.startsWith('/static/')" in worker.data
    assert b"url.pathname.startsWith('/pwa/icon-')" in worker.data
    assert b"/media" not in worker.data
    assert b"/thumb" not in worker.data
    assert b"/api/" not in worker.data
    assert b"serviceWorker.register('/service-worker.js?v='" in install_script.data


def test_install_guide_and_ca_download_are_public(tmp_path, monkeypatch):
    ca_path = ensure_tls_material(tls_dir=tmp_path / 'tls').ca_cert_path
    client = _build_app(
        tmp_path,
        monkeypatch,
        extra_config={
            'HTTPS_ENABLED': True,
            'TLS_CA_CERT_PATH': ca_path,
            'TLS_CA_FINGERPRINT': 'AA:BB:CC',
        },
    ).test_client()

    guide = client.get('/install')
    certificate = client.get('/install/ca.pem')
    der_certificate = client.get('/install/ca.cer')

    assert guide.status_code == 200
    assert '文件 → 添加到程序坞'.encode() in guide.data
    assert b'AA:BB:CC' in guide.data
    assert b'href="/install/ca.cer"' in guide.data
    assert certificate.status_code == 200
    assert x509.load_pem_x509_certificate(certificate.data)
    assert 'attachment' in certificate.headers['Content-Disposition']
    assert der_certificate.status_code == 200
    assert der_certificate.mimetype == 'application/pkix-cert'
    assert x509.load_der_x509_certificate(der_certificate.data)


def test_install_script_distinguishes_browser_and_certificate_states(tmp_path, monkeypatch):
    client = _build_app(tmp_path, monkeypatch, auth_enabled=False).test_client()
    script = client.get('/static/pwa_install.js').data

    assert b'untrusted-certificate' in script
    assert b'safari-menu' in script
    assert b'chromium-waiting' in script
    assert b"outcome: 'guide'" in script
