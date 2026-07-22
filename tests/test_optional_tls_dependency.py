import subprocess
import sys

import pytest

from tiklocal import run


def test_http_app_imports_without_cryptography():
    script = r'''
import builtins
import sys

real_import = builtins.__import__

def import_without_cryptography(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "cryptography" or name.startswith("cryptography."):
        raise ModuleNotFoundError("No module named 'cryptography'", name="cryptography")
    return real_import(name, globals, locals, fromlist, level)

builtins.__import__ = import_without_cryptography
import tiklocal.app
import tiklocal.run

assert "tiklocal.services.tls" not in sys.modules
'''

    result = subprocess.run(
        [sys.executable, '-c', script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_managed_https_explains_how_to_install_optional_dependency(monkeypatch):
    def missing_tls_dependency(_module_name):
        raise ModuleNotFoundError("No module named 'cryptography'", name='cryptography')

    monkeypatch.setattr(run.importlib, 'import_module', missing_tls_dependency)

    with pytest.raises(RuntimeError, match=r"pip install 'TikLocal\[https\]'"):
        run._load_tls_service()
