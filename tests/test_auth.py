"""auth 모듈 — Keychain 부분 단위 테스트."""

import subprocess
import time
from unittest.mock import MagicMock

import pytest

from angeldash._common.auth import (
    KEYCHAIN_SERVICE,
    KeychainStore,
    TokenCache,
)


def test_keychain_get_returns_password_when_security_succeeds(monkeypatch):
    fake_run = MagicMock(
        return_value=subprocess.CompletedProcess(
            args=[], returncode=0, stdout="test-password\n", stderr=""
        )
    )
    monkeypatch.setattr(subprocess, "run", fake_run)

    store = KeychainStore(account="testuser")
    assert store.get() == "test-password"

    args, _ = fake_run.call_args
    assert args[0][:7] == [
        "security",
        "find-generic-password",
        "-s",
        KEYCHAIN_SERVICE,
        "-a",
        "testuser",
        "-w",
    ]


def test_keychain_get_returns_none_when_not_found(monkeypatch):
    fake_run = MagicMock(
        return_value=subprocess.CompletedProcess(
            args=[], returncode=44, stdout="", stderr="not found"
        )
    )
    monkeypatch.setattr(subprocess, "run", fake_run)

    store = KeychainStore(account="testuser")
    assert store.get() is None


def test_keychain_save_invokes_add_generic_password(monkeypatch):
    fake_run = MagicMock(
        return_value=subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
    )
    monkeypatch.setattr(subprocess, "run", fake_run)

    store = KeychainStore(account="testuser")
    store.save("newpass")

    args, _ = fake_run.call_args
    assert "add-generic-password" in args[0]
    assert "-U" in args[0]
    pwd_idx = args[0].index("-w") + 1
    assert args[0][pwd_idx] == "newpass"


def test_keychain_save_raises_on_failure(monkeypatch):
    fake_run = MagicMock(
        return_value=subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="permission denied"
        )
    )
    monkeypatch.setattr(subprocess, "run", fake_run)

    store = KeychainStore(account="testuser")
    with pytest.raises(RuntimeError, match="security add-generic-password"):
        store.save("x")


def test_token_cache_returns_none_when_empty():
    cache = TokenCache()
    assert cache.get() is None


def test_token_cache_returns_token_before_expiry():
    cache = TokenCache()
    cache.set("abc", expires_at=time.time() + 600)
    assert cache.get() == "abc"


def test_token_cache_returns_none_when_within_skew_window():
    # exp 가 30초 후이면 기본 skew(300초) 안쪽이므로 만료로 간주
    cache = TokenCache()
    cache.set("abc", expires_at=time.time() + 30)
    assert cache.get() is None


def test_token_cache_clear_drops_value():
    cache = TokenCache()
    cache.set("abc", expires_at=time.time() + 600)
    cache.clear()
    assert cache.get() is None
