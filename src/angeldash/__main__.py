"""angeldash CLI 진입점."""

from __future__ import annotations

import argparse
import getpass
import logging
import os
import sys

import uvicorn

from ._common.auth import KeychainStore
from .server import build_app

logger = logging.getLogger(__name__)

DEFAULT_PORT = 5173
# 로컬 전용 default. 사내 다른 사람도 접근시키려면 --host 0.0.0.0
DEFAULT_HOST = "127.0.0.1"


def _ensure_password(user_id: str) -> str:
    """패스워드를 Keychain → env → prompt 순으로 확보. 첫 입력은 Keychain 에 저장."""
    keychain = KeychainStore(account=user_id)

    if pwd := keychain.get():
        logger.info("Loaded password from keychain")
        return pwd

    if pwd := os.environ.get("ANGELNET_PWD"):
        logger.info("Loaded password from env, persisting to keychain")
        keychain.save(pwd)
        return pwd

    pwd = getpass.getpass(f"AngelNet password for {user_id}: ")
    if not pwd:
        raise SystemExit("Password is required")
    keychain.save(pwd)
    print("Password saved to macOS Keychain (service=angeldash).", file=sys.stderr)
    return pwd


def main() -> None:
    """CLI 진입점: argparse → 패스워드 확보 → uvicorn 실행."""
    parser = argparse.ArgumentParser(description="AngelNet 회의실 대시보드 서버")
    parser.add_argument(
        "--user",
        default=os.environ.get("ANGELNET_USER"),
        help="AngelNet 사용자 ID (또는 환경변수 ANGELNET_USER)",
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    if not args.user:
        raise SystemExit(
            "AngelNet 사용자 ID 가 필요합니다. "
            "환경변수 ANGELNET_USER 를 설정하거나 --user 옵션을 지정하세요."
        )

    log_format = "%(asctime)s %(levelname)s %(name)s %(message)s"
    logging.basicConfig(
        level=args.log_level.upper(),
        format=log_format,
    )

    pwd = _ensure_password(args.user)
    os.environ["ANGELNET_PWD"] = pwd

    # uvicorn 의 기본 log_config 는 timestamp 없는 access log 를 출력한다.
    # 자체 LOGGING_CONFIG 의 formatter 만 timestamp 포함 형식으로 교체해서
    # 모든 라인이 일관된 prefix 를 가지게 한다.
    from uvicorn.config import LOGGING_CONFIG
    uv_log_cfg = {**LOGGING_CONFIG}
    uv_log_cfg["formatters"] = {
        **LOGGING_CONFIG["formatters"],
        "default": {
            "()": "uvicorn.logging.DefaultFormatter",
            "fmt": "%(asctime)s %(levelprefix)s %(message)s",
            "use_colors": None,
        },
        "access": {
            "()": "uvicorn.logging.AccessFormatter",
            "fmt": (
                "%(asctime)s %(levelprefix)s "
                '%(client_addr)s - "%(request_line)s" %(status_code)s'
            ),
            "use_colors": None,
        },
    }

    app = build_app(user_id=args.user)
    uvicorn.run(
        app, host=args.host, port=args.port,
        log_level=args.log_level, log_config=uv_log_cfg,
    )


if __name__ == "__main__":
    main()
