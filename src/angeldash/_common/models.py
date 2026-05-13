"""도메인 공유 Pydantic 모델 — 현재는 User 하나."""

from __future__ import annotations

from pydantic import BaseModel


class User(BaseModel):
    """현재 로그인 사용자 정보 (토큰 응답에서 추출)."""

    user_id: str
    name: str
    email: str | None = None
