"""DB 스키마와 repository 함수 테스트."""

from __future__ import annotations

import sqlite3

import pytest

from angeldash.timesheet import db


def test_init_schema_creates_all_tables(conn: sqlite3.Connection) -> None:
    """init_schema 는 모든 테이블을 생성한다."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    names = {row["name"] for row in cur.fetchall()}
    expected = {
        "days",
        "entries",
        "projects",
        "mappings",
        "week_notes",
        "action_logs",
        "settings",
    }
    assert expected.issubset(names)


def test_init_schema_is_idempotent(conn: sqlite3.Connection) -> None:
    """init_schema 를 다시 호출해도 에러나 데이터 손실이 없어야 한다."""
    conn.execute("INSERT INTO days(date, week_iso) VALUES('2026-05-12','2026-W19')")
    conn.commit()
    db.init_schema(conn)
    n = conn.execute("SELECT COUNT(*) AS c FROM days").fetchone()["c"]
    assert n == 1


def test_upsert_entries_replaces_day(conn: sqlite3.Connection) -> None:
    """upsert_entries 는 그 날의 entries 를 완전 교체한다."""
    db.upsert_entries(
        conn,
        date="2026-05-12",
        week_iso="2026-W19",
        entries=[
            {"category": "A", "hours": 4.0, "body_md": "x"},
            {"category": "B", "hours": 4.0, "body_md": "y"},
        ],
    )
    rows = conn.execute(
        "SELECT category, order_index FROM entries WHERE date='2026-05-12' ORDER BY order_index"
    ).fetchall()
    assert [r["category"] for r in rows] == ["A", "B"]

    db.upsert_entries(
        conn, date="2026-05-12", week_iso="2026-W19",
        entries=[{"category": "C", "hours": 1.0, "body_md": ""}],
    )
    rows = conn.execute(
        "SELECT category FROM entries WHERE date='2026-05-12'"
    ).fetchall()
    assert [r["category"] for r in rows] == ["C"]


def test_get_week_aggregates_days(conn: sqlite3.Connection) -> None:
    """get_week 는 그 주의 모든 날짜를 반환한다."""
    db.upsert_entries(
        conn, date="2026-05-12", week_iso="2026-W19",
        entries=[{"category": "A", "hours": 4.0, "body_md": ""}],
    )
    db.upsert_entries(
        conn, date="2026-05-13", week_iso="2026-W19",
        entries=[{"category": "B", "hours": 4.0, "body_md": ""}],
    )
    week = db.get_week(conn, "2026-W19")
    assert {d["date"] for d in week} == {"2026-05-12", "2026-05-13"}


def test_week_notes_upsert_and_get(conn: sqlite3.Connection) -> None:
    """주별 자유 메모는 upsert 가능하고 빈 주는 빈 문자열을 반환한다."""
    assert db.get_week_note(conn, "2026-W19") == ""
    db.upsert_week_note(conn, "2026-W19", "메모 본문")
    assert db.get_week_note(conn, "2026-W19") == "메모 본문"
    db.upsert_week_note(conn, "2026-W19", "수정됨")
    assert db.get_week_note(conn, "2026-W19") == "수정됨"


def test_mapping_lookup_with_project(conn: sqlite3.Connection) -> None:
    """매핑 조회는 project 정보를 함께 반환한다."""
    pid = db.create_project(conn, name="25년 SKT SMSC MAP 프로토콜 제거")
    db.set_mapping(conn, "SKT SMSC 리빌딩", project_id=pid, excluded=False)
    m = db.get_mapping(conn, "SKT SMSC 리빌딩")
    assert m["project_id"] == pid
    assert m["project_name"] == "25년 SKT SMSC MAP 프로토콜 제거"


def test_action_log_insert_and_recent(conn: sqlite3.Connection) -> None:
    """action_log 는 시간 역순으로 조회된다."""
    db.log_action(conn, "report", "2026-05-12", "ok", None)
    db.log_action(conn, "timesheet", "2026-05-12", "fail", "401")
    logs = db.recent_actions(conn, limit=10)
    assert len(logs) == 2
    assert logs[0]["action_type"] == "timesheet"  # 최신이 먼저


def test_action_log_cleanup_drops_older_than_days(conn: sqlite3.Connection) -> None:
    """action_log_cleanup 은 N일 이전 항목을 삭제한다."""
    conn.execute(
        "INSERT INTO action_logs (action_type, target_range, status, created_at) "
        "VALUES (?, ?, ?, datetime('now', '-100 days'))",
        ("report", "old", "ok"),
    )
    conn.execute(
        "INSERT INTO action_logs (action_type, target_range, status, created_at) "
        "VALUES (?, ?, ?, datetime('now', '-10 days'))",
        ("report", "recent", "ok"),
    )
    conn.commit()
    deleted = db.cleanup_action_logs(conn, days=90)
    assert deleted == 1
    remaining = conn.execute(
        "SELECT target_range FROM action_logs"
    ).fetchall()
    assert [r["target_range"] for r in remaining] == ["recent"]


def test_settings_get_set(conn: sqlite3.Connection) -> None:
    """settings 는 key/value upsert."""
    assert db.get_setting(conn, "k") is None
    db.set_setting(conn, "k", "v1")
    assert db.get_setting(conn, "k") == "v1"
    db.set_setting(conn, "k", "v2")
    assert db.get_setting(conn, "k") == "v2"


def test_cleanup_obsolete_default_settings_removes_byte_identical_only(
    conn: sqlite3.Connection,
) -> None:
    """과거 DEFAULT 와 byte-identical 한 행만 삭제. 사용자가 편집한 행은 보존."""
    db.set_setting(conn, "team_report.template", "OLD-DEFAULT-V1")
    db.set_setting(conn, "upnote.body_template", "USER-CUSTOMIZED")
    db.set_setting(conn, "unrelated.key", "OLD-DEFAULT-V1")

    deleted = db.cleanup_obsolete_default_settings(
        conn,
        {
            "team_report.template": ["OLD-DEFAULT-V1", "OLDER-DEFAULT-V0"],
            "upnote.body_template": ["OBSOLETE-UPNOTE"],
        },
    )
    assert deleted == 1
    # team_report 는 obsolete 와 일치 → 삭제됨
    assert db.get_setting(conn, "team_report.template") is None
    # upnote.body_template 는 사용자 편집값 → 보존
    assert db.get_setting(conn, "upnote.body_template") == "USER-CUSTOMIZED"
    # 인자 dict 에 없는 키는 손대지 않음
    assert db.get_setting(conn, "unrelated.key") == "OLD-DEFAULT-V1"


def test_list_mappings_includes_entries_categories(conn) -> None:
    """entries 에는 있는데 mappings 에 없는 카테고리도 placeholder 로 포함된다."""
    db.upsert_entries(
        conn, date="2026-05-12", week_iso="2026-W20",
        entries=[
            {"category": "EM 고도화", "hours": 4, "body_md": ""},
            {"category": "소스 Commit", "hours": 0, "body_md": ""},
        ],
    )
    # mappings 테이블은 비어있음
    items = {m["category"]: m for m in db.list_mappings(conn)}
    assert "EM 고도화" in items
    assert items["EM 고도화"]["project_id"] is None
    assert items["EM 고도화"]["excluded"] is False
    assert items["EM 고도화"]["project_name"] is None
    assert "소스 Commit" in items


def test_list_mappings_merges_mapping_row_over_placeholder(conn) -> None:
    """동일 카테고리가 mappings 에 있으면 placeholder 대신 매핑 정보가 우선."""
    db.upsert_entries(
        conn, date="2026-05-12", week_iso="2026-W20",
        entries=[{"category": "X", "hours": 4, "body_md": ""}],
    )
    pid = db.create_project(conn, name="P-X")
    db.set_mapping(conn, "X", project_id=pid, excluded=False)
    items = {m["category"]: m for m in db.list_mappings(conn)}
    assert items["X"]["project_id"] == pid
    assert items["X"]["project_name"] == "P-X"


def test_pattern_mapping_create_and_list(conn) -> None:
    pid = db.create_project(conn, name="P1")
    pmid = db.create_pattern_mapping(
        conn, pattern="VM1.0.5 PKG", project_id=pid
    )
    rows = db.list_pattern_mappings(conn)
    assert len(rows) == 1
    assert rows[0]["pattern"] == "VM1.0.5 PKG"
    assert rows[0]["project_id"] == pid
    assert rows[0]["project_name"] == "P1"
    assert rows[0]["id"] == pmid


def test_pattern_mapping_ordered_by_length_desc(conn) -> None:
    pid = db.create_project(conn, name="P")
    db.create_pattern_mapping(conn, pattern="X", project_id=pid)
    db.create_pattern_mapping(conn, pattern="VM1.0.5 PKG", project_id=pid)
    db.create_pattern_mapping(conn, pattern="KCTHLR", project_id=pid)
    patterns = [r["pattern"] for r in db.list_pattern_mappings(conn)]
    assert patterns == ["VM1.0.5 PKG", "KCTHLR", "X"]


def test_find_pattern_match_picks_longest(conn) -> None:
    pid_short = db.create_project(conn, name="Short")
    pid_long = db.create_project(conn, name="Long")
    db.create_pattern_mapping(conn, pattern="VM1.0.5 PKG", project_id=pid_long)
    db.create_pattern_mapping(conn, pattern="VM", project_id=pid_short)
    m = db.find_pattern_match(conn, "지금 VM1.0.5 PKG 작업 중")
    assert m["project_name"] == "Long"


def test_find_pattern_match_returns_none_when_no_match(conn) -> None:
    pid = db.create_project(conn, name="P")
    db.create_pattern_mapping(conn, pattern="ZZZ", project_id=pid)
    assert db.find_pattern_match(conn, "다른 내용") is None


def test_pattern_mapping_delete(conn) -> None:
    pid = db.create_project(conn, name="P")
    pmid = db.create_pattern_mapping(conn, pattern="P1", project_id=pid)
    assert db.delete_pattern_mapping(conn, pmid) is True
    assert db.list_pattern_mappings(conn) == []
    assert db.delete_pattern_mapping(conn, 99999) is False


def test_pattern_mapping_unique(conn) -> None:
    import sqlite3 as _sqlite3
    pid = db.create_project(conn, name="P")
    db.create_pattern_mapping(conn, pattern="X", project_id=pid)
    with pytest.raises(_sqlite3.IntegrityError):
        db.create_pattern_mapping(conn, pattern="X", project_id=pid)


def test_daily_meta_get_default(conn) -> None:
    """meta 없으면 default 반환."""
    meta = db.get_daily_meta(conn, "2026-05-12")
    assert meta == {"date": "2026-05-12", "source_commit": "done", "misc_note": ""}


def test_daily_meta_upsert(conn) -> None:
    db.upsert_daily_meta(
        conn, "2026-05-12", source_commit="later", misc_note="내일 연차",
    )
    meta = db.get_daily_meta(conn, "2026-05-12")
    assert meta["source_commit"] == "later"
    assert meta["misc_note"] == "내일 연차"


def test_daily_meta_rejects_invalid_source_commit(conn) -> None:
    with pytest.raises(ValueError):
        db.upsert_daily_meta(
            conn, "2026-05-12", source_commit="bogus", misc_note="",
        )
