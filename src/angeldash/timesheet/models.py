"""Pydantic 모델 — API request/response 및 내부 데이터.

EntryInput / WeekNoteInput 등 *Input* 접미사 모델은 사용자가 보내는 페이로드용 (validation 강함).
Entry / WeekNote 등은 DB 에서 읽어온 도메인 객체 (id 등 자동 필드 포함).

User 는 angeldash._common.models 의 것을 공유 (회의실 모듈과 동일).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

# 회의실 서브패키지와 같은 User 타입 사용 → 외부에서 `from .models import User` 호환
from .._common.models import User  # noqa: F401


class EntryInput(BaseModel):
    """클라이언트가 보내는 보고서 항목 페이로드."""

    category: str = Field(min_length=1)
    hours: float = Field(ge=0, lt=24)
    body_md: str = ""

    @field_validator("category")
    @classmethod
    def strip_category(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("category must be non-empty after strip")
        return s


class Entry(BaseModel):
    """DB 의 entries 한 row + 파생 필드."""

    id: int
    date: str
    order_index: int
    category: str
    hours: float
    body_md: str

    @property
    def body_first_line(self) -> str:
        """본문 첫 줄. 본문이 비면 빈 문자열."""
        if not self.body_md:
            return ""
        return self.body_md.split("\n", 1)[0]

    @property
    def body_rest(self) -> str:
        """본문 둘째 줄부터 (rstrip)."""
        if not self.body_md or "\n" not in self.body_md:
            return ""
        return self.body_md.split("\n", 1)[1].rstrip()


class WeekNoteInput(BaseModel):
    """주별 자유 메모 페이로드."""

    body_md: str = ""


class WeekNote(BaseModel):
    week_iso: str
    body_md: str
    updated_at: str


class Project(BaseModel):
    id: int
    name: str = Field(min_length=1)
    # 회사 시스템의 work_type (예: '개발', '시험/지원', '영업', '세미나').
    # 같은 프로젝트명에 여러 task 가 등록될 수 있으므로 구분 키.
    work_type: str = ""
    remote_id: str | None = None
    active: bool = True


class ProjectInput(BaseModel):
    name: str = Field(min_length=1)
    work_type: str = ""
    remote_id: str | None = None
    active: bool = True


class Mapping(BaseModel):
    """카테고리 → 프로젝트 매핑.

    project_id 가 None 이고 excluded=True 면 의도적으로 타임시트 미입력.
    project_id 가 None 이고 excluded=False 면 매핑이 누락된 상태.
    weekly_project_name 은 주간업무보고에서 사용할 별도 이름 (None=미설정).
    """

    category: str
    project_id: int | None = None
    excluded: bool = False
    weekly_project_name: str | None = None


class ActionLog(BaseModel):
    id: int
    action_type: str
    target_range: str
    status: str
    message: str | None = None
    created_at: str


class DailyMetaInput(BaseModel):
    """PUT /api/days/{date}/meta 페이로드."""

    source_commit: str  # 'done' | 'later' | 'local_backup' | 'none'
    misc_note: str = ""
