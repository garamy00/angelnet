"""weekly_table 모듈 unit 테스트."""

from __future__ import annotations

import pytest

from angeldash.timesheet import weekly_table


@pytest.fixture
def seeded_conn(conn):
    """projects + mappings + 이번주/지난주 entries 시드."""
    # 프로젝트 2개
    conn.execute(
        "INSERT INTO projects(id, name, active) VALUES(1, 'OAM 공통', 1)"
    )
    conn.execute(
        "INSERT INTO projects(id, name, active) VALUES(2, 'SKT SMSC', 1)"
    )
    # 카테고리 매핑
    conn.execute(
        "INSERT INTO mappings(category, project_id, excluded) "
        "VALUES('차세대OAM', 1, 0)"
    )
    conn.execute(
        "INSERT INTO mappings(category, project_id, excluded) "
        "VALUES('SMSC 리빌딩', 2, 0)"
    )
    # 이번주 = 2026-W20 → 월요일 = 2026-05-11
    # 지난주 = 2026-W19 → 월요일 = 2026-05-04
    for date in ("2026-05-11", "2026-05-12"):
        conn.execute("INSERT INTO days(date, week_iso) VALUES(?, '2026-W20')", (date,))
    for date in ("2026-05-04",):
        conn.execute("INSERT INTO days(date, week_iso) VALUES(?, '2026-W19')", (date,))
    # entries
    conn.execute(
        "INSERT INTO entries(date, order_index, category, hours, body_md) "
        "VALUES('2026-05-11', 0, '차세대OAM', 4, '코어 인프라 구현')"
    )
    conn.execute(
        "INSERT INTO entries(date, order_index, category, hours, body_md) "
        "VALUES('2026-05-12', 0, 'SMSC 리빌딩', 4, '통계 기능 개발')"
    )
    conn.execute(
        "INSERT INTO entries(date, order_index, category, hours, body_md) "
        "VALUES('2026-05-04', 0, '차세대OAM', 4, '설계 문서 작성')"
    )
    # 매핑 없는 카테고리 (this week)
    conn.execute(
        "INSERT INTO entries(date, order_index, category, hours, body_md) "
        "VALUES('2026-05-12', 1, '미매핑 카테고리', 1, '잡일')"
    )
    conn.commit()
    return conn


def test_build_rows_groups_by_project(seeded_conn) -> None:
    rows = weekly_table.build_weekly_table_rows(
        seeded_conn, week_iso="2026-W20",
    )
    names = [r["project_name"] for r in rows]
    assert "OAM 공통" in names
    assert "SKT SMSC" in names
    assert "(매핑 없음)" in names


def test_build_rows_last_week_filled(seeded_conn) -> None:
    rows = weekly_table.build_weekly_table_rows(
        seeded_conn, week_iso="2026-W20",
    )
    oam = next(r for r in rows if r["project_name"] == "OAM 공통")
    assert "설계 문서 작성" in oam["last_week"]
    assert "코어 인프라 구현" in oam["this_week"]


def test_build_rows_preserves_manual(seeded_conn) -> None:
    manual = [
        {"project_name": "OAM 공통", "last_week": "old", "this_week": "old",
         "next_week": "다음주 X 검토", "note": "비고 메모"},
    ]
    rows = weekly_table.build_weekly_table_rows(
        seeded_conn, week_iso="2026-W20", preserve_manual_rows=manual,
    )
    oam = next(r for r in rows if r["project_name"] == "OAM 공통")
    assert oam["next_week"] == "다음주 X 검토"
    assert oam["note"] == "비고 메모"
    # last/this_week 는 자동 채움으로 덮어쓰기
    assert oam["last_week"] != "old"
    assert oam["this_week"] != "old"


def test_render_html_table_escapes_and_styles() -> None:
    rows = [{
        "project_name": "<b>OAM</b>", "last_week": "*) cat\n  - body",
        "this_week": "", "next_week": "", "note": "",
    }]
    html = weekly_table.render_html_table(rows)
    assert "&lt;b&gt;OAM&lt;/b&gt;" in html  # escape
    assert "white-space:pre-wrap" in html
    assert "border-collapse:collapse" in html


def test_render_markdown_table_handles_newlines_and_pipes() -> None:
    rows = [{
        "project_name": "A | B", "last_week": "line1\nline2",
        "this_week": "", "next_week": "", "note": "",
    }]
    md = weekly_table.render_markdown_table(rows)
    assert "A \\| B" in md  # pipe escape
    assert "line1<br>line2" in md  # newline → <br>
    assert md.startswith("| 프로젝트 | 지난주 한 일")  # header


def test_prev_week_iso_year_boundary() -> None:
    assert weekly_table._prev_week_iso("2026-W01") == "2025-W52"
