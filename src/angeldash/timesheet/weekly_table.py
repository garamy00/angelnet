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
from dataclasses import dataclass, field
from typing import Any

from . import db

_FALLBACK_PROJECT = "(매핑 없음)"
# 자동 생성되는 휴가 행의 프로젝트명. UI/재생성 로직이 이 이름으로 행을 식별한다.
VACATION_PROJECT_NAME = "휴가"

# 회사 시스템 휴가 type 코드 → 사용자 표시 라벨
_VAC_TYPE_DISPLAY_LABEL = {
    "연차": "연차",
    "반차(오전)": "오전 반차",
    "반차(오후)": "오후 반차",
    "공가": "공가",
    "공가(오전)": "오전 공가",
    "공가(오후)": "오후 공가",
    "경조사": "경조사",
    "휴직": "휴직",
}
_VAC_AM_HALF_TYPES = {"반차(오전)", "공가(오전)"}
_VAC_PM_HALF_TYPES = {"반차(오후)", "공가(오후)"}
_DAY_KR = ["월", "화", "수", "목", "금", "토", "일"]


def _prev_week_iso(week_iso: str) -> str:
    """'YYYY-Www' 의 직전 주 ISO 문자열."""
    year_s, w_s = week_iso.split("-W")
    year, week = int(year_s), int(w_s)
    # 그 주의 월요일을 구해 7일 빼고 다시 ISO 주로
    monday = datetime.date.fromisocalendar(year, week, 1)
    prev_monday = monday - datetime.timedelta(days=7)
    iso = prev_monday.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _build_project_map(
    conn: sqlite3.Connection,
) -> dict[str, tuple[str | None, str | None]]:
    """category(원본 텍스트) → (weekly_project_name, timesheet_project_name) 맵.

    각 튜플의 첫 요소가 trim 후 비어있지 않으면 _resolve_project 가 그 값을 우선
    사용. 둘 다 None 이면 매핑 누락 처리.
    """
    out: dict[str, tuple[str | None, str | None]] = {}
    cur = conn.execute(
        "SELECT m.category, m.weekly_project_name, p.name "
        "FROM mappings m "
        "LEFT JOIN projects p ON p.id = m.project_id "
        "WHERE m.excluded = 0"
    )
    for row in cur:
        weekly = (row["weekly_project_name"] or "").strip() or None
        out[row["category"]] = (weekly, row["name"])
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
    category: str,
    cat_map: dict[str, tuple[str | None, str | None]],
    pat_list: list[tuple[str, str]],
) -> str:
    """카테고리 텍스트 → 프로젝트명.

    우선순위 (높음 → 낮음):
    1) mappings.weekly_project_name (trim 후 비어있지 않은 경우)
    2) mappings → projects.name (타임시트 프로젝트명)
    3) pattern_mappings substring 매칭
    4) _FALLBACK_PROJECT ('(매핑 없음)')
    """
    if category in cat_map:
        weekly, project = cat_map[category]
        if weekly:
            return weekly
        if project:
            return project
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


# ─── body_md tree-merge 헬퍼 ────────────────────────
# 같은 (week, project, category) 의 여러 body_md 를 들여쓰기 기반 트리로 파싱한 뒤
# 공통 prefix 라인은 1번만, 다른 leaf 만 enumerate 하도록 합친다.


@dataclass
class _Node:
    """들여쓰기 기반 단순 트리 노드."""
    depth: int                                 # leading-space count
    line: str                                  # 원본 라인 (들여쓰기 유지)
    children: list[_Node] = field(default_factory=list)


def _parse_body_to_tree(body_md: str) -> list[_Node]:
    """body_md 의 라인을 들여쓰기 깊이 기반 트리로 파싱.

    빈 라인은 skip. depth 는 앞쪽 space 수.
    """
    roots: list[_Node] = []
    stack: list[_Node] = []
    for raw in body_md.split("\n"):
        if not raw.strip():
            continue
        depth = len(raw) - len(raw.lstrip(" "))
        node = _Node(depth=depth, line=raw.rstrip(), children=[])
        # stack top 의 depth 가 현재 이상이면 pop (sibling/얕은 위치 처리)
        while stack and stack[-1].depth >= depth:
            stack.pop()
        if stack:
            stack[-1].children.append(node)
        else:
            roots.append(node)
        stack.append(node)
    return roots


def _merge_trees(trees: list[list[_Node]]) -> list[_Node]:
    """여러 트리의 같은-level 노드들을 content key(line.strip()) 로 머지.

    같은 key 의 자식 노드들은 재귀적으로 머지. 첫 등장 순서 보존.
    입력 트리들을 mutate 하지 않도록 자식 리스트는 shallow copy 후 머지.
    """
    merged: list[_Node] = []
    by_key: dict[str, _Node] = {}
    for tree in trees:
        for src in tree:
            key = src.line.strip()
            if key in by_key:
                existing = by_key[key]
                existing.children = _merge_trees(
                    [existing.children, src.children]
                )
            else:
                node = _Node(
                    depth=src.depth,
                    line=src.line,
                    children=list(src.children),
                )
                merged.append(node)
                by_key[key] = node
    return merged


def _render_tree(nodes: list[_Node]) -> str:
    """트리를 DFS 로 다시 텍스트로. 원본 line 그대로 출력."""
    out: list[str] = []

    def walk(n: _Node) -> None:
        out.append(n.line)
        for c in n.children:
            walk(c)

    for n in nodes:
        walk(n)
    return "\n".join(out)


def _merge_bodies(bodies: list[str]) -> str:
    """같은 카테고리 안의 body_md 들을 tree-merge 로 결합."""
    if not bodies:
        return ""
    trees = [_parse_body_to_tree(b) for b in bodies]
    merged = _merge_trees(trees)
    return _render_tree(merged)


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
            body_block = _merge_bodies(bodies)
            chunks.append(f"*) {cat}\n{body_block}")
        else:
            chunks.append(f"*) {cat}")
    return "\n\n".join(chunks)


# ─── 휴가 행 자동 생성 헬퍼 ─────────────────────────


def _vac_label(vac_type: str) -> str:
    """type 코드 → 표시 라벨. 모르는 type 은 원본 그대로."""
    return _VAC_TYPE_DISPLAY_LABEL.get(vac_type, vac_type)


def _half_suffix(vac_type: str) -> str:
    """오전/오후 반차이면 ', 오전' / ', 오후', 종일은 ''."""
    if vac_type in _VAC_AM_HALF_TYPES:
        return ", 오전"
    if vac_type in _VAC_PM_HALF_TYPES:
        return ", 오후"
    return ""


def _vac_in_week(vacations: list[dict], week_iso: str) -> list[dict]:
    """그 주(월~금)에 속한 휴가만 필터링하고 (date, type) 으로 정렬."""
    year_s, w_s = week_iso.split("-W")
    year, week = int(year_s), int(w_s)
    monday = datetime.date.fromisocalendar(year, week, 1)
    friday = monday + datetime.timedelta(days=4)
    monday_iso = monday.isoformat()
    friday_iso = friday.isoformat()
    return sorted(
        [v for v in vacations if monday_iso <= (v.get("date") or "") <= friday_iso],
        key=lambda v: (v.get("date") or "", v.get("type") or ""),
    )


def _group_consecutive_dates(
    dates: list[datetime.date],
) -> list[list[datetime.date]]:
    """정렬된 date 리스트를 연속 구간으로 묶는다."""
    if not dates:
        return []
    groups: list[list[datetime.date]] = [[dates[0]]]
    for d in dates[1:]:
        if (d - groups[-1][-1]).days == 1:
            groups[-1].append(d)
        else:
            groups.append([d])
    return groups


def _format_vacation_line(
    vac_type: str,
    dates: list[datetime.date],
    author_name: str,
) -> str:
    """같은 type 의 연속 구간 하나를 한 줄로 포맷.

    예 (반차/연차 모두 동일 규칙):
        종일 단일: '   . 손대곤 부장(04/21, 화)'
        종일 범위: '   . 손대곤 부장(02/02~06, 월~금)'
        반차 단일: '   . 손대곤 부장(04/21, 화, 오후)'
    author_name 이 비면 괄호 앞 빈 prefix.
    """
    start, end = dates[0], dates[-1]
    half = _half_suffix(vac_type)
    if start == end:
        date_part = f"{start.month:02d}/{start.day:02d}"
        day_part = _DAY_KR[start.weekday()]
    else:
        # 같은 달이면 'MM/DD~DD', 다른 달이면 'MM/DD~MM/DD'
        if start.month == end.month:
            date_part = f"{start.month:02d}/{start.day:02d}~{end.day:02d}"
        else:
            date_part = (
                f"{start.month:02d}/{start.day:02d}~"
                f"{end.month:02d}/{end.day:02d}"
            )
        day_part = f"{_DAY_KR[start.weekday()]}~{_DAY_KR[end.weekday()]}"

    inside = f"{date_part}, {day_part}{half}"
    return f"   . {author_name}({inside})" if author_name else f"   . ({inside})"


def _format_vacation_cell(
    vacations_in_week: list[dict],
    *,
    author_name: str,
) -> str:
    """그 주의 휴가를 셀 텍스트로. 비어있으면 빈 문자열.

    형식:
        *) 휴가
         - {유형 라벨}
           . {본인}(MM/DD, 요일[, 오전|오후])
           . ...
         - {다른 유형}
           ...
    """
    if not vacations_in_week:
        return ""

    # type 별 그룹 (등장 순으로 출력 순서 고정)
    by_type: dict[str, list[datetime.date]] = {}
    order: list[str] = []
    for v in vacations_in_week:
        vac_type = v.get("type") or ""
        try:
            d = datetime.date.fromisoformat(v.get("date") or "")
        except ValueError:
            continue
        if vac_type not in by_type:
            by_type[vac_type] = []
            order.append(vac_type)
        by_type[vac_type].append(d)

    lines: list[str] = ["*) 휴가"]
    for vac_type in order:
        groups = _group_consecutive_dates(sorted(by_type[vac_type]))
        lines.append(f" - {_vac_label(vac_type)}")
        for group in groups:
            lines.append(_format_vacation_line(vac_type, group, author_name))
    return "\n".join(lines)


def build_weekly_table_rows(
    conn: sqlite3.Connection,
    *,
    week_iso: str,
    preserve_manual_rows: list[dict] | None = None,
    vacations: list[dict] | None = None,
    author_name: str = "",
) -> list[dict]:
    """주차별 4컬럼 표의 행 리스트 생성.

    last_week / this_week 는 daily entries 에서 자동 채움.
    next_week / note 는 preserve_manual_rows 가 주어지면 같은 project_name 행의
    것을 보존, 아니면 빈 문자열.

    vacations 가 주어지면 그 안에서 지난주/이번주 휴가를 골라 마지막에
    '휴가' 프로젝트 행을 자동 추가. 양쪽 모두 비어있으면 행을 만들지 않는다.
    """
    this_grouped = _entries_grouped_by_project(conn, week_iso=week_iso)
    last_grouped = _entries_grouped_by_project(
        conn, week_iso=_prev_week_iso(week_iso),
    )

    # 자동 발견 프로젝트 순서 (지난주 → 이번주 등장 순)
    auto_order: list[str] = []
    seen: set[str] = set()
    for grouped in (last_grouped, this_grouped):
        for proj in grouped.keys():
            if proj not in seen:
                auto_order.append(proj)
                seen.add(proj)

    # 사용자가 ▲▼ 로 정한 순서를 우선 — preserve_manual_rows 가 있으면 그 순서가 base.
    # 자동 발견된 새 프로젝트는 그 뒤에 append. 휴가 행은 별도 처리하므로 여기서 제외.
    manual_order: list[str] = []
    manual_set: set[str] = set()
    manual_lookup: dict[str, dict[str, str]] = {}
    if preserve_manual_rows:
        for r in preserve_manual_rows:
            name = r.get("project_name", "")
            if not name or name == VACATION_PROJECT_NAME:
                continue
            if name not in manual_set:
                manual_order.append(name)
                manual_set.add(name)
            manual_lookup[name] = {
                "next_week": r.get("next_week", "") or "",
                "note": r.get("note", "") or "",
            }

    project_order: list[str] = list(manual_order)
    for proj in auto_order:
        if proj not in manual_set:
            project_order.append(proj)

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

    # 휴가 행은 자동 생성 — 항상 마지막. 양쪽 셀 모두 비면 행 자체를 추가하지 않는다.
    last_iso = _prev_week_iso(week_iso)
    vacs = vacations or []
    last_cell = _format_vacation_cell(
        _vac_in_week(vacs, last_iso), author_name=author_name,
    )
    this_cell = _format_vacation_cell(
        _vac_in_week(vacs, week_iso), author_name=author_name,
    )
    if last_cell or this_cell:
        out.append({
            "project_name": VACATION_PROJECT_NAME,
            "last_week": last_cell,
            "this_week": this_cell,
            "next_week": "",
            "note": "",
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
