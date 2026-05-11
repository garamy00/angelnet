"""Pydantic 모델: 예약·사용자 도메인 객체."""

from __future__ import annotations

import datetime
import re
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator

_TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d:[0-5]\d$")
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class User(BaseModel):
    """현재 로그인 사용자 정보 (토큰 응답에서 추출)."""

    user_id: str
    name: str
    email: str | None = None


class Reservation(BaseModel):
    """AngelNet 예약 항목 (Spring REST 응답을 from_spring 으로 정규화)."""

    id: str
    creator_name: str
    creator_id: str | None = None
    room_id: str
    room: str
    # 서버 응답을 신뢰하므로 date/time 형식 검증 생략.
    # 이상 시 client 가 ApiError 로 처리.
    date: str
    time: str
    duration: int
    is_all_day: bool
    is_repeat: bool
    weekdays: int | None = None
    reason: str
    end_date: str | None = None

    @field_validator("end_date", mode="before")
    @classmethod
    def empty_string_to_none(cls, v: object) -> object:
        # 서버가 비반복 예약에 대해 빈 문자열을 보낼 수 있어 None 으로 정규화
        if isinstance(v, str) and v == "":
            return None
        return v

    def occurs_on(self, iso_date: str) -> bool:
        """예약이 주어진 날짜(YYYY-MM-DD)에 발생하는지 판단.

        - is_repeat=True : 시작~종료 범위 + weekdays 비트 매칭
          (weekdays 비트: 월=1 화=2 수=4 목=8 금=16 토=32 일=64, 0/None 이면 매일)
        - is_repeat=False + end_date 있음: 시작~종료 범위 매일 발생
          (AngelNet 의 종일 기간 예약: isRepeat=0 + endDate 있는 multi-day 케이스)
        - is_repeat=False + end_date 없음: 시작일에만 발생

        이 로직은 `src/angeldash/static/app.js` 의 reservationOccursOn() 과
        동일하게 유지되어야 한다. 양쪽 동시 수정 필요.
        """
        if self.is_repeat:
            if iso_date < self.date:
                return False
            if self.end_date and iso_date > self.end_date:
                return False
            if not self.weekdays:
                return True
            d = datetime.date.fromisoformat(iso_date)
            bit = 1 << (d.isoweekday() - 1)
            return (self.weekdays & bit) != 0
        # 비반복 multi-day
        if self.end_date:
            return self.date <= iso_date <= self.end_date
        # 비반복 단일
        return self.date == iso_date

    @classmethod
    def from_spring(cls, raw: dict) -> Reservation:
        """Spring REST 응답 row 를 정규화해 Reservation 인스턴스로 변환.

        - camelCase → snake_case
        - epoch ms (date/endDate) → "YYYY-MM-DD" (Asia/Seoul 기준)
        - 0/1 int (isAllDay/isRepeat) → bool
        - roomId int → str
        """
        return cls(
            id=str(raw["id"]),
            creator_name=raw.get("creatorName") or "",
            creator_id=raw.get("creatorId"),
            room_id=str(raw["roomId"]),
            room=raw.get("room") or "",
            date=_epoch_ms_to_iso_kst(raw["date"]),
            time=raw.get("time") or "00:00:00",
            duration=int(raw.get("duration") or 0),
            is_all_day=bool(raw.get("isAllDay")),
            is_repeat=bool(raw.get("isRepeat")),
            weekdays=raw.get("weekdays"),
            reason=raw.get("reason") or "",
            end_date=(
                _epoch_ms_to_iso_kst(raw["endDate"]) if raw.get("endDate") else None
            ),
        )


_KST = ZoneInfo("Asia/Seoul")


def _epoch_ms_to_iso_kst(ms: int | None) -> str:
    """epoch milliseconds 를 Asia/Seoul YYYY-MM-DD 로 변환."""
    if ms is None:
        return ""
    dt = datetime.datetime.fromtimestamp(ms / 1000, tz=_KST)
    return dt.strftime("%Y-%m-%d")


class ReservationCreate(BaseModel):
    """예약 생성 요청 본문."""

    date: Annotated[str, Field(min_length=10, max_length=10)]
    time: str
    duration: Annotated[int, Field(ge=1, le=720)]
    room_id: Annotated[str, Field(min_length=1)]
    reason: Annotated[str, Field(min_length=1, max_length=200)]
    participants: Annotated[int, Field(ge=1, le=999)]

    @field_validator("date")
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        if not _DATE_PATTERN.match(v):
            raise ValueError("date must be YYYY-MM-DD")
        try:
            datetime.date.fromisoformat(v)
        except ValueError as exc:
            raise ValueError(f"date must be a valid calendar date: {v}") from exc
        return v

    @field_validator("time")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        if not _TIME_PATTERN.match(v):
            raise ValueError("time must be HH:MM:SS")
        return v
