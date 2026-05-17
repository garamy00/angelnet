"""AngelNet 호출 관련 도메인 예외 계층."""

from __future__ import annotations

from typing import Any


class AngelNetError(Exception):
    """모든 AngelNet 호출 예외의 기반."""


class AuthError(AngelNetError):
    """토큰 발급 실패 또는 401."""


class BotBlockedError(AngelNetError):
    """서버가 자동화 호출이라고 차단(`Automated requests are not allowed`)."""


class SchemaError(AngelNetError):
    """GraphQL 스키마 변경 등으로 validation 실패."""


class ApiError(AngelNetError):
    """그 외 4xx/5xx 응답."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        payload: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class MappingError(AngelNetError):
    """타임시트 카테고리 → 프로젝트 매핑 누락. timesheet 서브패키지가 사용."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = list(missing)
        super().__init__(f"unmapped categories: {', '.join(self.missing)}")
