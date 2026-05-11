"""인증 자료(패스워드) 보관소 및 토큰 라이프사이클.

이 모듈은 Task 4 에서 KeychainStore 만 도입하고, Task 5 에서
TokenCache 를 추가한다.
"""

from __future__ import annotations

import logging
import subprocess
import time

logger = logging.getLogger(__name__)

KEYCHAIN_SERVICE = "angeldash"


class KeychainStore:
    """macOS Keychain 의 generic-password 항목을 다루는 얇은 래퍼.

    `security` CLI 를 subprocess.run(list) 형태로 호출한다 (shell=True 금지).
    save() 시 패스워드가 프로세스 인자로 전달되어 짧은 시간 ps aux 에 노출될 수 있다.
    단일 사용자 로컬 환경에서 허용되는 위험으로 판단한다.
    """

    def __init__(self, account: str, service: str = KEYCHAIN_SERVICE) -> None:
        self.account = account
        self.service = service

    def get(self) -> str | None:
        """저장된 패스워드를 반환한다. 없으면 None."""
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-s",
                self.service,
                "-a",
                self.account,
                "-w",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            logger.debug(
                "Keychain miss for account=%s rc=%d", self.account, result.returncode
            )
            return None
        return result.stdout.strip() or None

    def save(self, password: str) -> None:
        """패스워드를 저장(또는 덮어쓰기)한다. 실패 시 RuntimeError."""
        result = subprocess.run(
            [
                "security",
                "add-generic-password",
                "-s",
                self.service,
                "-a",
                self.account,
                "-w",
                password,
                "-U",  # 기존 항목 있으면 업데이트
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"security add-generic-password failed: rc={result.returncode} "
                f"stderr={result.stderr.strip()}"
            )
        logger.info("Password stored to keychain for account=%s", self.account)


class TokenCache:
    """JWT 토큰을 만료 전까지 메모리에 보관한다.

    skew 초만큼 만료 시점보다 일찍 무효화하여 만료 직전 호출 실패를 막는다.
    """

    def __init__(self, skew_seconds: int = 300) -> None:
        self._token: str | None = None
        self._expires_at: float = 0.0
        self._skew = skew_seconds

    def get(self) -> str | None:
        """유효한 토큰을 반환한다. 없거나 만료(skew 포함) 시 None."""
        if self._token is None:
            return None
        if time.time() + self._skew >= self._expires_at:
            return None
        return self._token

    def set(self, token: str, expires_at: float) -> None:
        """토큰과 만료 epoch 시각을 저장한다."""
        self._token = token
        self._expires_at = expires_at

    def clear(self) -> None:
        """저장된 토큰을 삭제한다."""
        self._token = None
        self._expires_at = 0.0
