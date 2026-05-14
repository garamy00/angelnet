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


# ─── tree-merge: body 결합 시 공통 prefix 묶기 ─────────


def test_merge_bodies_identical_returns_one() -> None:
    """3개의 완전 동일한 body → 1번만 표시."""
    body = "  - 신규 OAM 서버 공통 패키지 개발\n    . 코어 인프라 구현"
    out = weekly_table._merge_bodies([body, body, body])
    assert out == body


def test_merge_bodies_shared_prefix_different_leaf() -> None:
    """공통 prefix 묶음 + leaf 만 다른 줄 enumerate."""
    bodies = [
        "  - 코어 인프라\n    -> 로깅 모듈",
        "  - 코어 인프라\n    -> DB 레이어",
        "  - 코어 인프라\n    -> 데몬 뼈대",
    ]
    out = weekly_table._merge_bodies(bodies)
    assert out == (
        "  - 코어 인프라\n"
        "    -> 로깅 모듈\n"
        "    -> DB 레이어\n"
        "    -> 데몬 뼈대"
    )


def test_merge_bodies_different_top_level_kept_in_order() -> None:
    """완전 다른 top-level entries 는 첫 등장 순으로 결합 (merge 없음)."""
    bodies = [
        "  - 회의 참석",
        "  - 보고서 작성",
    ]
    out = weekly_table._merge_bodies(bodies)
    assert out == "  - 회의 참석\n  - 보고서 작성"


def test_merge_bodies_single_body_unchanged() -> None:
    """1개 body 는 그대로 (round-trip)."""
    body = "  - X\n    . Y\n      -> Z"
    assert weekly_table._merge_bodies([body]) == body


def test_merge_bodies_empty_list_returns_empty() -> None:
    """빈 입력 → 빈 출력."""
    assert weekly_table._merge_bodies([]) == ""


# ─── weekly_project_name 우선순위 + 머지 ─────────────


def test_resolve_project_prefers_weekly_name(seeded_conn) -> None:
    """weekly_project_name 이 설정된 카테고리는 그 이름이 우선."""
    seeded_conn.execute(
        "UPDATE mappings SET weekly_project_name = 'OAM 통합' "
        "WHERE category = '차세대OAM'"
    )
    seeded_conn.commit()
    rows = weekly_table.build_weekly_table_rows(
        seeded_conn, week_iso="2026-W20",
    )
    names = [r["project_name"] for r in rows]
    assert "OAM 통합" in names  # weekly_project_name 적용
    assert "OAM 공통" not in names  # 기존 타임시트 project name 은 빠짐


def test_resolve_project_falls_back_to_project_name_when_weekly_empty(
    seeded_conn,
) -> None:
    """weekly_project_name 비어있으면 기존 타임시트 project name 사용."""
    # weekly_project_name 미설정 (default NULL) 상태
    rows = weekly_table.build_weekly_table_rows(
        seeded_conn, week_iso="2026-W20",
    )
    names = [r["project_name"] for r in rows]
    assert "OAM 공통" in names  # 기존 동작 보존


def test_resolve_project_treats_whitespace_as_unset(seeded_conn) -> None:
    """공백만 들어간 weekly_project_name 은 미설정으로 취급."""
    seeded_conn.execute(
        "UPDATE mappings SET weekly_project_name = '   ' "
        "WHERE category = '차세대OAM'"
    )
    seeded_conn.commit()
    rows = weekly_table.build_weekly_table_rows(
        seeded_conn, week_iso="2026-W20",
    )
    names = [r["project_name"] for r in rows]
    assert "OAM 공통" in names  # whitespace 만 → fallback


def test_two_categories_same_weekly_name_merged_into_one_row(
    seeded_conn,
) -> None:
    """같은 weekly_project_name 인 카테고리들의 entries 가 한 행으로 머지."""
    seeded_conn.execute(
        "UPDATE mappings SET weekly_project_name = '통합' "
        "WHERE category = '차세대OAM'"
    )
    seeded_conn.execute(
        "UPDATE mappings SET weekly_project_name = '통합' "
        "WHERE category = 'SMSC 리빌딩'"
    )
    seeded_conn.commit()
    rows = weekly_table.build_weekly_table_rows(
        seeded_conn, week_iso="2026-W20",
    )
    names = [r["project_name"] for r in rows]
    # '통합' 행이 정확히 1개, 두 카테고리의 entries 가 합쳐짐
    assert names.count("통합") == 1
    merged = next(r for r in rows if r["project_name"] == "통합")
    # 두 카테고리 모두의 body 가 this_week 셀에 포함
    assert "차세대OAM" in merged["this_week"] or "OAM" in merged["this_week"]
    assert "SMSC" in merged["this_week"]
