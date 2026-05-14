"""SQLite 스키마, 연결, repository 함수.

운영 경로: ~/.local/share/angeltime/db.sqlite (XDG Base Directory).
테스트에서는 conftest 의 :memory: 픽스처를 사용.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# DB 경로 우선순위:
#   ANGELDASH_TIMESHEET_DB env > ANGELTIME_DB env (legacy) >
#   ~/.local/share/angeldash/timesheet.sqlite (신규 default) >
#   ~/.local/share/angeltime/db.sqlite (legacy default; 기존 사용자 데이터 보존)
_DEFAULT_NEW = Path.home() / ".local" / "share" / "angeldash" / "timesheet.sqlite"
_LEGACY_DEFAULT = Path.home() / ".local" / "share" / "angeltime" / "db.sqlite"


def _resolve_default_db_path() -> Path:
    """env 우선, 없으면 신규 default. 신규 파일이 없고 legacy 가 있으면 legacy 사용."""
    if env := os.environ.get("ANGELDASH_TIMESHEET_DB"):
        return Path(env)
    if env := os.environ.get("ANGELTIME_DB"):
        return Path(env)
    if not _DEFAULT_NEW.exists() and _LEGACY_DEFAULT.exists():
        return _LEGACY_DEFAULT
    return _DEFAULT_NEW


DEFAULT_DB_PATH = _resolve_default_db_path()

SCHEMA = """
CREATE TABLE IF NOT EXISTS days (
    date TEXT PRIMARY KEY,
    week_iso TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL REFERENCES days(date) ON DELETE CASCADE,
    order_index INTEGER NOT NULL,
    category TEXT NOT NULL,
    hours REAL NOT NULL DEFAULT 0,
    body_md TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_entries_date ON entries(date);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    work_type TEXT NOT NULL DEFAULT '',
    remote_id TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    UNIQUE(name, work_type)
);

CREATE TABLE IF NOT EXISTS mappings (
    category TEXT PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    excluded INTEGER NOT NULL DEFAULT 0,
    weekly_project_name TEXT
);

CREATE TABLE IF NOT EXISTS week_notes (
    week_iso TEXT PRIMARY KEY,
    body_md TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS action_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_type TEXT NOT NULL,
    target_range TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_action_logs_created_at ON action_logs(created_at);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS pattern_mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL UNIQUE,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    excluded INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS daily_meta (
    date TEXT PRIMARY KEY,
    source_commit TEXT NOT NULL DEFAULT 'done',
    misc_note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS weekly_reports (
    week_iso TEXT PRIMARY KEY,
    rows_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def connect(path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """DB 파일 경로를 받아 connection 을 반환한다. 디렉토리가 없으면 생성."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_schema(conn)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """스키마를 초기화한다 (멱등) + 필요 시 in-place migration 수행."""
    conn.executescript(SCHEMA)
    _migrate_projects_add_work_type(conn)
    _migrate_mappings_add_weekly_project_name(conn)
    conn.commit()


def _migrate_projects_add_work_type(conn: sqlite3.Connection) -> None:
    """기존 projects 테이블에 work_type 컬럼이 없으면 추가하고 UNIQUE 재구성.

    SQLite 는 ALTER TABLE 로 UNIQUE 제약 변경 불가 → 테이블 rebuild.
    rebuild 시 외래키(mappings.project_id, pattern_mappings.project_id) 도 그대로 유지된다
    — id 가 보존되기 때문.
    """
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(projects)")}
    if "work_type" in cols:
        return
    # foreign_keys 가 ON 인 상태에서 테이블 drop 시 cascade. 잠깐 OFF.
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.executescript("""
    CREATE TABLE projects_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        work_type TEXT NOT NULL DEFAULT '',
        remote_id TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        UNIQUE(name, work_type)
    );
    INSERT INTO projects_new(id, name, work_type, remote_id, active)
        SELECT id, name, '', remote_id, active FROM projects;
    DROP TABLE projects;
    ALTER TABLE projects_new RENAME TO projects;
    """)
    conn.execute("PRAGMA foreign_keys = ON")
    logger.info("Migrated projects table: added work_type column")


def _migrate_mappings_add_weekly_project_name(conn: sqlite3.Connection) -> None:
    """기존 mappings 테이블에 weekly_project_name 컬럼이 없으면 ALTER TABLE 로 추가.

    멱등 (PRAGMA 로 컬럼 존재 여부 확인 후 추가). 신규 사용자는 CREATE TABLE 에
    이미 포함이라 no-op.
    """
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(mappings)")}
    if "weekly_project_name" in cols:
        return
    conn.execute("ALTER TABLE mappings ADD COLUMN weekly_project_name TEXT")
    conn.commit()


# ─── days / entries ────────────────────────────────────


def upsert_entries(
    conn: sqlite3.Connection,
    *,
    date: str,
    week_iso: str,
    entries: list[dict[str, Any]],
) -> None:
    """그 날의 entries 를 완전 교체한다.

    days 행은 없으면 생성. 기존 entries 는 모두 삭제 후 새로 INSERT.
    """
    conn.execute(
        "INSERT OR IGNORE INTO days(date, week_iso) VALUES(?, ?)",
        (date, week_iso),
    )
    conn.execute("DELETE FROM entries WHERE date = ?", (date,))
    for idx, e in enumerate(entries):
        conn.execute(
            "INSERT INTO entries(date, order_index, category, hours, body_md) "
            "VALUES(?, ?, ?, ?, ?)",
            (date, idx, e["category"], e["hours"], e.get("body_md", "")),
        )
    conn.commit()


def get_day(conn: sqlite3.Connection, date: str) -> dict[str, Any]:
    """그 날의 entries 를 order_index 순으로 반환."""
    rows = conn.execute(
        "SELECT id, date, order_index, category, hours, body_md "
        "FROM entries WHERE date = ? ORDER BY order_index",
        (date,),
    ).fetchall()
    return {"date": date, "entries": [dict(r) for r in rows]}


def get_week(conn: sqlite3.Connection, week_iso: str) -> list[dict[str, Any]]:
    """그 주의 entries 가 있는 날짜들을 오름차순으로 반환.

    날짜 자체가 days 테이블에 없으면 결과에 포함되지 않는다.
    """
    dates = [
        r["date"]
        for r in conn.execute(
            "SELECT date FROM days WHERE week_iso = ? ORDER BY date",
            (week_iso,),
        ).fetchall()
    ]
    return [get_day(conn, d) for d in dates]


# ─── week_notes ────────────────────────────────────────


def get_week_note(conn: sqlite3.Connection, week_iso: str) -> str:
    """주별 자유 메모 본문. 없으면 빈 문자열."""
    row = conn.execute(
        "SELECT body_md FROM week_notes WHERE week_iso = ?", (week_iso,)
    ).fetchone()
    return row["body_md"] if row else ""


def upsert_week_note(
    conn: sqlite3.Connection, week_iso: str, body_md: str
) -> None:
    """주별 메모 upsert."""
    conn.execute(
        "INSERT INTO week_notes(week_iso, body_md, updated_at) "
        "VALUES(?, ?, datetime('now')) "
        "ON CONFLICT(week_iso) DO UPDATE SET "
        "  body_md = excluded.body_md, updated_at = datetime('now')",
        (week_iso, body_md),
    )
    conn.commit()


# ─── projects / mappings ───────────────────────────────


def create_project(
    conn: sqlite3.Connection,
    *,
    name: str,
    remote_id: str | None = None,
    work_type: str = "",
) -> int:
    """프로젝트를 생성하고 id 반환. (name, work_type) 중복은 IntegrityError."""
    cur = conn.execute(
        "INSERT INTO projects(name, work_type, remote_id) VALUES(?, ?, ?)",
        (name, work_type, remote_id),
    )
    conn.commit()
    return cur.lastrowid


def list_projects(
    conn: sqlite3.Connection, *, active_only: bool = False
) -> list[dict[str, Any]]:
    """프로젝트 목록을 반환한다. (name, work_type) 알파벳 순."""
    sql = "SELECT id, name, work_type, remote_id, active FROM projects"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY name, work_type"
    return [dict(r) for r in conn.execute(sql).fetchall()]


def count_project_mapping_usage(
    conn: sqlite3.Connection, project_id: int,
) -> dict[str, int]:
    """프로젝트가 카테고리/패턴 매핑에서 몇 번 사용 중인지 반환.

    프로젝트 삭제 전 차단/안내 용. 두 매핑 모두 0이어야 안전 삭제 가능.
    """
    cat = conn.execute(
        "SELECT COUNT(*) AS c FROM mappings WHERE project_id = ?", (project_id,),
    ).fetchone()
    pat = conn.execute(
        "SELECT COUNT(*) AS c FROM pattern_mappings WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    return {"category": cat["c"], "pattern": pat["c"]}


def delete_project(conn: sqlite3.Connection, project_id: int) -> bool:
    """프로젝트 삭제. 매핑에 사용 중이면 호출 전에 막아야 한다 (이 함수는 검증 안 함)."""
    cur = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    return cur.rowcount > 0


def set_mapping(
    conn: sqlite3.Connection,
    category: str,
    *,
    project_id: int | None,
    excluded: bool = False,
    weekly_project_name: str | None = None,
) -> None:
    """카테고리 매핑 upsert.

    project_id=None + excluded=True 면 의도적 미입력.
    weekly_project_name: 주간업무보고 표 프로젝트명. 빈 문자열 정규화.
    """
    # 빈 문자열 → None 정규화 (NULL 과 빈 문자열을 같은 의미로 취급)
    if weekly_project_name is not None:
        normalized = weekly_project_name.strip()
        weekly_project_name = normalized or None
    conn.execute(
        "INSERT INTO mappings(category, project_id, excluded, weekly_project_name) "
        "VALUES(?, ?, ?, ?) "
        "ON CONFLICT(category) DO UPDATE SET "
        "  project_id = excluded.project_id, "
        "  excluded = excluded.excluded, "
        "  weekly_project_name = excluded.weekly_project_name",
        (category, project_id, 1 if excluded else 0, weekly_project_name),
    )
    conn.commit()


def get_mapping(
    conn: sqlite3.Connection, category: str
) -> dict[str, Any] | None:
    """카테고리 매핑 + 프로젝트명을 함께 반환. 없으면 None."""
    row = conn.execute(
        "SELECT m.category, m.project_id, m.excluded, m.weekly_project_name, "
        "       p.name AS project_name, p.work_type AS project_work_type "
        "FROM mappings m LEFT JOIN projects p ON p.id = m.project_id "
        "WHERE m.category = ?",
        (category,),
    ).fetchone()
    return dict(row) if row else None


def list_mappings(
    conn: sqlite3.Connection, *, since_date: str | None = None,
) -> list[dict[str, Any]]:
    """전체 카테고리 매핑 목록을 반환한다.

    포함 기준:
      - mappings 테이블에 명시적으로 등록된 카테고리 (사용자 설정한 매핑은 항상 보임)
      - entries 에 등장하는 카테고리 중 since_date 이후의 것
    since_date=None 이면 entries 전체 (legacy 동작).
    """
    rows = conn.execute(
        "SELECT m.category, m.project_id, m.excluded, m.weekly_project_name, "
        "       p.name AS project_name, p.work_type AS project_work_type "
        "FROM mappings m LEFT JOIN projects p ON p.id = m.project_id"
    ).fetchall()
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for r in rows:
        row = dict(r)
        row["excluded"] = bool(row["excluded"])
        result.append(row)
        seen.add(row["category"])

    if since_date:
        extra = conn.execute(
            "SELECT DISTINCT category FROM entries "
            "WHERE date >= ? AND category NOT IN (SELECT category FROM mappings) "
            "ORDER BY category",
            (since_date,),
        ).fetchall()
    else:
        extra = conn.execute(
            "SELECT DISTINCT category FROM entries "
            "WHERE category NOT IN (SELECT category FROM mappings) "
            "ORDER BY category"
        ).fetchall()
    for r in extra:
        if r["category"] in seen:
            continue
        result.append({
            "category": r["category"],
            "project_id": None,
            "excluded": False,
            "project_name": None,
            "weekly_project_name": None,
        })
    result.sort(key=lambda x: x["category"])
    return result


def delete_mapping(conn: sqlite3.Connection, category: str) -> bool:
    """카테고리 매핑 row 삭제. entries 의 카테고리는 건드리지 않음."""
    cur = conn.execute("DELETE FROM mappings WHERE category = ?", (category,))
    conn.commit()
    return cur.rowcount > 0


# ─── pattern_mappings ──────────────────────────────────


def create_pattern_mapping(
    conn: sqlite3.Connection,
    *,
    pattern: str,
    project_id: int | None = None,
    excluded: bool = False,
) -> int:
    """본문 패턴 매핑 추가. pattern 중복은 IntegrityError."""
    cur = conn.execute(
        "INSERT INTO pattern_mappings(pattern, project_id, excluded) "
        "VALUES(?, ?, ?)",
        (pattern, project_id, 1 if excluded else 0),
    )
    conn.commit()
    return cur.lastrowid


def list_pattern_mappings(
    conn: sqlite3.Connection,
) -> list[dict[str, Any]]:
    """패턴 매핑 목록 — 패턴 길이 DESC 순 (긴 패턴 우선 매칭).

    project_name 도 함께 반환.
    """
    rows = conn.execute(
        "SELECT pm.id, pm.pattern, pm.project_id, pm.excluded, "
        "       p.name AS project_name, p.work_type AS project_work_type "
        "FROM pattern_mappings pm "
        "LEFT JOIN projects p ON p.id = pm.project_id "
        "ORDER BY LENGTH(pm.pattern) DESC, pm.pattern"
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        d["excluded"] = bool(d["excluded"])
        out.append(d)
    return out


def delete_pattern_mapping(conn: sqlite3.Connection, id_: int) -> bool:
    """패턴 매핑 삭제. 삭제되었으면 True."""
    cur = conn.execute(
        "DELETE FROM pattern_mappings WHERE id = ?", (id_,)
    )
    conn.commit()
    return cur.rowcount > 0


def find_pattern_match(
    conn: sqlite3.Connection, haystack: str
) -> dict[str, Any] | None:
    """haystack 에 substring 으로 매칭되는 가장 긴 패턴 매핑을 반환. 없으면 None."""
    for row in list_pattern_mappings(conn):
        if row["pattern"] and row["pattern"] in haystack:
            return row
    return None


# ─── action_logs ───────────────────────────────────────


def log_action(
    conn: sqlite3.Connection,
    action_type: str,
    target_range: str,
    status: str,
    message: str | None = None,
) -> None:
    """액션 로그를 기록한다."""
    conn.execute(
        "INSERT INTO action_logs(action_type, target_range, status, message) "
        "VALUES(?, ?, ?, ?)",
        (action_type, target_range, status, message),
    )
    conn.commit()


def recent_actions(
    conn: sqlite3.Connection, *, limit: int = 50
) -> list[dict[str, Any]]:
    """최근 action_logs 를 시간 역순으로 반환한다."""
    rows = conn.execute(
        "SELECT id, action_type, target_range, status, message, created_at "
        "FROM action_logs ORDER BY created_at DESC, id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def cleanup_action_logs(conn: sqlite3.Connection, *, days: int = 90) -> int:
    """N일보다 오래된 action_logs 삭제. 삭제된 row 수 반환."""
    cur = conn.execute(
        "DELETE FROM action_logs WHERE created_at < datetime('now', ?)",
        (f"-{days} days",),
    )
    conn.commit()
    return cur.rowcount


def cleanup_obsolete_default_settings(
    conn: sqlite3.Connection, obsolete_by_key: dict[str, list[str]],
) -> int:
    """저장된 설정값이 과거 default 와 byte-identical 이면 = 미커스텀이라 판단하고 삭제.

    삭제하면 다음 read 때 코드의 SETTING_DEFAULTS 가 사용된다. 사용자가 직접 편집한
    값은 그 어느 obsolete default 와도 일치하지 않으므로 보존된다.

    obsolete_by_key: {setting_key: [old_default_1, old_default_2, ...]} — 키별로
    여러 과거 버전을 누적해두면 어느 시점의 사용자든 마이그레이션된다.
    """
    deleted = 0
    for key, obsolete_values in obsolete_by_key.items():
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,),
        ).fetchone()
        if row is None:
            continue
        if row["value"] in obsolete_values:
            conn.execute("DELETE FROM settings WHERE key = ?", (key,))
            deleted += 1
            logger.info("Removed obsolete-default setting %r (will fall back to new default)", key)
    if deleted:
        conn.commit()
    return deleted


# ─── settings ──────────────────────────────────────────


def get_setting(conn: sqlite3.Connection, key: str) -> str | None:
    """설정값을 반환한다. 키가 없으면 None."""
    row = conn.execute(
        "SELECT value FROM settings WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row else None


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    """설정값을 upsert한다."""
    conn.execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


# ─── daily_meta ────────────────────────────────────────


SOURCE_COMMIT_LABELS = {
    "done": "완료",
    "later": "추후",
    "local_backup": "로컬백업",
    "none": "없음",
}


def get_daily_meta(conn: sqlite3.Connection, date: str) -> dict[str, Any]:
    """그 날의 meta 를 반환. 없으면 default (source_commit='done', misc_note='')."""
    row = conn.execute(
        "SELECT source_commit, misc_note FROM daily_meta WHERE date = ?",
        (date,),
    ).fetchone()
    if row is None:
        return {"date": date, "source_commit": "done", "misc_note": ""}
    return {
        "date": date,
        "source_commit": row["source_commit"],
        "misc_note": row["misc_note"],
    }


def upsert_daily_meta(
    conn: sqlite3.Connection,
    date: str,
    *,
    source_commit: str,
    misc_note: str,
) -> None:
    """daily_meta upsert."""
    if source_commit not in SOURCE_COMMIT_LABELS:
        raise ValueError(f"invalid source_commit: {source_commit!r}")
    conn.execute(
        "INSERT INTO daily_meta(date, source_commit, misc_note) "
        "VALUES(?, ?, ?) "
        "ON CONFLICT(date) DO UPDATE SET "
        "  source_commit = excluded.source_commit, "
        "  misc_note = excluded.misc_note",
        (date, source_commit, misc_note),
    )
    conn.commit()


# ─── weekly_reports ───────────────────────────────────


def get_weekly_report(
    conn: sqlite3.Connection, week_iso: str
) -> dict[str, Any]:
    """그 주의 보고 rows + updated_at 반환. 없으면 빈 rows."""
    row = conn.execute(
        "SELECT rows_json, updated_at FROM weekly_reports WHERE week_iso = ?",
        (week_iso,),
    ).fetchone()
    if row is None:
        return {"week_iso": week_iso, "rows": [], "updated_at": None}
    return {
        "week_iso": week_iso,
        "rows": json.loads(row["rows_json"]),
        "updated_at": row["updated_at"],
    }


def upsert_weekly_report(
    conn: sqlite3.Connection, week_iso: str, rows: list[dict]
) -> str:
    """rows 를 그 주의 보고로 저장. updated_at 갱신. 반환: 새 updated_at ISO."""
    updated_at = datetime.datetime.now().isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO weekly_reports(week_iso, rows_json, updated_at) "
        "VALUES(?, ?, ?) "
        "ON CONFLICT(week_iso) DO UPDATE SET "
        "  rows_json = excluded.rows_json, "
        "  updated_at = excluded.updated_at",
        (week_iso, json.dumps(rows, ensure_ascii=False), updated_at),
    )
    conn.commit()
    return updated_at
