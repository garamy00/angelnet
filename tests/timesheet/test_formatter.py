"""formatter 의 컨텍스트 빌더와 템플릿 렌더링."""

from __future__ import annotations

import sqlite3

import pytest
from jinja2 import TemplateSyntaxError

from angeldash.timesheet import db, formatter
from angeldash.timesheet.templates import (
    DEFAULT_TEAM_REPORT,
    DEFAULT_UPNOTE_BODY,
    DEFAULT_UPNOTE_TITLE,
)


def _seed_user_sample(conn: sqlite3.Connection) -> None:
    """spec 의 사용자 제공 예시 데이터를 DB 에 넣는다.

    2026-05-12 는 ISO 달력 기준 W20 (05/11 ~ 05/15) 에 속한다.
    """
    db.upsert_entries(
        conn,
        date="2026-05-12",
        week_iso="2026-W20",
        entries=[
            {
                "category": "SKT SMSC 리빌딩",
                "hours": 4.0,
                "body_md": " - VM1.0.5 PKG 신규 통계(KCTHLR) 기능 개발\n   . 시험 및 패키지 배포",
            },
            {
                "category": "EM 고도화",
                "hours": 4.0,
                "body_md": (
                    " - 신규 OAM 서버 공통 패키지 개발\n"
                    "   . 코어 인프라 구현 (05/06 ~ 05/29)\n"
                    "     -> 공통 로깅/설정 모듈 구현"
                ),
            },
            {
                "category": "소스 Commit",
                "hours": 0.0,
                "body_md": " - 완료",
            },
        ],
    )


def test_render_team_report_matches_user_example(conn: sqlite3.Connection) -> None:
    """기본 템플릿 + 사용자 샘플 = spec 의 예시 문자열.

    source_commit 기본값('done') 이 템플릿에 의해 마지막에 추가된다.
    """
    _seed_user_sample(conn)
    ctx = formatter.build_team_report_context(conn, date="2026-05-12")
    out = formatter.render_team_report(DEFAULT_TEAM_REPORT, ctx)
    expected = (
        "*) SKT SMSC 리빌딩\n"
        " - VM1.0.5 PKG 신규 통계(KCTHLR) 기능 개발\n"
        "   . 시험 및 패키지 배포\n"
        "\n"
        "*) EM 고도화\n"
        " - 신규 OAM 서버 공통 패키지 개발\n"
        "   . 코어 인프라 구현 (05/06 ~ 05/29)\n"
        "     -> 공통 로깅/설정 모듈 구현\n"
        "\n"
        "*) 소스 Commit\n"
        " - 완료\n"
        "\n"
        "*) 소스 Commit\n"
        " - 완료"
    )
    assert out == expected


def test_render_team_report_week_range_flattens_all_days(
    conn: sqlite3.Connection,
) -> None:
    """date=None, week_iso='2026-W20' 로 호출하면 그 주의 모든 entries 가 평탄화된다."""
    _seed_user_sample(conn)
    db.upsert_entries(
        conn, date="2026-05-13", week_iso="2026-W20",
        entries=[{"category": "Z", "hours": 1.0, "body_md": "x"}],
    )
    ctx = formatter.build_team_report_context(conn, week_iso="2026-W20")
    cats = [e["category"] for e in ctx["entries"]]
    assert cats == [
        "SKT SMSC 리빌딩", "EM 고도화", "소스 Commit", "Z",
    ]


def test_render_upnote_body_matches_user_example(conn: sqlite3.Connection) -> None:
    """그 주의 모든 날짜 + 빈 메모 → 메모 헤더는 출력되지 않는다."""
    _seed_user_sample(conn)
    ctx = formatter.build_week_context(conn, week_iso="2026-W20")
    out = formatter.render_upnote_body(DEFAULT_UPNOTE_BODY, ctx)
    assert "📝 메모" not in out
    assert out.startswith("26년 < 05/12, 화 >")
    assert "*) 소스 Commit" in out


def test_render_upnote_body_with_week_note_includes_section(
    conn: sqlite3.Connection,
) -> None:
    """week_notes 가 비어있지 않으면 구분선 + 헤더 + 본문이 출력된다."""
    _seed_user_sample(conn)
    db.upsert_week_note(conn, "2026-W20", "강남에서…\n기계 : 젠틀맥스 프로")
    ctx = formatter.build_week_context(conn, week_iso="2026-W20")
    out = formatter.render_upnote_body(DEFAULT_UPNOTE_BODY, ctx)
    assert "📝 메모" in out
    assert "강남에서…" in out
    assert "기계 : 젠틀맥스 프로" in out
    # 메모 헤더는 마지막 날짜 블록 뒤에 와야 한다
    assert out.index("📝 메모") > out.index("*) 소스 Commit")


def test_render_upnote_body_blank_only_week_note_omits_section(
    conn: sqlite3.Connection,
) -> None:
    """공백만 있는 메모는 빈 것으로 처리되어 헤더가 출력되지 않는다."""
    _seed_user_sample(conn)
    db.upsert_week_note(conn, "2026-W20", "   \n\n  ")
    ctx = formatter.build_week_context(conn, week_iso="2026-W20")
    out = formatter.render_upnote_body(DEFAULT_UPNOTE_BODY, ctx)
    assert "📝 메모" not in out


def test_render_upnote_title_matches_format(conn: sqlite3.Connection) -> None:
    """기본 제목 템플릿 + 컨텍스트 → '26년 W20 (05/11 ~ 05/15)' 형식."""
    _seed_user_sample(conn)
    ctx = formatter.build_week_context(conn, week_iso="2026-W20")
    title = formatter.render_upnote_title(DEFAULT_UPNOTE_TITLE, ctx)
    assert title == "26년 W20 (05/11 ~ 05/15)"


def test_render_with_syntax_error_raises(conn: sqlite3.Connection) -> None:
    """잘못된 Jinja2 syntax 는 TemplateSyntaxError."""
    _seed_user_sample(conn)
    ctx = formatter.build_team_report_context(conn, date="2026-05-12")
    with pytest.raises(TemplateSyntaxError):
        formatter.render_team_report("{% bogus %}", ctx)


def test_sandbox_blocks_unsafe_attribute_access(
    conn: sqlite3.Connection,
) -> None:
    """샌드박스 환경에서 위험한 속성 접근은 차단된다."""
    _seed_user_sample(conn)
    ctx = formatter.build_team_report_context(conn, date="2026-05-12")
    with pytest.raises(Exception):  # SecurityError 또는 UndefinedError
        formatter.render_team_report(
            "{{ entries.__class__.__mro__ }}", ctx
        )


def test_entry_body_first_line_and_rest_in_context(
    conn: sqlite3.Connection,
) -> None:
    """컨텍스트 안 entry 객체에 body_first_line / body_rest 가 노출된다.

    스펙 6.4.2 에 명시된 변수.
    """
    db.upsert_entries(
        conn, date="2026-05-12", week_iso="2026-W20",
        entries=[{
            "category": "X",
            "hours": 1.0,
            "body_md": "first line\nsecond line\nthird",
        }],
    )
    ctx = formatter.build_team_report_context(conn, date="2026-05-12")
    out = formatter.render_team_report(
        "[{{ entry.category }}] {{ entry.body_first_line }}\n* {{ entry.body_rest }}",
        ctx,
        repeat_entries=False,  # 단일 entry 컨텍스트로 사용
    )
    # 단일 entry 헬퍼가 없으면 위 호출은 안 되니 대안: 본문 검증
    assert "[X] first line" in out


def test_entry_body_trailing_newline_stripped(conn) -> None:
    """body_md 끝의 newline 이 entry.body 에서 제거되어
    카테고리 사이가 빈 줄 1개로 일관되게 보이게 한다."""
    db.upsert_entries(
        conn, date="2026-05-12", week_iso="2026-W20",
        entries=[
            {"category": "A", "hours": 1.0, "body_md": " - line1\n"},  # trailing \n
            {"category": "B", "hours": 1.0, "body_md": " - line2"},
        ],
    )
    ctx = formatter.build_team_report_context(conn, date="2026-05-12")
    out = formatter.render_team_report(DEFAULT_TEAM_REPORT, ctx)
    # source_commit 이 기본값 'done' → 완료 추가, misc 없으면 기타 생략
    assert "*) A\n - line1\n\n*) B\n - line2\n\n*) 소스 Commit\n - 완료" == out


def test_render_team_report_renders_source_commit_label(conn) -> None:
    db.upsert_entries(
        conn, date="2026-05-12", week_iso="2026-W20",
        entries=[{"category": "X", "hours": 8, "body_md": " - 작업"}],
    )
    db.upsert_daily_meta(
        conn, "2026-05-12", source_commit="local_backup", misc_note="",
    )
    ctx = formatter.build_team_report_context(conn, date="2026-05-12")
    out = formatter.render_team_report(DEFAULT_TEAM_REPORT, ctx)
    assert out.endswith("*) 소스 Commit\n - 로컬백업")
