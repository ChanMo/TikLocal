from __future__ import annotations

import datetime
import ipaddress
import os
import re
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from tiklocal.paths import get_tls_dir


ROOT_LIFETIME_DAYS = 3650
LEAF_LIFETIME_DAYS = 90
RENEW_BEFORE_DAYS = 30


@dataclass(frozen=True)
class TLSMaterial:
    ca_cert_path: Path
    ca_key_path: Path
    cert_path: Path
    key_path: Path
    hostnames: tuple[str, ...]
    ip_addresses: tuple[str, ...]
    ca_created: bool
    cert_created: bool
    expires_at: datetime.datetime
    ca_fingerprint: str


def discover_local_names(extra_hostnames: Iterable[str] = ()) -> tuple[str, ...]:
    names = {'localhost'}
    candidates = [socket.gethostname(), socket.getfqdn(), *extra_hostnames]
    for candidate in candidates:
        name = _normalize_hostname(candidate)
        if not name:
            continue
        names.add(name)
        if '.' not in name and name != 'localhost':
            names.add(f'{name}.local')
    return tuple(sorted(names))


def discover_local_ips(extra_ips: Iterable[str] = ()) -> tuple[str, ...]:
    addresses = {'127.0.0.1', '::1'}
    candidates = list(extra_ips)
    try:
        candidates.extend(item[4][0] for item in socket.getaddrinfo(socket.gethostname(), None))
    except OSError:
        pass

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(('192.0.2.1', 9))
        candidates.append(probe.getsockname()[0])
    except OSError:
        pass
    finally:
        probe.close()

    for candidate in candidates:
        try:
            addresses.add(str(ipaddress.ip_address(str(candidate).split('%', 1)[0])))
        except ValueError:
            continue
    return tuple(sorted(addresses))


def ensure_tls_material(
    *,
    extra_hostnames: Iterable[str] = (),
    extra_ips: Iterable[str] = (),
    force_renew: bool = False,
    tls_dir: str | Path | None = None,
) -> TLSMaterial:
    directory = Path(tls_dir) if tls_dir is not None else get_tls_dir()
    directory.mkdir(parents=True, exist_ok=True)
    ca_cert_path = directory / 'ca.pem'
    ca_key_path = directory / 'ca-key.pem'
    cert_path = directory / 'server.pem'
    key_path = directory / 'server-key.pem'
    preserved_hostnames = []
    try:
        existing_cert = _load_certificate(cert_path)
        existing_san = existing_cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        preserved_hostnames = existing_san.get_values_for_type(x509.DNSName)
    except (OSError, ValueError, x509.ExtensionNotFound):
        pass
    hostnames = discover_local_names([*extra_hostnames, *preserved_hostnames])
    ip_addresses = discover_local_ips(extra_ips)
    now = datetime.datetime.now(datetime.timezone.utc)

    ca_created = False
    try:
        ca_key = _load_private_key(ca_key_path)
        ca_cert = _load_certificate(ca_cert_path)
        if not _root_is_usable(ca_key, ca_cert, now):
            raise ValueError('local CA needs replacement')
    except (OSError, ValueError, TypeError):
        ca_key, ca_cert = _create_root_ca(now)
        _write_private_key(ca_key_path, ca_key)
        _write_certificate(ca_cert_path, ca_cert)
        ca_created = True

    cert_created = force_renew or ca_created
    if not cert_created:
        try:
            server_key = _load_private_key(key_path)
            server_cert = _load_certificate(cert_path)
            cert_created = not _leaf_is_usable(
                server_key,
                server_cert,
                ca_cert,
                hostnames,
                ip_addresses,
                now,
            )
        except (OSError, ValueError, TypeError):
            cert_created = True

    if cert_created:
        server_key, server_cert = _create_server_certificate(
            ca_key,
            ca_cert,
            hostnames,
            ip_addresses,
            now,
        )
        _write_private_key(key_path, server_key)
        _write_certificate(cert_path, server_cert)
    else:
        server_cert = _load_certificate(cert_path)

    return TLSMaterial(
        ca_cert_path=ca_cert_path,
        ca_key_path=ca_key_path,
        cert_path=cert_path,
        key_path=key_path,
        hostnames=hostnames,
        ip_addresses=ip_addresses,
        ca_created=ca_created,
        cert_created=cert_created,
        expires_at=server_cert.not_valid_after_utc,
        ca_fingerprint=_fingerprint(ca_cert),
    )


def read_tls_material(tls_dir: str | Path | None = None) -> TLSMaterial | None:
    directory = Path(tls_dir) if tls_dir is not None else get_tls_dir()
    ca_cert_path = directory / 'ca.pem'
    ca_key_path = directory / 'ca-key.pem'
    cert_path = directory / 'server.pem'
    key_path = directory / 'server-key.pem'
    try:
        ca_key = _load_private_key(ca_key_path)
        ca_cert = _load_certificate(ca_cert_path)
        server_key = _load_private_key(key_path)
        server_cert = _load_certificate(cert_path)
        if not _public_keys_match(ca_key, ca_cert) or not _public_keys_match(server_key, server_cert):
            return None
        ca_cert.public_key().verify(
            server_cert.signature,
            server_cert.tbs_certificate_bytes,
            padding.PKCS1v15(),
            server_cert.signature_hash_algorithm,
        )
        san = server_cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except (OSError, ValueError, TypeError, InvalidSignature, x509.ExtensionNotFound):
        return None
    return TLSMaterial(
        ca_cert_path=ca_cert_path,
        ca_key_path=ca_key_path,
        cert_path=cert_path,
        key_path=key_path,
        hostnames=tuple(sorted(san.get_values_for_type(x509.DNSName))),
        ip_addresses=tuple(sorted(str(value) for value in san.get_values_for_type(x509.IPAddress))),
        ca_created=False,
        cert_created=False,
        expires_at=server_cert.not_valid_after_utc,
        ca_fingerprint=_fingerprint(ca_cert),
    )


def trust_local_ca(ca_cert_path: str | Path) -> Path:
    """Trust the TikLocal root CA for the current macOS user."""
    if sys.platform != 'darwin':
        raise RuntimeError('自动信任目前只支持 macOS；请在当前设备手动导入 ca.pem。')

    certificate = Path(ca_cert_path).expanduser().resolve()
    if not certificate.is_file():
        raise RuntimeError(f'根证书不存在: {certificate}')

    keychain = Path.home() / 'Library' / 'Keychains' / 'login.keychain-db'
    result = subprocess.run(
        [
            'security',
            'add-trusted-cert',
            '-r',
            'trustRoot',
            '-k',
            str(keychain),
            str(certificate),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or '').strip()
        raise RuntimeError(detail or '无法写入 macOS 登录钥匙串。')
    return keychain


def local_ca_is_installed(ca_cert_path: str | Path) -> bool | None:
    """Return whether the exact CA is present in a standard macOS keychain."""
    if sys.platform != 'darwin':
        return None

    certificate = Path(ca_cert_path).expanduser()
    if not certificate.is_file():
        return False
    expected = _load_certificate(certificate).fingerprint(hashes.SHA256()).hex().upper()
    keychains = [
        Path.home() / 'Library' / 'Keychains' / 'login.keychain-db',
        Path('/Library/Keychains/System.keychain'),
    ]
    for keychain in keychains:
        result = subprocess.run(
            ['security', 'find-certificate', '-a', '-Z', '-c', 'TikLocal Local CA', str(keychain)],
            capture_output=True,
            text=True,
            check=False,
        )
        fingerprints = re.findall(r'SHA-256 hash:\s*([0-9A-F]{64})', result.stdout or '', re.IGNORECASE)
        if expected in {value.upper() for value in fingerprints}:
            return True
    return False


def _normalize_hostname(value: object) -> str:
    name = str(value or '').strip().rstrip('.').lower()
    if (
        not name
        or len(name) > 253
        or name.endswith(('.in-addr.arpa', '.ip6.arpa'))
        or '/' in name
        or ':' in name
        or ' ' in name
    ):
        return ''
    try:
        ascii_name = name.encode('idna').decode('ascii')
    except UnicodeError:
        return ''
    labels = ascii_name.split('.')
    if any(
        not label
        or len(label) > 63
        or not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]*[a-z0-9])?', label)
        for label in labels
    ):
        return ''
    return ascii_name


def _create_root_ca(now: datetime.datetime):
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    subject = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'TikLocal'),
        x509.NameAttribute(NameOID.COMMON_NAME, 'TikLocal Local CA'),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=ROOT_LIFETIME_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    return key, cert


def _create_server_certificate(ca_key, ca_cert, hostnames, ip_addresses, now):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    common_name = next((name for name in hostnames if name != 'localhost' and len(name) <= 64), 'localhost')
    subject = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'TikLocal'),
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])
    san_values = [x509.DNSName(name) for name in hostnames]
    san_values.extend(x509.IPAddress(ipaddress.ip_address(value)) for value in ip_addresses)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=LEAF_LIFETIME_DAYS))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName(san_values), critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    return key, cert


def _root_is_usable(key, cert, now: datetime.datetime) -> bool:
    if cert.subject != cert.issuer or cert.not_valid_after_utc <= now + datetime.timedelta(days=365):
        return False
    return _public_keys_match(key, cert)


def _leaf_is_usable(key, cert, ca_cert, hostnames, ip_addresses, now) -> bool:
    if cert.not_valid_after_utc <= now + datetime.timedelta(days=RENEW_BEFORE_DAYS):
        return False
    if cert.issuer != ca_cert.subject or not _public_keys_match(key, cert):
        return False
    try:
        ca_cert.public_key().verify(
            cert.signature,
            cert.tbs_certificate_bytes,
            padding.PKCS1v15(),
            cert.signature_hash_algorithm,
        )
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except (ValueError, TypeError, InvalidSignature, x509.ExtensionNotFound):
        return False
    cert_names = set(san.get_values_for_type(x509.DNSName))
    cert_ips = {str(value) for value in san.get_values_for_type(x509.IPAddress)}
    return set(hostnames).issubset(cert_names) and set(ip_addresses).issubset(cert_ips)


def _public_keys_match(key, cert) -> bool:
    private_public = key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    cert_public = cert.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_public == cert_public


def _load_private_key(path: Path):
    return serialization.load_pem_private_key(path.read_bytes(), password=None)


def _load_certificate(path: Path) -> x509.Certificate:
    return x509.load_pem_x509_certificate(path.read_bytes())


def _write_private_key(path: Path, key) -> None:
    payload = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    _atomic_write(path, payload, 0o600)


def _write_certificate(path: Path, cert: x509.Certificate) -> None:
    _atomic_write(path, cert.public_bytes(serialization.Encoding.PEM), 0o644)


def _atomic_write(path: Path, payload: bytes, mode: int) -> None:
    temp_path = path.with_suffix(f'{path.suffix}.tmp')
    temp_path.write_bytes(payload)
    try:
        os.chmod(temp_path, mode)
    except OSError:
        pass
    os.replace(temp_path, path)
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def _fingerprint(cert: x509.Certificate) -> str:
    value = cert.fingerprint(hashes.SHA256()).hex().upper()
    return ':'.join(value[index:index + 2] for index in range(0, len(value), 2))
