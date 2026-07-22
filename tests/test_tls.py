import stat
import sys
import threading
import time

import requests
from cheroot.ssl.builtin import BuiltinSSLAdapter
from cheroot.wsgi import Server
from cryptography import x509

from tiklocal.app import create_app
from tiklocal.run import main
from tiklocal.services.tls import ensure_tls_material
from tiklocal.services.tls import local_ca_is_installed


def test_tls_material_is_reused_and_covers_local_addresses(tmp_path):
    tls_dir = tmp_path / 'tls'
    first = ensure_tls_material(
        tls_dir=tls_dir,
        extra_hostnames=['media-box.local'],
        extra_ips=['192.168.50.10'],
    )
    first_cert = x509.load_pem_x509_certificate(first.cert_path.read_bytes())

    second = ensure_tls_material(
        tls_dir=tls_dir,
        extra_hostnames=['media-box.local'],
        extra_ips=['192.168.50.10'],
    )
    second_cert = x509.load_pem_x509_certificate(second.cert_path.read_bytes())
    renewed = ensure_tls_material(
        tls_dir=tls_dir,
        extra_ips=['192.168.50.10'],
        force_renew=True,
    )
    renewed_cert = x509.load_pem_x509_certificate(renewed.cert_path.read_bytes())

    san = first_cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert first.ca_created is True
    assert first.cert_created is True
    assert second.ca_created is False
    assert second.cert_created is False
    assert first_cert.serial_number == second_cert.serial_number
    assert renewed_cert.serial_number != second_cert.serial_number
    assert renewed.ca_fingerprint == first.ca_fingerprint
    renewed_san = renewed_cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert 'media-box.local' in renewed_san.get_values_for_type(x509.DNSName)
    assert 'media-box.local' in san.get_values_for_type(x509.DNSName)
    assert '192.168.50.10' in {str(value) for value in san.get_values_for_type(x509.IPAddress)}
    assert stat.S_IMODE(first.ca_key_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(first.key_path.stat().st_mode) == 0o600


def test_tls_cli_initializes_and_reports_certificate(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('TIKLOCAL_INSTANCE', str(tmp_path / 'data'))
    monkeypatch.setattr(sys, 'argv', ['tiklocal', 'tls', 'init', '--hostname', 'studio.local'])
    main()
    initialized = capsys.readouterr().out

    monkeypatch.setattr(sys, 'argv', ['tiklocal', 'tls', 'status'])
    main()
    status_output = capsys.readouterr().out

    assert 'HTTPS 证书: 已新建' in initialized
    assert 'studio.local' in initialized
    assert 'HTTPS 证书: 有效' in status_output
    assert 'CA SHA-256:' in status_output


def test_tls_trust_adds_ca_to_current_user_keychain(tmp_path, monkeypatch, capsys):
    data_dir = tmp_path / 'data'
    monkeypatch.setenv('TIKLOCAL_INSTANCE', str(data_dir))
    trusted = []

    def fake_trust(path):
        trusted.append(path)
        return tmp_path / 'login.keychain-db'

    monkeypatch.setattr('tiklocal.services.tls.trust_local_ca', fake_trust)
    monkeypatch.setattr(sys, 'argv', ['tiklocal', 'tls', 'trust'])
    main()

    output = capsys.readouterr().out
    assert trusted == [data_dir / 'tls' / 'ca.pem']
    assert '根证书已信任:' in output
    assert '重新打开 Safari 和 Chrome' in output


def test_local_ca_installation_check_matches_exact_fingerprint(tmp_path, monkeypatch):
    material = ensure_tls_material(tls_dir=tmp_path / 'tls')
    fingerprint = material.ca_fingerprint.replace(':', '')

    class Result:
        returncode = 0
        stdout = f'SHA-256 hash: {fingerprint}\n'
        stderr = ''

    monkeypatch.setattr('tiklocal.services.tls.sys.platform', 'darwin')
    monkeypatch.setattr('tiklocal.services.tls.subprocess.run', lambda *args, **kwargs: Result())

    assert local_ca_is_installed(material.ca_cert_path) is True


def test_cheroot_https_preserves_media_range_requests(tmp_path, monkeypatch):
    media_root = tmp_path / 'media'
    media_root.mkdir()
    (media_root / 'clip.mp4').write_bytes(b'0123456789')
    monkeypatch.setenv('TIKLOCAL_INSTANCE', str(tmp_path / 'data'))
    app = create_app({'TESTING': True, 'MEDIA_ROOT': media_root, 'AUTH_ENABLED': False})
    material = ensure_tls_material(tls_dir=tmp_path / 'tls', extra_hostnames=['localhost'])

    server = Server(('127.0.0.1', 0), app, server_name='TikLocal test')
    server.ssl_adapter = BuiltinSSLAdapter(str(material.cert_path), str(material.key_path))
    server.prepare()
    port = server.bind_addr[1]
    thread = threading.Thread(target=server.serve, daemon=True)
    thread.start()
    try:
        response = None
        for _ in range(20):
            try:
                response = requests.get(
                    f'https://127.0.0.1:{port}/media/clip.mp4',
                    headers={'Range': 'bytes=3-6'},
                    verify=str(material.ca_cert_path),
                    timeout=1,
                )
                break
            except requests.ConnectionError:
                time.sleep(0.05)
        assert response is not None
        assert response.status_code == 206
        assert response.content == b'3456'
        assert response.headers['Content-Range'] == 'bytes 3-6/10'
    finally:
        server.stop()
        thread.join(timeout=2)
