"""주간업무보고 표 — 자동 채움(daily entries → 프로젝트 그룹) + HTML/마크다운 렌더링.

행 구조: {"project_name": str, "last_week": str, "this_week": str,
          "next_week": str, "note": str}.

자동 채움 흐름:
1. 이번주 + 직전 주의 daily entries 모두 fetch.
2. 각 entry 의 category → mappings → projects.name 으로 그룹.
3. 매핑 없는 카테고리는 "(매핑 없음)" 가상 프로젝트로 묶음.
4. 한 (week, project) 묶음 안에서 카테고리별로 텍스트 셀 빌드.
"""

from __future__ import annotations

import datetime
import sqlite3
from typing import Any

from . import db

_FALLBACK_PROJECT = "(매핑 없음)"


def _prev_week_iso(week_iso: str) -> str:
    """'YYYY-Www' 의 직전 주 ISO 문자열."""
    year_s, w_s = week_iso.split("-W")
    year, week = int(year_s), int(w_s)
    # 그 주의 월요일을 구해 7일 빼고 다시 ISO 주로
    monday = datetime.date.fromisocalendar(year, week, 1)
    prev_monday = monday - datetime.timedelta(days=7)
    iso = prev_monday.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _build_project_map(conn: sqlite3.Connection) -> dict[str, str]:
    """category(원본 텍스트) → project_name 맵.

    mappings 테이블 + pattern_mappings 테이블 양쪽을 사용해, 일반 매핑이 없으면
    pattern substring 매치도 시도.
    """
    # 일반 카테고리 매핑
    out: dict[str, str] = {}
    cur = conn.execute(
        "SELECT m.category, p.name FROM mappings m "
        "JOIN projects p ON p.id = m.project_id "
        "WHERE m.excluded = 0"
    )
    for row in cur:
        out[row["category"]] = row["name"]
    return out


def _build_pattern_map(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """pattern_mappings 의 (pattern, project_name) 리스트, 긴 pattern 우선."""
    rows = conn.execute(
        "SELECT pm.pattern, p.name FROM pattern_mappings pm "
        "JOIN projects p ON p.id = pm.project_id "
        "WHERE pm.excluded = 0"
    ).fetchall()
    return sorted(
        [(r["pattern"], r["name"]) for r in rows],
        key=lambda t: -len(t[0]),
    )


def _resolve_project(
    category: str, cat_map: dict[str, str], pat_list: list[tuple[str, str]]
) -> str:
    """카테고리 텍스트 → 프로젝트명. 매핑 없으면 _FALLBACK_PROJECT."""
    if category in cat_map:
        return cat_map[category]
    for pat, name in pat_list:
        if pat and pat in category:
            return name
    return _FALLBACK_PROJECT


def _entries_grouped_by_project(
    conn: sqlite3.Connection, *, week_iso: str
) -> dict[str, list[dict[str, Any]]]:
    """그 주의 entries 를 프로젝트별로 그룹.

    각 entry: {category, body_md}.
    """
    cat_map = _build_project_map(conn)
    pat_list = _build_pattern_map(conn)
    week = db.get_week(conn, week_iso)
    by_project: dict[str, list[dict[str, Any]]] = {}
    for day in week:
        for entry in day["entries"]:
            cat = entry.get("category", "")
            proj = _resolve_project(cat, cat_map, pat_list)
            by_project.setdefault(proj, []).append({
                "category": cat,
                "body_md": entry.get("body_md", ""),
            })
    return by_project


def _format_cell_text(entries: list[dict[str, Any]]) -> str:
    """카테고리별로 묶어 셀 텍스트 생성.

    형식:
        *) {category}
          {body_md 줄들}

        *) {다른 category}
          ...
    """
    # 카테고리별 그룹 (등장 순)
    by_cat: dict[str, list[str]] = {}
    order: list[str] = []
    for e in entries:
        cat = e["category"]
        if cat not in by_cat:
            by_cat[cat] = []
            order.append(cat)
        body = (e.get("body_md") or "").rstrip()
        if body:
            by_cat[cat].append(body)
    chunks: list[str] = []
    for cat in order:
        bodies = by_cat[cat]
        if bodies:
            body_block = "\n".join(bodies)
            chunks.append(f"*) {cat}\n{body_block}")
        else:
            chunks.append(f"*) {cat}")
    return "\n\n".join(chunks)


def build_weekly_table_rows(
    conn: sqlite3.Connection,
    *,
    week_iso: str,
    preserve_manual_rows: list[dict] | None = None,
) -> list[dict]:
    """주차별 4컬럼 표의 행 리스트 생성.

    last_week / this_week 는 daily entries 에서 자동 채움.
    next_week / note 는 preserve_manual_rows 가 주어지면 같은 project_name 행의
    것을 보존, 아니면 빈 문자열.
    """
    this_grouped = _entries_grouped_by_project(conn, week_iso=week_iso)
    last_grouped = _entries_grouped_by_project(
        conn, week_iso=_prev_week_iso(week_iso),
    )

    # 프로젝트 순서: 지난주 → 이번주 등장 순으로 합집합 (안정적 ordering)
    project_order: list[str] = []
    seen: set[str] = set()
    for grouped in (last_grouped, this_grouped):
        for proj in grouped.keys():
            if proj not in seen:
                project_order.append(proj)
                seen.add(proj)

    # 보존할 manual 값 lookup
    manual_lookup: dict[str, dict[str, str]] = {}
    if preserve_manual_rows:
        for r in preserve_manual_rows:
            name = r.get("project_name", "")
            if name:
                manual_lookup[name] = {
                    "next_week": r.get("next_week", "") or "",
                    "note": r.get("note", "") or "",
                }

    out: list[dict] = []
    for proj in project_order:
        manual = manual_lookup.get(proj, {"next_week": "", "note": ""})
        out.append({
            "project_name": proj,
            "last_week": _format_cell_text(last_grouped.get(proj, [])),
            "this_week": _format_cell_text(this_grouped.get(proj, [])),
            "next_week": manual["next_week"],
            "note": manual["note"],
        })
    return out


# ─── 표 렌더링 ─────────────────────────────────────────


_COL_HEADERS = (
    "프로젝트", "지난주 한 일", "이번주 한 일/할 일", "다음주 할 일", "비고"
)


def render_html_table(rows: list[dict]) -> str:
    """Outlook 친화 HTML 표 (인라인 스타일).

    셀 내부의 줄바꿈/들여쓰기는 white-space:pre-wrap + monospace 폰트로 보존.
    """
    def _esc(s: str) -> str:
        return (
            (s or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    th_style = "border:1px solid #888; padding:6px;"
    td_proj_style = "border:1px solid #888; padding:6px; vertical-align:top;"
    td_body_style = (
        "border:1px solid #888; padding:6px; vertical-align:top; "
        "white-space:pre-wrap; font-family: 'SF Mono', Menlo, Consolas, monospace; "
        "font-size:12px;"
    )

    lines: list[str] = []
    lines.append(
        '<table cellpadding="6" cellspacing="0" '
        'style="border-collapse:collapse; '
        "font-family: '맑은 고딕', sans-serif; font-size:13px;\">"
    )
    lines.append('<thead><tr style="background:#e8e8e8;">')
    for h in _COL_HEADERS:
        lines.append(f'<th style="{th_style}">{_esc(h)}</th>')
    lines.append("</tr></thead>")
    lines.append("<tbody>")
    for r in rows:
        lines.append("<tr>")
        lines.append(
            f'<td style="{td_proj_style}"><b>{_esc(r.get("project_name", ""))}</b></td>'
        )
        for key in ("last_week", "this_week", "next_week", "note"):
            lines.append(f'<td style="{td_body_style}">{_esc(r.get(key, ""))}</td>')
        lines.append("</tr>")
    lines.append("</tbody></table>")
    return "".join(lines)


def render_markdown_table(rows: list[dict]) -> str:
    """마크다운 표 (UpNote 본문 + plain 폴백).

    셀 내부 줄바꿈은 `<br>` 로 치환하여 단일 셀 안에 멀티라인 유지.
    pipe 문자는 escape.
    """
    def _cell(s: str) -> str:
        return (s or "").replace("|", "\\|").replace("\n", "<br>")

    out: list[str] = []
    out.append("| " + " | ".join(_COL_HEADERS) + " |")
    out.append("| " + " | ".join(["---"] * len(_COL_HEADERS)) + " |")
    for r in rows:
        cells = [
            r.get("project_name", ""),
            r.get("last_week", ""),
            r.get("this_week", ""),
            r.get("next_week", ""),
            r.get("note", ""),
        ]
        out.append("| " + " | ".join(_cell(c) for c in cells) + " |")
    return "\n".join(out)
