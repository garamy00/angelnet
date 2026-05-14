"""Jinja2 SandboxedEnvironment + 출력 컨텍스트 빌더 + 렌더 함수.

스펙 6.4 참조. 모든 출력 (팀장 보고, UpNote 제목/본문) 은 이 모듈을 거친다.
"""

from __future__ import annotations

import datetime
import sqlite3
from typing import Any

from jinja2 import TemplateSyntaxError, select_autoescape
from jinja2.sandbox import SandboxedEnvironment

from . import db

_DAY_KR = ["월", "화", "수", "목", "금", "토", "일"]
_DAY_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _env() -> SandboxedEnvironment:
    """SandboxedEnvironment 인스턴스. 매 호출마다 새로 만들어 캐시 의도 없이 단순화."""
    env = SandboxedEnvironment(
        autoescape=select_autoescape(default_for_string=False),
        keep_trailing_newline=False,
        trim_blocks=False,
        lstrip_blocks=False,
    )
    return env


def _entry_dict(row: dict[str, Any]) -> dict[str, Any]:
    """DB row → 템플릿에 노출할 entry 객체.

    body 는 trailing whitespace/newline 을 제거한 형태로 노출한다.
    텍스트에어리어 입력 끝에 자동 추가되는 newline 이 템플릿의 줄바꿈과 합쳐져
    카테고리 사이 빈 줄이 두 줄로 보이는 문제를 방지하기 위함.
    """
    body = (row.get("body_md") or "").rstrip()
    if body:
        first, _, rest = body.partition("\n")
        body_first_line = first
        body_rest = rest.rstrip()
    else:
        body_first_line = ""
        body_rest = ""
    return {
        "date": row.get("date"),
        "category": row["category"],
        "hours": row["hours"],
        "body": body,
        "body_first_line": body_first_line,
        "body_rest": body_rest,
    }


def _day_obj(date_str: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    """날짜 객체 + 그날 entries."""
    d = datetime.date.fromisoformat(date_str)
    return {
        "date": date_str,
        "yy": f"{d.year % 100:02d}",
        "yyyy": str(d.year),
        "mm": f"{d.month:02d}",
        "dd": f"{d.day:02d}",
        "day_kr": _DAY_KR[d.weekday()],
        "day_en": _DAY_EN[d.weekday()],
        "weekday": d.weekday(),
        "entries": [_entry_dict(e) for e in entries],
    }


def _week_globals(week_iso: str) -> dict[str, Any]:
    """주차 관련 ctx 변수.

    포함: yy, yyyy, ww (ISO 주차), mm (월요일 기준 월),
          ww_of_month (월의 몇 번째 주), week_start/end, week_start_mmdd 등.

    ww_of_month 는 월요일의 일자 기준 — 1~7일은 1주, 8~14일은 2주, ...
    """
    year_str, w_str = week_iso.split("-W")
    year = int(year_str)
    week = int(w_str)
    # ISO 주는 월요일~일요일, 우리는 월~금만 다룬다 (출력에 영향 없음)
    monday = datetime.date.fromisocalendar(year, week, 1)
    friday = monday + datetime.timedelta(days=4)
    # 월의 몇 번째 주 — 월요일의 day 기준. 1주차 = 그 달의 첫 월~7일.
    week_of_month = (monday.day - 1) // 7 + 1
    return {
        "yy": f"{year % 100:02d}",
        "yyyy": str(year),
        "ww": f"{week:02d}",
        "mm": f"{monday.month:02d}",
        "ww_of_month": str(week_of_month),
        "week_iso": week_iso,
        "week_start": monday.isoformat(),
        "week_end": friday.isoformat(),
        "week_start_mmdd": f"{monday.month:02d}/{monday.day:02d}",
        "week_end_mmdd": f"{friday.month:02d}/{friday.day:02d}",
        "week_label": (
            f"{year % 100:02d}년 W{week:02d} "
            f"({monday.month:02d}/{monday.day:02d} ~ "
            f"{friday.month:02d}/{friday.day:02d})"
        ),
    }


# ─── 컨텍스트 빌더 ──────────────────────────────────────


def build_week_context(
    conn: sqlite3.Connection, *, week_iso: str
) -> dict[str, Any]:
    """UpNote 본문/제목용 컨텍스트.

    - days: 그 주의 entries 있는 날짜만
    - week_notes: 공백 트림 후 비면 None
    """
    week = db.get_week(conn, week_iso)
    days = []
    for d in week:
        if not d["entries"]:
            # 빈 날도 meta 가 있을 수 있지만 정책: entries 가 비면 day 자체 제외 (기존 동작)
            continue
        meta = db.get_daily_meta(conn, d["date"])
        day_obj = _day_obj(d["date"], d["entries"])
        day_obj["source_commit"] = meta["source_commit"]
        day_obj["source_commit_label"] = db.SOURCE_COMMIT_LABELS.get(
            meta["source_commit"], meta["source_commit"]
        )
        day_obj["misc_note"] = (meta["misc_note"] or "").rstrip()
        days.append(day_obj)
    raw_note = db.get_week_note(conn, week_iso)
    note = raw_note.strip() or None
    return {
        **_week_globals(week_iso),
        "days": days,
        "week_notes": note,
    }


def build_team_report_context(
    conn: sqlite3.Connection,
    *,
    date: str | None = None,
    week_iso: str | None = None,
) -> dict[str, Any]:
    """팀장 보고용 컨텍스트.

    date 가 주어지면 그 날짜의 entries 만, week_iso 가 주어지면 그 주
    모든 날짜의 entries 를 날짜 오름차순 → order_index 순으로 평탄화.
    """
    if date is not None and week_iso is not None:
        raise ValueError("date 와 week_iso 는 동시에 줄 수 없다")
    if date is None and week_iso is None:
        raise ValueError("date 또는 week_iso 둘 중 하나는 필요하다")

    if date is not None:
        day = db.get_day(conn, date)
        entries = [_entry_dict({**e, "date": date}) for e in day["entries"]]
        meta = db.get_daily_meta(conn, date)
        target_label = date
        d = datetime.date.fromisoformat(date)
        globals_ = {
            "yy": f"{d.year % 100:02d}",
            "yyyy": str(d.year),
            "mm": f"{d.month:02d}",
            "dd": f"{d.day:02d}",
            "day_kr": _DAY_KR[d.weekday()],
            "day_en": _DAY_EN[d.weekday()],
        }
        source_commit = meta["source_commit"]
        misc_note = (meta["misc_note"] or "").rstrip()
    else:
        week = db.get_week(conn, week_iso)
        entries: list[dict[str, Any]] = []
        for day in week:
            for e in day["entries"]:
                entries.append(_entry_dict({**e, "date": day["date"]}))
        target_label = "이번 주 전체"
        globals_ = _week_globals(week_iso)
        # 주 단위: team-report 는 보통 일일 단위. 주 단위에서는 source_commit/misc_note 미사용.
        source_commit = "none"
        misc_note = ""

    return {
        **globals_,
        "entries": entries,
        "target_label": target_label,
        "source_commit": source_commit,
        "source_commit_label": db.SOURCE_COMMIT_LABELS.get(source_commit, source_commit),
        "misc_note": misc_note,
    }


# ─── 렌더 함수 ──────────────────────────────────────────


def render_team_report(
    template: str, ctx: dict[str, Any], *, repeat_entries: bool = True
) -> str:
    """팀장 보고 텍스트 렌더. TemplateSyntaxError 는 그대로 raise.

    repeat_entries=False 인 경우 (테스트용) ctx['entries'] 의 첫 entry 를
    'entry' 단일 변수로도 노출한다.
    """
    env = _env()
    t = env.from_string(template)
    if not repeat_entries and ctx.get("entries"):
        ctx = {**ctx, "entry": ctx["entries"][0]}
    return t.render(**ctx)


def render_upnote_title(template: str, ctx: dict[str, Any]) -> str:
    """UpNote 제목 렌더."""
    return _env().from_string(template).render(**ctx)


def render_upnote_body(template: str, ctx: dict[str, Any]) -> str:
    """UpNote 본문 렌더."""
    return _env().from_string(template).render(**ctx)


def validate_template(template: str) -> None:
    """syntax 만 검증한다. TemplateSyntaxError 를 그대로 raise."""
    _env().from_string(template)


__all__ = [
    "build_week_context",
    "build_team_report_context",
    "render_team_report",
    "render_upnote_title",
    "render_upnote_body",
    "validate_template",
    "TemplateSyntaxError",
]
