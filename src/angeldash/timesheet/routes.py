"""timesheet 라우트 등록 모듈.

angeldash/server.py 의 build_app 이 register_routes(app) 을 호출해
FastAPI 인스턴스에 타임시트/보고서 관련 라우트를 추가한다.
정적 자산과 lifespan(client login, db open) 은 angeldash/server.py 가 일괄 담당.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI
from pydantic import BaseModel, Field

from . import db as db_module
from . import formatter as fmt_module
from .client import TimesheetClient
from .misc_auto import generate_misc_auto
from .models import DailyMetaInput, EntryInput, ProjectInput, User, WeekNoteInput
from .templates import DEFAULT_TEAM_REPORT, DEFAULT_UPNOTE_BODY, DEFAULT_UPNOTE_TITLE


class DayInput(BaseModel):
    """PUT /api/days/{date} 페이로드."""

    week_iso: str
    entries: list[EntryInput]


class MappingInput(BaseModel):
    """PUT /api/mappings/{category} 페이로드."""

    project_id: int | None = None
    excluded: bool = False
    weekly_project_name: str | None = None


class SettingsPreviewInput(BaseModel):
    """POST /api/settings/preview 페이로드."""

    kind: str  # 'team_report' | 'upnote_title' | 'upnote_body'
    template: str
    date: str | None = None
    week_iso: str | None = None


class EmailPasswordInput(BaseModel):
    """PUT /api/settings/email-password 페이로드.

    빈 문자열이면 Keychain 항목 삭제 의도로 해석.
    """

    password: str


class EmailSendWeeklyInput(BaseModel):
    """POST /api/actions/email-send-weekly 페이로드.

    override_to / override_cc 가 주어지면 설정값 대신 사용 (받는사람 확인 시 수정 가능).
    """

    week_iso: str
    override_to: str | None = None
    override_cc: str | None = None


class TeamReportActionInput(BaseModel):
    """POST /api/actions/team-report 페이로드."""

    date: str | None = None
    week_iso: str | None = None


class UpNoteSyncInput(BaseModel):
    """POST /api/actions/upnote-sync 페이로드."""

    week_iso: str
    dry_run: bool = False


class TimesheetSubmitInput(BaseModel):
    """POST /api/actions/timesheet-submit 페이로드."""

    date: str | None = None
    week_iso: str | None = None
    dry_run: bool = False


class TimesheetPushOneInput(BaseModel):
    """POST /api/actions/timesheet-push-one 페이로드."""

    date: str  # 'YYYY-MM-DD'
    task_name: str
    hours: float  # 0 이면 그 셀 삭제와 동일


class WeeklyReportInput(BaseModel):
    """PUT /api/weekly-reports/{week_iso} 페이로드."""

    rows: list[dict]


class WeeklyReportGenerateInput(BaseModel):
    """POST /api/weekly-reports/{week_iso}/generate 페이로드."""

    preserve_manual: bool = True


class WeeklyReportUpnoteInput(BaseModel):
    """POST /api/actions/weekly-report-upnote 페이로드."""

    week_iso: str


class PatternMappingInput(BaseModel):
    """POST /api/pattern-mappings 페이로드."""

    pattern: str = Field(min_length=1)
    project_id: int | None = None
    excluded: bool = False


class ProjectJoinInput(BaseModel):
    """POST /api/timesheet/projects/join 페이로드."""

    project_id: str
    joined: bool

logger = logging.getLogger(__name__)


# ─── 의존성 placeholder ────────────────────────────────


def get_conn() -> sqlite3.Connection:
    raise RuntimeError("db connection not initialized")


def get_client() -> TimesheetClient:
    raise RuntimeError("client not initialized")


def get_password() -> str:
    raise RuntimeError("password not initialized")


# ─── 라우트 등록 함수 ──────────────────────────────────


def register_routes(app: FastAPI) -> None:
    """타임시트/보고서 모든 API 라우트를 app 에 등록한다.

    의존성(conn/client/password) 은 app.dependency_overrides 로 주입돼야 한다.
    static 자산과 페이지 라우트(`/projects.html` 등) 는 호출 측이 별도로 등록.
    """

    # ─── /api/me ────────────────────────────────────
    # angeldash 회의실 모듈에 이미 /api/me 가 있으면 충돌. 회의실 모듈의 것을 우선
    # 사용하므로 여기 등록은 생략 (회의실 me 도 동일 User 구조).

    # ─── Reports API ────────────────────────────────

    @app.get("/api/weeks/{week_iso}")
    async def get_week_route(
        week_iso: str, conn=Depends(get_conn)
    ) -> dict:
        days = db_module.get_week(conn, week_iso)
        return {"week_iso": week_iso, "days": days}

    @app.get("/api/days/{date}")
    async def get_day_route(date: str, conn=Depends(get_conn)) -> dict:
        return db_module.get_day(conn, date)

    @app.put("/api/days/{date}")
    async def put_day_route(
        date: str, payload: DayInput, conn=Depends(get_conn)
    ) -> dict:
        db_module.upsert_entries(
            conn,
            date=date,
            week_iso=payload.week_iso,
            entries=[e.model_dump() for e in payload.entries],
        )
        return {"ok": True}

    @app.get("/api/days/{date}/meta")
    async def get_daily_meta_route(
        date: str, conn=Depends(get_conn)
    ) -> dict:
        return db_module.get_daily_meta(conn, date)

    @app.put("/api/days/{date}/meta")
    async def put_daily_meta_route(
        date: str, payload: DailyMetaInput, conn=Depends(get_conn)
    ) -> dict:
        from fastapi import HTTPException
        try:
            db_module.upsert_daily_meta(
                conn, date,
                source_commit=payload.source_commit,
                misc_note=payload.misc_note,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"ok": True}

    @app.get("/api/days/{date}/misc-auto")
    async def misc_auto_route(
        date: str,
        conn=Depends(get_conn),
        client: TimesheetClient = Depends(get_client),
    ) -> dict:
        """그 날 기준 자동 '기타' 문구 생성."""
        import datetime as _dt
        from fastapi import HTTPException

        try:
            base = _dt.date.fromisoformat(date)
        except ValueError as exc:
            raise HTTPException(400, f"invalid date: {date}") from exc

        # 이번 달 + 다음 달 휴가/공휴일 (연속 휴가가 달 넘을 수 있음)
        cur_ym = date[:7]
        next_month = base.replace(day=1) + _dt.timedelta(days=32)
        next_ym = next_month.strftime("%Y-%m")

        try:
            cur_vacs = await client.list_vacations(year_month=cur_ym)
            next_vacs = await client.list_vacations(year_month=next_ym)
            cur_hols = await client.list_holidays(year_month=cur_ym)
            next_hols = await client.list_holidays(year_month=next_ym)
        except Exception as exc:
            raise HTTPException(500, f"vacation/holiday fetch failed: {exc}") from exc

        # exclude_labels 읽기 (settings)
        raw = db_module.get_setting(conn, "misc.holiday_exclude_labels") or ""
        labels = {
            s.strip() for s in raw.replace("\n", ",").split(",") if s.strip()
        }

        text = generate_misc_auto(
            date,
            vacations=cur_vacs + next_vacs,
            holidays=cur_hols + next_hols,
            exclude_labels=labels,
        )
        return {"date": date, "text": text}

    @app.get("/api/weeks/{week_iso}/note")
    async def get_week_note_route(
        week_iso: str, conn=Depends(get_conn)
    ) -> dict:
        return {
            "week_iso": week_iso,
            "body_md": db_module.get_week_note(conn, week_iso),
        }

    @app.put("/api/weeks/{week_iso}/note")
    async def put_week_note_route(
        week_iso: str, payload: WeekNoteInput, conn=Depends(get_conn)
    ) -> dict:
        db_module.upsert_week_note(conn, week_iso, payload.body_md)
        return {"ok": True}

    # ─── Projects + Mappings API ────────────────────

    @app.get("/api/projects")
    async def list_projects_route(conn=Depends(get_conn)) -> list[dict]:
        return db_module.list_projects(conn)

    @app.post("/api/projects")
    async def create_project_route(
        payload: ProjectInput, conn=Depends(get_conn)
    ) -> dict:
        from fastapi import HTTPException
        try:
            pid = db_module.create_project(
                conn,
                name=payload.name,
                work_type=payload.work_type,
                remote_id=payload.remote_id,
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(
                status_code=409,
                detail="duplicate (name, work_type)",
            ) from exc
        return {"id": pid, "name": payload.name, "work_type": payload.work_type}

    @app.delete("/api/projects/{pid}")
    async def delete_project_route(
        pid: int, conn=Depends(get_conn)
    ) -> dict:
        """프로젝트 삭제. 카테고리/패턴 매핑이 참조 중이면 409 로 차단."""
        from fastapi import HTTPException
        usage = db_module.count_project_mapping_usage(conn, pid)
        if usage["category"] or usage["pattern"]:
            raise HTTPException(
                status_code=409,
                detail={
                    "reason": "in_use",
                    "category_mappings": usage["category"],
                    "pattern_mappings": usage["pattern"],
                },
            )
        if not db_module.delete_project(conn, pid):
            raise HTTPException(404, "not found")
        return {"ok": True}

    @app.get("/api/mappings")
    async def list_mappings_route(conn=Depends(get_conn)) -> list[dict]:
        # 지난달 1일 이후의 entries 카테고리만 노출 (오래된 placeholder 제외)
        today = date.today()
        first_this_month = today.replace(day=1)
        last_month_last_day = first_this_month - timedelta(days=1)
        since = last_month_last_day.replace(day=1).isoformat()
        return db_module.list_mappings(conn, since_date=since)

    @app.put("/api/mappings/{category}")
    async def put_mapping_route(
        category: str, payload: MappingInput, conn=Depends(get_conn)
    ) -> dict:
        db_module.set_mapping(
            conn,
            category,
            project_id=payload.project_id,
            excluded=payload.excluded,
            weekly_project_name=payload.weekly_project_name,
        )
        return {"ok": True}

    @app.delete("/api/mappings/{category}")
    async def delete_mapping_route(
        category: str, conn=Depends(get_conn)
    ) -> dict:
        """카테고리 매핑 삭제. entries 카테고리는 그대로 유지."""
        from fastapi import HTTPException
        if not db_module.delete_mapping(conn, category):
            raise HTTPException(404, "not found")
        return {"ok": True}

    # ─── Pattern mappings ───────────────────────────

    @app.get("/api/pattern-mappings")
    async def list_pattern_mappings_route(
        conn=Depends(get_conn),
    ) -> list[dict]:
        return db_module.list_pattern_mappings(conn)

    @app.post("/api/pattern-mappings")
    async def create_pattern_mapping_route(
        payload: PatternMappingInput, conn=Depends(get_conn)
    ) -> dict:
        import sqlite3 as _sqlite3
        from fastapi import HTTPException
        try:
            pmid = db_module.create_pattern_mapping(
                conn,
                pattern=payload.pattern.strip(),
                project_id=payload.project_id,
                excluded=payload.excluded,
            )
        except _sqlite3.IntegrityError as exc:
            raise HTTPException(409, "duplicate pattern") from exc
        return {"id": pmid, "pattern": payload.pattern.strip()}

    @app.delete("/api/pattern-mappings/{pmid}")
    async def delete_pattern_mapping_route(
        pmid: int, conn=Depends(get_conn)
    ) -> dict:
        from fastapi import HTTPException
        ok = db_module.delete_pattern_mapping(conn, pmid)
        if not ok:
            raise HTTPException(404, "not found")
        return {"ok": True}

    # ─── 휴가계 조회 (read-only) ──────────────────────
    @app.get("/api/vacation/annual")
    async def vacation_annual_route(
        year: int | None = None,
        client: TimesheetClient = Depends(get_client),
    ) -> dict:
        """연간 휴가 사용/잔여 일수 요약."""
        import datetime as _dt
        from fastapi import HTTPException

        y = year or _dt.date.today().year
        try:
            return await client.get_annual_vacation_summary(year=y)
        except Exception as exc:
            raise HTTPException(500, str(exc)) from exc

    @app.get("/api/vacation/applications")
    async def vacation_applications_route(
        year: int | None = None,
        client: TimesheetClient = Depends(get_client),
    ) -> list[dict]:
        """연간 휴가계 목록 (조회 전용)."""
        import datetime as _dt
        from fastapi import HTTPException

        y = year or _dt.date.today().year
        try:
            return await client.list_vacation_applications(year=y)
        except Exception as exc:
            raise HTTPException(500, str(exc)) from exc

    # ─── Timesheet remote tasks (read-only helper) ──────────

    @app.get("/api/timesheet/tasks")
    async def list_remote_tasks_route(
        year_month: str | None = None,
        conn=Depends(get_conn),
        client: TimesheetClient = Depends(get_client),
    ) -> list[dict]:
        """현재 타임시트에서 그 달의 task 목록을 가져온다.

        각 task 에 `already_registered` 플래그를 붙여 이미 우리 DB 의 projects 에
        등록된 task 인지 표시한다.

        year_month: 'YYYY-MM' (없으면 오늘 기준 현재 달).
        """
        import datetime as _dt
        from fastapi import HTTPException

        ym = year_month or _dt.date.today().strftime("%Y-%m")
        try:
            tasks = await client.list_jobtime_tasks(year_month=ym)
        except Exception as exc:
            raise HTTPException(500, str(exc)) from exc

        # 매칭: (remote_id, work_type) 튜플 우선. 같은 task name 이라도 work_type 이
        # 다르면 별개 항목.
        all_projects = db_module.list_projects(conn)
        existing_strict = {
            ((p["remote_id"] or "").strip(), (p["work_type"] or "").strip()): p
            for p in all_projects
            if p["remote_id"]
        }
        # 레거시 fallback: work_type 이 비어 있는 행은 같은 이름의 첫 remote task 에
        # 1회 매칭되며 그때 work_type 을 backfill 한다 (마이그레이션 보조).
        legacy_empty = {
            (p["remote_id"] or "").strip(): p
            for p in all_projects
            if p["remote_id"] and not (p["work_type"] or "").strip()
        }
        for t in tasks:
            name = t["name"]
            wt = (t.get("work_type") or "").strip()
            matched = existing_strict.get((name, wt))
            if matched is None and name in legacy_empty:
                # legacy: 처음 만난 remote work_type 으로 채움
                legacy_row = legacy_empty.pop(name)
                conn.execute(
                    "UPDATE projects SET work_type = ? WHERE id = ? AND work_type = ''",
                    (wt, legacy_row["id"]),
                )
                conn.commit()
                matched = legacy_row
                logger.info(
                    "Backfilled work_type=%r for legacy project id=%s name=%r",
                    wt, legacy_row["id"], name,
                )
            t["already_registered"] = matched is not None
            t["project_id"] = matched["id"] if matched else None
        return tasks

    # ─── Timesheet 프로젝트 가입/탈퇴 ─────────────

    @app.get("/api/timesheet/projects/search")
    async def search_joinable_route(
        keyword: str = "",
        page: int = 1,
        page_size: int = 50,
        client: TimesheetClient = Depends(get_client),
    ) -> dict:
        from fastapi import HTTPException
        try:
            return await client.search_joinable_projects(
                keyword=keyword, page=page, page_size=page_size,
            )
        except Exception as exc:
            raise HTTPException(500, str(exc)) from exc

    @app.post("/api/timesheet/projects/join")
    async def join_project_route(
        payload: ProjectJoinInput,
        conn=Depends(get_conn),
        client: TimesheetClient = Depends(get_client),
    ) -> dict:
        from fastapi import HTTPException
        try:
            if payload.joined:
                # 프로젝트 가입
                await client.join_project(project_id=payload.project_id)
                # 자동 task 가입 (회사 페이지 안내: task 가입 → 프로젝트 자동 가입.
                # 우리는 명시적으로 프로젝트 먼저 join 후 task 도 join.)
                auto_name = (
                    db_module.get_setting(conn, "join.auto_task_name")
                    or SETTING_DEFAULTS["join.auto_task_name"]
                ).strip()
                joined_task = None
                if auto_name:
                    tasks = await client.list_project_tasks(
                        project_id=payload.project_id,
                    )
                    match = next((t for t in tasks if t["name"] == auto_name), None)
                    if match:
                        if not match["joined"]:
                            await client.set_project_task_joined(
                                project_id=payload.project_id,
                                task_id=match["task_id"],
                            )
                        joined_task = auto_name
                    else:
                        logger.warning(
                            "auto_task_name=%r not found in project=%s tasks",
                            auto_name, payload.project_id,
                        )
                msg = f"project join + task={joined_task or 'none'}"
                db_module.log_action(
                    conn, "timesheet", payload.project_id, "ok", msg,
                )
                return {"ok": True, "joined_task": joined_task}
            else:
                # 탈퇴: tasksMapDelAll cascade 로 task+프로젝트 동시 unjoin
                await client.unjoin_project(project_id=payload.project_id)
                db_module.log_action(
                    conn, "timesheet", payload.project_id, "ok",
                    "project unjoin via tasksMapDelAll cascade",
                )
                return {"ok": True}
        except Exception as exc:
            db_module.log_action(
                conn, "timesheet", payload.project_id, "fail",
                f"project-join({payload.joined}): {exc}",
            )
            raise HTTPException(500, str(exc)) from exc

    # ─── Timesheet verify (read-only) ─────────────

    @app.get("/api/timesheet/verify")
    async def verify_timesheet_route(
        week_iso: str,
        conn=Depends(get_conn),
        client: TimesheetClient = Depends(get_client),
    ) -> dict:
        """그 주의 entries 가 회사 타임시트와 일치하는지 검증."""
        from fastapi import HTTPException

        week = db_module.get_week(conn, week_iso)
        rows = []
        for d in week:
            for e in d["entries"]:
                rows.append({**e, "date": d["date"]})

        # 매핑 분류 (timesheet-submit 과 동일한 로직: pattern 우선 → category fallback)
        items: list[dict] = []
        to_check: list[dict] = []
        needed_months: set[str] = set()
        for e in rows:
            # 1) 본문 패턴 매핑 먼저 검사 (긴 패턴 우선)
            haystack = (e["category"] or "") + "\n" + (e.get("body_md") or "")
            pm = db_module.find_pattern_match(conn, haystack)
            matched_via_pattern = False
            if pm is not None:
                if pm["excluded"]:
                    items.append({**e, "sync_status": "excluded",
                                  "matched_pattern": pm["pattern"]})
                    continue
                if pm["project_id"] is not None:
                    project = conn.execute(
                        "SELECT name, remote_id FROM projects WHERE id = ?",
                        (pm["project_id"],),
                    ).fetchone()
                    task_name = (
                        (project["remote_id"] or "").strip() if project else ""
                    )
                    if not task_name:
                        items.append({**e, "sync_status": "no_remote_id",
                                      "matched_pattern": pm["pattern"]})
                        continue
                    to_check.append({
                        **e, "task_name": task_name,
                        "matched_pattern": pm["pattern"],
                    })
                    needed_months.add(e["date"][:7])
                    matched_via_pattern = True
            if matched_via_pattern:
                continue

            # 2) 카테고리 매핑 fallback
            m = db_module.get_mapping(conn, e["category"])
            if m is None or (m["project_id"] is None and not m["excluded"]):
                items.append({**e, "sync_status": "no_mapping"})
                continue
            if m["excluded"]:
                items.append({**e, "sync_status": "excluded"})
                continue
            project = conn.execute(
                "SELECT name, remote_id FROM projects WHERE id = ?",
                (m["project_id"],),
            ).fetchone()
            task_name = (
                (project["remote_id"] or "").strip() if project else ""
            )
            if not task_name:
                items.append({**e, "sync_status": "no_remote_id"})
                continue
            to_check.append({**e, "task_name": task_name})
            needed_months.add(e["date"][:7])

        # 월별 search.json grid 호출
        grids: dict[str, dict[str, dict[int, float]]] = {}
        for ym in sorted(needed_months):
            try:
                grids[ym] = await client.fetch_jobtime_grid(year_month=ym)
            except Exception as exc:
                raise HTTPException(500, f"verify({ym}): {exc}") from exc

        # 한 날에 여러 entries 가 같은 task 로 매핑될 수 있으므로
        # (date, task_name) 단위로 도구 hours 를 합산하여 회사 시스템과 비교한다.
        local_totals: dict[tuple[str, str], float] = {}
        for e in to_check:
            key = (e["date"], e["task_name"])
            local_totals[key] = local_totals.get(key, 0.0) + e["hours"]

        for e in to_check:
            ym = e["date"][:7]
            day = int(e["date"].split("-")[2])
            grid = grids.get(ym, {})
            remote = grid.get(e["task_name"], {}).get(day, 0.0)
            local_total = local_totals[(e["date"], e["task_name"])]
            entry = {
                **e,
                "remote_hours": remote,
                "local_task_total": local_total,
            }
            if abs(remote - local_total) < 0.001:
                entry["sync_status"] = "synced"
            elif remote == 0 and local_total > 0:
                entry["sync_status"] = "not_submitted"
            elif remote > 0 and local_total == 0:
                entry["sync_status"] = "remote_only"
            else:
                entry["sync_status"] = "mismatch"
            items.append(entry)

        # ─── orphan 검출: 회사 grid 에 있는데 도구 entries 에 없는 (date, task) ───
        import datetime as _dt
        year_str, w_str = week_iso.split("-W")
        try:
            monday = _dt.date.fromisocalendar(int(year_str), int(w_str), 1)
            week_dates_set = {
                (monday + _dt.timedelta(days=i)).isoformat() for i in range(7)
            }
        except ValueError:
            week_dates_set = set()

        local_keys = {(e["date"], e["task_name"]) for e in to_check}
        for ym, grid in grids.items():
            try:
                y_int = int(ym.split("-")[0])
                m_int = int(ym.split("-")[1])
            except (ValueError, IndexError):
                continue
            for task_name, day_hours in grid.items():
                for day, h in day_hours.items():
                    if h <= 0:
                        continue
                    try:
                        date_iso = _dt.date(y_int, m_int, day).isoformat()
                    except ValueError:
                        continue
                    if date_iso not in week_dates_set:
                        continue
                    if (date_iso, task_name) in local_keys:
                        continue
                    items.append({
                        "date": date_iso,
                        "category": task_name,
                        "task_name": task_name,
                        "hours": 0.0,
                        "body_md": "",
                        "remote_hours": h,
                        "local_task_total": 0.0,
                        "sync_status": "orphan",
                    })

        return {"items": items, "week_iso": week_iso}

    # ─── Timesheet Excel 다운로드 (read-only proxy) ────
    from fastapi.responses import Response as _FastAPIResponse
    from urllib.parse import quote as _quote

    @app.get("/api/timesheet/excel")
    async def download_excel_route(
        year_month: str,
        client: TimesheetClient = Depends(get_client),
    ) -> _FastAPIResponse:
        """그 달의 jobtime Excel 다운로드 (회사 시스템에서 받아 그대로 전달)."""
        from fastapi import HTTPException

        try:
            body, filename = await client.download_jobtime_excel(year_month=year_month)
        except Exception as exc:
            raise HTTPException(500, str(exc)) from exc

        # Content-Disposition 헤더에 한글 filename — RFC 5987 형식
        ascii_fallback = f"jobtime_{year_month}.xlsx"
        cd = (
            f'attachment; filename="{ascii_fallback}"; '
            f"filename*=UTF-8''{_quote(filename)}"
        )
        return _FastAPIResponse(
            content=body,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": cd},
        )

    @app.get("/api/timesheet/monthly-grid")
    async def monthly_grid_route(
        year_month: str,
        conn=Depends(get_conn),
        client: TimesheetClient = Depends(get_client),
    ) -> dict:
        """그 달의 task×day 매트릭스 + 휴가 + 공휴일 (회사 시스템 fetch).

        - tasks: 합계가 0 인 항목은 제외 (회사 시스템에 등록만 되고 입력 없는 task)
        - vacations: 연차/반차 등을 type 별로 그룹화한 별도 row 들
            연차/공가/경조사/휴직 → 8h, 반차(오전/오후)·공가(오전/오후) → 4h
        - holidays: '출근일로 취급' label 을 제외한 진짜 공휴일 일자 set
        """
        import datetime as _dt
        from calendar import monthrange

        from fastapi import HTTPException

        try:
            year_s, month_s = year_month.split("-")
            year, month = int(year_s), int(month_s)
        except ValueError as exc:
            raise HTTPException(
                400, f"invalid year_month: {year_month}",
            ) from exc
        days_in_month = monthrange(year, month)[1]

        # 회사 시스템 fetch — grid 가 핵심, 나머지는 실패해도 본 응답 유지
        try:
            grid = await client.fetch_jobtime_grid(year_month=year_month)
        except Exception as exc:
            raise HTTPException(500, f"monthly grid fetch failed: {exc}") from exc

        vacations_raw: list[dict] = []
        holidays_raw: list[dict] = []
        try:
            vacations_raw = await client.list_vacations(year_month=year_month)
        except Exception as exc:
            logger.warning("monthly_grid: vacation fetch failed: %s", exc)
        try:
            holidays_raw = await client.list_holidays(year_month=year_month)
        except Exception as exc:
            logger.warning("monthly_grid: holiday fetch failed: %s", exc)

        # 출근일로 취급할 공휴일 label 집합 (설정값)
        exclude_raw = db_module.get_setting(
            conn, "misc.holiday_exclude_labels"
        ) or ""
        exclude_labels = {
            s.strip() for s in exclude_raw.replace("\n", ",").split(",")
            if s.strip()
        }

        # 진짜 공휴일 일자 list (출근일 제외)
        holidays_out: list[dict] = []
        for h in holidays_raw:
            label = (h.get("label") or "").strip()
            if label in exclude_labels:
                continue
            date_iso = h.get("date") or ""
            try:
                d = _dt.date.fromisoformat(date_iso)
            except ValueError:
                continue
            if d.year != year or d.month != month:
                continue
            holidays_out.append({"day": d.day, "label": label})

        # tasks 집계 — 합계 0 제외
        tasks: list[dict] = []
        daily_totals: dict[int, float] = {}
        month_total = 0.0
        for task_name in sorted(grid.keys()):
            days = grid[task_name]
            task_total = round(sum(days.values()), 2)
            if task_total <= 0:
                continue  # 모두 0 인 task hide
            month_total += task_total
            for day, hours in days.items():
                daily_totals[day] = round(
                    daily_totals.get(day, 0.0) + hours, 2,
                )
            tasks.append({
                "task_name": task_name,
                "days": days,
                "total": task_total,
            })

        # 휴가 — type 별 그룹화 후 반차는 4h, 그 외는 8h 적용
        # type 라벨은 misc_auto._VAC_TYPE_LABEL 와 동일하게 한국어 표시명으로 변환
        from . import misc_auto as ma_module
        half_types = (
            ma_module._AM_HALF_TYPES | ma_module._PM_HALF_TYPES
        )
        by_label: dict[str, dict[int, float]] = {}
        label_order: list[str] = []
        for v in vacations_raw:
            vac_type = v.get("type") or ""
            date_iso = v.get("date") or ""
            try:
                d = _dt.date.fromisoformat(date_iso)
            except ValueError:
                continue
            if d.year != year or d.month != month:
                continue
            label = ma_module._label_for_type(vac_type)
            hours = 4.0 if vac_type in half_types else 8.0
            if label not in by_label:
                by_label[label] = {}
                label_order.append(label)
            by_label[label][d.day] = hours

        vacations_out: list[dict] = []
        for label in label_order:
            days = by_label[label]
            total = round(sum(days.values()), 2)
            vacations_out.append({
                "label": label, "days": days, "total": total,
            })
            # 일별 합계에도 휴가 시간을 포함 (사용자가 8h/4h 매일 합 확인 가능)
            for day, hours in days.items():
                daily_totals[day] = round(
                    daily_totals.get(day, 0.0) + hours, 2,
                )
            month_total += total

        return {
            "year_month": year_month,
            "tasks": tasks,
            "vacations": vacations_out,
            "holidays": holidays_out,
            "daily_totals": daily_totals,
            "month_total": round(month_total, 2),
            "days_in_month": days_in_month,
        }

    # ─── Vacations / Holidays (read-only) ──────────

    @app.get("/api/vacations")
    async def list_vacations_route(
        year_month: str | None = None,
        conn=Depends(get_conn),
        client: TimesheetClient = Depends(get_client),
    ) -> list[dict]:
        """그 달의 휴가 정보를 회사 시스템에서 가져온다 (read-only)."""
        import datetime as _dt
        from fastapi import HTTPException

        ym = year_month or _dt.date.today().strftime("%Y-%m")
        try:
            return await client.list_vacations(year_month=ym)
        except Exception as exc:
            raise HTTPException(500, str(exc)) from exc

    @app.get("/api/holidays")
    async def list_holidays_route(
        year_month: str | None = None,
        conn=Depends(get_conn),
        client: TimesheetClient = Depends(get_client),
    ) -> list[dict]:
        """그 달의 공휴일 정보를 회사 시스템에서 가져온다 (read-only)."""
        import datetime as _dt
        from fastapi import HTTPException

        ym = year_month or _dt.date.today().strftime("%Y-%m")
        try:
            return await client.list_holidays(year_month=ym)
        except Exception as exc:
            raise HTTPException(500, str(exc)) from exc

    # ─── Weekly Report API ───────────────────────────────

    from . import weekly_table as weekly_module

    @app.get("/api/weekly-reports/{week_iso}")
    async def get_weekly_report_route(
        week_iso: str, conn=Depends(get_conn)
    ) -> dict:
        return db_module.get_weekly_report(conn, week_iso)

    @app.put("/api/weekly-reports/{week_iso}")
    async def put_weekly_report_route(
        week_iso: str,
        payload: WeeklyReportInput,
        conn=Depends(get_conn),
    ) -> dict:
        updated_at = db_module.upsert_weekly_report(conn, week_iso, payload.rows)
        return {"ok": True, "updated_at": updated_at}

    @app.post("/api/weekly-reports/{week_iso}/generate")
    async def generate_weekly_report_route(
        week_iso: str,
        payload: WeeklyReportGenerateInput,
        conn=Depends(get_conn),
        client: TimesheetClient = Depends(get_client),
    ) -> dict:
        import datetime as _dt

        existing = db_module.get_weekly_report(conn, week_iso)
        preserve = existing["rows"] if payload.preserve_manual else None

        # 지난주/이번주 가 걸친 모든 month 휴가 fetch (set 으로 중복 제거)
        year_s, w_s = week_iso.split("-W")
        this_monday = _dt.date.fromisocalendar(int(year_s), int(w_s), 1)
        this_friday = this_monday + _dt.timedelta(days=4)
        last_monday = this_monday - _dt.timedelta(days=7)
        last_friday = last_monday + _dt.timedelta(days=4)
        months = {
            d.strftime("%Y-%m")
            for d in (last_monday, last_friday, this_monday, this_friday)
        }
        all_vacations: list[dict] = []
        for ym in sorted(months):
            try:
                all_vacations.extend(await client.list_vacations(year_month=ym))
            except Exception as exc:
                # 휴가 fetch 실패는 경고만 — 본문은 그대로 생성
                logger.warning(
                    "weekly_generate: vacation fetch failed ym=%s err=%s",
                    ym, exc,
                )

        # author_name: 설정 우선, 비면 client 캐시된 user.name
        author_name = (
            db_module.get_setting(conn, "report.author_name") or ""
        ).strip()
        if not author_name and getattr(client, "_user", None):
            author_name = client._user.name or ""

        rows = weekly_module.build_weekly_table_rows(
            conn, week_iso=week_iso, preserve_manual_rows=preserve,
            vacations=all_vacations, author_name=author_name,
        )
        updated_at = db_module.upsert_weekly_report(conn, week_iso, rows)
        return {"week_iso": week_iso, "rows": rows, "updated_at": updated_at}

    @app.post("/api/actions/weekly-report-upnote")
    async def action_weekly_report_upnote(
        payload: WeeklyReportUpnoteInput, conn=Depends(get_conn),
    ) -> dict:
        from fastapi import HTTPException

        from . import upnote as upnote_module

        notebook_id = (
            db_module.get_setting(conn, "upnote.weekly_notebook_id") or ""
        )
        if not notebook_id:
            raise HTTPException(
                400,
                "upnote.weekly_notebook_id 가 설정되지 않았습니다. "
                "설정 페이지에서 주간업무보고 노트북 ID 를 먼저 등록하세요.",
            )

        title_template = (
            db_module.get_setting(conn, "upnote.title_template")
            or SETTING_DEFAULTS["upnote.title_template"]
        )
        markdown_setting = (
            db_module.get_setting(conn, "upnote.markdown")
            or SETTING_DEFAULTS["upnote.markdown"]
        )
        markdown = markdown_setting.strip().lower() == "true"
        wrap_setting = (
            db_module.get_setting(conn, "upnote.wrap_in_code_block")
            or SETTING_DEFAULTS["upnote.wrap_in_code_block"]
        )
        wrap_in_code = wrap_setting.strip().lower() == "true"

        wr = db_module.get_weekly_report(conn, payload.week_iso)
        rows = wr["rows"]
        if not rows:
            raise HTTPException(
                400, "이 주의 보고서가 비어있습니다. 먼저 생성/편집하세요.",
            )

        ctx_globals = fmt_module._week_globals(payload.week_iso)
        try:
            title = fmt_module.render_upnote_title(title_template, ctx_globals)
        except Exception as exc:
            db_module.log_action(
                conn, "weekly_report_upnote", payload.week_iso, "fail", str(exc),
            )
            raise HTTPException(400, str(exc)) from exc

        # 주간업무보고 UpNote 는 Unicode 박스 표 (monospace) 로 시각화.
        # markdown 표의 셀 안 줄바꿈(<br>) / 강조(**\*)…**) 가 사용자의
        # wrap_in_code_block / markdown=false 환경에서 raw 로 노출되는 문제 회피.
        # ASCII 폭 계산으로 한글 셀도 정렬됨 (east_asian_width 기준).
        text = weekly_module.render_weekly_upnote_table(rows)
        if wrap_in_code:
            text = "```\n" + text + "\n```"

        try:
            url = upnote_module.open_new_note(
                title=title, text=text,
                notebook_id=notebook_id, markdown=markdown,
            )
            logger.info("Weekly UpNote url: %s", url[:300])
        except Exception as exc:
            db_module.log_action(
                conn, "weekly_report_upnote", payload.week_iso, "fail", str(exc),
            )
            raise HTTPException(500, str(exc)) from exc

        db_module.log_action(
            conn, "weekly_report_upnote", payload.week_iso, "ok",
            f"title={title}",
        )
        return {"title": title, "text": text, "opened": True}

    # ─── Email SMTP API ────────────────────────────────
    # password 는 Keychain (service="angeldash-email", account=email.username) 에 저장.
    # settings 테이블에는 평문 password 를 두지 않는다.
    from .._common.auth import KeychainStore

    EMAIL_KEYCHAIN_SERVICE = "angeldash-email"

    def _email_keychain(username: str) -> KeychainStore:
        # username 이 비어있으면 의미 있는 항목이 아니므로 caller 가 가드.
        return KeychainStore(account=username, service=EMAIL_KEYCHAIN_SERVICE)

    def _load_smtp_config(conn) -> tuple[object, str, str]:
        """settings + Keychain 에서 SMTP 파라미터 로드. 부족하면 HTTPException(400).

        Returns: (SmtpConfig, from_addr, signature_html).
        """
        from fastapi import HTTPException

        from . import email_smtp as smtp_module

        enabled = (
            db_module.get_setting(conn, "email.enabled") or "false"
        ).lower()
        if enabled != "true":
            raise HTTPException(
                400, "이메일 발송이 비활성화되어 있습니다 (설정에서 활성화)",
            )

        host = (db_module.get_setting(conn, "email.smtp_host") or "").strip()
        port_raw = (db_module.get_setting(conn, "email.smtp_port") or "0").strip()
        tls = (
            db_module.get_setting(conn, "email.smtp_tls") or "true"
        ).lower() == "true"
        username = (db_module.get_setting(conn, "email.username") or "").strip()
        from_addr = (db_module.get_setting(conn, "email.from") or username).strip()
        signature_html = db_module.get_setting(conn, "email.signature_html") or ""

        if not host or not username:
            raise HTTPException(400, "SMTP host/username 이 설정되지 않았습니다")
        try:
            port = int(port_raw)
        except ValueError as exc:
            raise HTTPException(
                400, f"SMTP port 가 숫자가 아닙니다: {port_raw}",
            ) from exc

        password = _email_keychain(username).get()
        if not password:
            raise HTTPException(
                400, "SMTP password 가 Keychain 에 저장되지 않았습니다",
            )

        return (
            smtp_module.SmtpConfig(
                host=host, port=port, use_tls=tls,
                username=username, password=password,
            ),
            from_addr,
            signature_html,
        )

    @app.put("/api/settings/email-password")
    async def put_email_password_route(
        payload: EmailPasswordInput, conn=Depends(get_conn),
    ) -> dict:
        """SMTP password 를 Keychain 에 저장. account = email.username 설정값."""
        from fastapi import HTTPException

        username = (db_module.get_setting(conn, "email.username") or "").strip()
        if not username:
            raise HTTPException(
                400, "먼저 email.username 을 설정 후 password 를 등록하세요",
            )
        try:
            _email_keychain(username).save(payload.password)
        except RuntimeError as exc:
            raise HTTPException(500, str(exc)) from exc
        return {"ok": True}

    @app.get("/api/settings/email-password-status")
    async def get_email_password_status_route(conn=Depends(get_conn)) -> dict:
        """저장 여부만 반환 (값은 절대 응답에 넣지 않는다)."""
        username = (db_module.get_setting(conn, "email.username") or "").strip()
        if not username:
            return {"has_password": False, "username": ""}
        present = _email_keychain(username).get() is not None
        return {"has_password": present, "username": username}

    @app.post("/api/actions/email-test")
    async def action_email_test_route(conn=Depends(get_conn)) -> dict:
        """SMTP 연결 + 인증만 검증. 실제 발송 없음."""
        from fastapi import HTTPException

        from . import email_smtp as smtp_module

        cfg, _from_addr, _sig = _load_smtp_config(conn)
        try:
            smtp_module.verify_connection(cfg)
        except smtp_module.SmtpError as exc:
            db_module.log_action(conn, "email_test", "", "fail", str(exc))
            raise HTTPException(400, str(exc)) from exc
        db_module.log_action(conn, "email_test", "", "ok", f"host={cfg.host}")
        return {"ok": True}

    @app.post("/api/actions/email-send-weekly")
    async def action_email_send_weekly_route(
        payload: EmailSendWeeklyInput, conn=Depends(get_conn),
    ) -> dict:
        """주간업무보고를 이메일로 발송. 받는사람은 override 가능."""
        from fastapi import HTTPException

        from . import email_smtp as smtp_module

        cfg, from_addr, signature_html = _load_smtp_config(conn)

        # 받는사람 결정: override 가 있으면 우선, 없으면 설정값
        to_raw = (
            payload.override_to
            if payload.override_to is not None
            else db_module.get_setting(conn, "email.to") or ""
        )
        cc_raw = (
            payload.override_cc
            if payload.override_cc is not None
            else db_module.get_setting(conn, "email.cc") or ""
        )
        to_list, cc_list = smtp_module.parse_recipients(to_raw, cc_raw)
        if not to_list:
            raise HTTPException(400, "받는사람(To) 이 비어있습니다")

        # 본문 빌드: subject 는 템플릿, body 는 인사말 + 표 + 마무리 + 서명
        wr = db_module.get_weekly_report(conn, payload.week_iso)
        rows = wr.get("rows") or []
        if not rows:
            raise HTTPException(400, "이 주의 보고서가 비어있습니다")

        subject_tmpl = (
            db_module.get_setting(conn, "email.subject_template")
            or SETTING_DEFAULTS["email.subject_template"]
        )
        ctx = fmt_module._week_globals(payload.week_iso)
        try:
            subject = fmt_module.render_upnote_title(subject_tmpl, ctx)
        except fmt_module.TemplateSyntaxError as exc:
            raise HTTPException(400, f"제목 템플릿 오류: {exc.message}") from exc

        greeting = db_module.get_setting(conn, "email.greeting") or ""
        closing = db_module.get_setting(conn, "email.closing") or ""

        html_body = weekly_module.render_email_html(
            rows, greeting=greeting, closing=closing,
            signature_html=signature_html,
        )
        plain_body = weekly_module.render_email_plain(
            rows, greeting=greeting, closing=closing,
        )

        spec = smtp_module.EmailMessageSpec(
            from_addr=from_addr,
            to=to_list, cc=cc_list,
            subject=subject,
            html_body=html_body, plain_body=plain_body,
        )
        try:
            smtp_module.send_email(cfg, spec)
        except smtp_module.SmtpError as exc:
            db_module.log_action(
                conn, "email_send_weekly", payload.week_iso, "fail", str(exc),
            )
            raise HTTPException(500, str(exc)) from exc

        db_module.log_action(
            conn, "email_send_weekly", payload.week_iso, "ok",
            f"to={','.join(to_list)} subject={subject}",
        )
        return {"ok": True, "subject": subject, "to": to_list, "cc": cc_list}

    # ─── Settings + Logs API ────────────────────────────

    SETTING_DEFAULTS: dict[str, str] = {
        "upnote.notebook_id": "",
        "upnote.markdown": "false",  # UpNote 본문을 markdown 으로 렌더할지
        "upnote.wrap_in_code_block": "false",  # 본문을 ``` 코드블록으로 감싸 markdown 변환 차단
        "upnote.title_template": DEFAULT_UPNOTE_TITLE,
        "upnote.body_template": DEFAULT_UPNOTE_BODY,
        "team_report.template": DEFAULT_TEAM_REPORT,
        "misc.holiday_exclude_labels": "",  # 출근일로 취급할 공휴일 label (콤마/줄바꿈 구분)
        "join.auto_task_name": "개발",  # 프로젝트 가입 시 자동으로 가입할 task name
        # 일일업무보고 페이지 상단의 "진행중인 일정" 영역 (월간/주간 계획 보관용)
        "ongoing_schedule": "",
        # 주간업무보고 페이지의 📤 UpNote 저장 — 일일 노트북과 분리된 노트북 ID
        "upnote.weekly_notebook_id": "",
        # 주간업무보고 휴가 행 표시명 (직급 포함 가능). 비면 client.user.name fallback.
        "report.author_name": "",
        # 주간업무보고 이메일 본문 — 표 위에 들어가는 인사말 (plain text, 여러 줄 가능)
        "email.greeting": "",
        # 주간업무보고 이메일 본문 — 표 아래 마무리 (plain text, 여러 줄)
        "email.closing": "",
        # 주간업무보고 이메일 받는사람 (콤마 구분, 여러 명 가능)
        "email.to": "",
        # 주간업무보고 이메일 참조 (콤마 구분)
        "email.cc": "",
        # 주간업무보고 이메일 제목 (Jinja2, upnote 제목과 동일 변수 — yy, ww 등)
        "email.subject_template": "주간업무보고 ({{ yy }}년 {{ ww }}주차)",
        # SMTP 발송 활성화 (true/false). 비활성이면 이메일 액션이 모두 차단.
        "email.enabled": "false",
        # SMTP 서버 주소 (예: smtp.office365.com)
        "email.smtp_host": "smtp.office365.com",
        # SMTP 포트 (587 = STARTTLS, 465 = SMTPS)
        "email.smtp_port": "587",
        # STARTTLS 사용 여부 (587 일 때 true, 465 일 때 false 권장)
        "email.smtp_tls": "true",
        # SMTP 인증 username (보통 보내는 메일 주소)
        "email.username": "",
        # 보내는사람 (From) — username 과 다를 수 있어 분리
        "email.from": "",
        # 이메일 서명 (HTML). SMTP 직접 발송이라 Outlook 의 자동 서명은 안 붙으므로
        # 사용자가 직접 입력. HTML body 끝(마무리 다음)에 추가. 비면 미첨부.
        "email.signature_html": "",
    }

    @app.get("/api/settings")
    async def get_settings_route(conn=Depends(get_conn)) -> dict:
        out: dict[str, str] = {}
        for k, default in SETTING_DEFAULTS.items():
            v = db_module.get_setting(conn, k)
            out[k] = v if v is not None else default
        return out

    @app.put("/api/settings")
    async def put_settings_route(
        payload: dict[str, str], conn=Depends(get_conn)
    ) -> dict:
        from fastapi import HTTPException

        template_keys = {
            "upnote.title_template",
            "upnote.body_template",
            "team_report.template",
        }
        # syntax 검증을 먼저 수행 (전체 통과 후에야 저장)
        for k, v in payload.items():
            if k in template_keys and v.strip():
                try:
                    fmt_module.validate_template(v)
                except fmt_module.TemplateSyntaxError as exc:
                    raise HTTPException(
                        status_code=400,
                        detail=f"template syntax error in {k}: {exc.message}",
                    ) from exc
        # 모두 OK일 때만 저장
        for k, v in payload.items():
            db_module.set_setting(conn, k, v)
        return {"ok": True}

    @app.post("/api/settings/preview")
    async def preview_settings_route(
        payload: SettingsPreviewInput, conn=Depends(get_conn)
    ) -> dict:
        from fastapi import HTTPException

        try:
            if payload.kind == "team_report":
                if payload.date:
                    ctx = fmt_module.build_team_report_context(conn, date=payload.date)
                elif payload.week_iso:
                    ctx = fmt_module.build_team_report_context(conn, week_iso=payload.week_iso)
                else:
                    raise HTTPException(400, "date or week_iso required")
                text = fmt_module.render_team_report(payload.template, ctx)
            else:
                if not payload.week_iso:
                    raise HTTPException(400, "week_iso required")
                ctx = fmt_module.build_week_context(conn, week_iso=payload.week_iso)
                if payload.kind == "upnote_title":
                    text = fmt_module.render_upnote_title(payload.template, ctx)
                elif payload.kind == "upnote_body":
                    text = fmt_module.render_upnote_body(payload.template, ctx)
                else:
                    raise HTTPException(400, f"unknown kind: {payload.kind}")
        except fmt_module.TemplateSyntaxError as exc:
            raise HTTPException(
                400, f"template syntax error: {exc.message}"
            ) from exc
        return {"text": text}

    @app.get("/api/logs")
    async def list_logs_route(conn=Depends(get_conn)) -> list[dict]:
        return db_module.recent_actions(conn, limit=200)

    # ─── Actions ────────────────────────────────────

    @app.post("/api/actions/team-report")
    async def action_team_report(
        payload: TeamReportActionInput, conn=Depends(get_conn)
    ) -> dict:
        from fastapi import HTTPException

        try:
            template = db_module.get_setting(conn, "team_report.template")
            if not template:
                template = SETTING_DEFAULTS["team_report.template"]
            if payload.date:
                ctx = fmt_module.build_team_report_context(
                    conn, date=payload.date
                )
                target_range = payload.date
            elif payload.week_iso:
                ctx = fmt_module.build_team_report_context(
                    conn, week_iso=payload.week_iso
                )
                target_range = payload.week_iso
            else:
                raise HTTPException(400, "date or week_iso required")
            text = fmt_module.render_team_report(template, ctx)
        except Exception as exc:
            db_module.log_action(
                conn, "report",
                payload.date or payload.week_iso or "?",
                "fail", str(exc),
            )
            raise
        db_module.log_action(conn, "report", target_range, "ok", None)
        return {"text": text}

    from . import upnote as upnote_module

    @app.post("/api/actions/upnote-sync")
    async def action_upnote_sync(
        payload: UpNoteSyncInput, conn=Depends(get_conn)
    ) -> dict:
        from fastapi import HTTPException

        title_template = (
            db_module.get_setting(conn, "upnote.title_template")
            or SETTING_DEFAULTS["upnote.title_template"]
        )
        body_template = (
            db_module.get_setting(conn, "upnote.body_template")
            or SETTING_DEFAULTS["upnote.body_template"]
        )
        notebook_id = db_module.get_setting(conn, "upnote.notebook_id") or ""
        # 'true'/'false' 문자열로 settings 에 저장
        markdown_setting = (
            db_module.get_setting(conn, "upnote.markdown")
            or SETTING_DEFAULTS["upnote.markdown"]
        )
        markdown = markdown_setting.strip().lower() == "true"
        wrap_setting = (
            db_module.get_setting(conn, "upnote.wrap_in_code_block")
            or SETTING_DEFAULTS["upnote.wrap_in_code_block"]
        )
        wrap_in_code = wrap_setting.strip().lower() == "true"

        try:
            ctx = fmt_module.build_week_context(conn, week_iso=payload.week_iso)
            title = fmt_module.render_upnote_title(title_template, ctx)
            text = fmt_module.render_upnote_body(body_template, ctx)
        except Exception as exc:
            db_module.log_action(
                conn, "upnote", payload.week_iso, "fail", str(exc),
            )
            raise HTTPException(400, str(exc)) from exc

        # 코드 블록 wrap (markdown 자동 변환 차단)
        if wrap_in_code:
            text = "```\n" + text + "\n```"

        if payload.dry_run:
            return {"title": title, "text": text, "opened": False}

        # 실제 URL 호출 — 디버깅용으로 url 도 같이 로깅
        try:
            url = upnote_module.open_new_note(
                title=title, text=text,
                notebook_id=notebook_id, markdown=markdown,
            )
            logger.info("UpNote sync url: %s", url[:300])
        except Exception as exc:
            db_module.log_action(
                conn, "upnote", payload.week_iso, "fail", str(exc),
            )
            raise HTTPException(500, str(exc)) from exc

        db_module.log_action(
            conn, "upnote", payload.week_iso, "ok",
            f"title={title}",
        )
        return {"title": title, "text": text, "opened": True}

    @app.post("/api/actions/timesheet-submit")
    async def action_timesheet_submit(
        payload: TimesheetSubmitInput,
        conn=Depends(get_conn),
        client: TimesheetClient = Depends(get_client),
    ) -> dict:
        from fastapi import HTTPException

        if not (payload.date or payload.week_iso):
            raise HTTPException(400, "date or week_iso required")

        # 대상 entries 수집
        if payload.date:
            day = db_module.get_day(conn, payload.date)
            rows = [{**e, "date": payload.date} for e in day["entries"]]
            target_range = payload.date
        else:
            week = db_module.get_week(conn, payload.week_iso)
            rows = []
            for d in week:
                for e in d["entries"]:
                    rows.append({**e, "date": d["date"]})
            target_range = payload.week_iso

        # 매핑 분류 (ready / missing_mapping / excluded / missing_remote_id)
        items: list[dict] = []
        ready: list[dict] = []
        missing_categories: list[str] = []
        for e in rows:
            # 본문 패턴 매핑 먼저 검사 (긴 패턴 우선)
            haystack = (e["category"] or "") + "\n" + (e.get("body_md") or "")
            pm = db_module.find_pattern_match(conn, haystack)
            if pm is not None:
                if pm["excluded"]:
                    items.append({**e, "status": "excluded",
                                  "project_name": None, "task_name": None,
                                  "matched_pattern": pm["pattern"]})
                    continue
                if pm["project_id"] is not None:
                    project = conn.execute(
                        "SELECT name, remote_id FROM projects WHERE id = ?",
                        (pm["project_id"],),
                    ).fetchone()
                    task_name = (
                        (project["remote_id"] or "").strip()
                        if project else ""
                    )
                    if not task_name:
                        items.append({**e, "status": "missing_remote_id",
                                      "project_name": pm["project_name"],
                                      "task_name": None,
                                      "matched_pattern": pm["pattern"]})
                        missing_categories.append(e["category"])
                        continue
                    items.append({**e, "status": "ready",
                                  "project_name": pm["project_name"],
                                  "task_name": task_name,
                                  "matched_pattern": pm["pattern"]})
                    ready.append({**e, "task_name": task_name})
                    continue
                # project_id 없는 패턴 매핑 — 카테고리 매핑으로 fallback

            # 패턴 매칭 없으면 기존 카테고리 매핑으로 fallback
            m = db_module.get_mapping(conn, e["category"])
            if m is None or (m["project_id"] is None and not m["excluded"]):
                items.append({**e, "status": "missing_mapping",
                              "project_name": None, "task_name": None})
                missing_categories.append(e["category"])
                continue
            if m["excluded"]:
                items.append({**e, "status": "excluded",
                              "project_name": None, "task_name": None})
                continue
            project = conn.execute(
                "SELECT name, remote_id FROM projects WHERE id = ?",
                (m["project_id"],),
            ).fetchone()
            task_name = (
                (project["remote_id"] or "").strip() if project else ""
            )
            if not task_name:
                items.append({**e, "status": "missing_remote_id",
                              "project_name": m["project_name"],
                              "task_name": None})
                missing_categories.append(e["category"])
                continue
            items.append({**e, "status": "ready",
                          "project_name": m["project_name"],
                          "task_name": task_name})
            ready.append({**e, "task_name": task_name})

        if payload.dry_run:
            return {"items": items, "missing": missing_categories}

        if missing_categories:
            raise HTTPException(
                400, f"missing mappings: {', '.join(missing_categories)}"
            )
        if not ready:
            return {"items": items, "results": [], "missing": []}

        # 필요한 월별 list_jobtime_tasks 호출 → name → task_id 맵
        months = sorted({e["date"][:7] for e in ready})
        task_id_by_month: dict[str, dict[str, str]] = {}
        for ym in months:
            try:
                tasks = await client.list_jobtime_tasks(year_month=ym)
            except Exception as exc:
                db_module.log_action(
                    conn, "timesheet", target_range, "fail",
                    f"list_jobtime_tasks({ym}): {exc}",
                )
                raise HTTPException(500, f"task 목록 조회 실패: {exc}") from exc
            task_id_by_month[ym] = {t["name"]: t["task_id"] for t in tasks}

        # save 페이로드 빌드 (task 미등록 항목은 분류)
        save_rows: list[dict] = []
        unregistered: list[str] = []
        for e in ready:
            ym = e["date"][:7]
            tid = task_id_by_month.get(ym, {}).get(e["task_name"])
            if not tid:
                unregistered.append(e["task_name"])
                continue
            save_rows.append({
                "task_id": tid,
                "work_hour": e["hours"],
                "work_day": e["date"].replace("-", ""),  # YYYYMMDD
                "user_id": client.user_id,
            })

        if unregistered:
            uniq = sorted(set(unregistered))
            db_module.log_action(
                conn, "timesheet", target_range, "fail",
                f"unregistered tasks: {', '.join(uniq)}",
            )
            raise HTTPException(
                400,
                f"타임시트에 미등록된 task: {', '.join(uniq)}. "
                "회사 페이지에서 먼저 task 를 추가하세요.",
            )

        if not save_rows:
            return {"items": items, "results": [], "missing": []}

        # submit_jobtimes 일괄 호출
        try:
            await client.submit_jobtimes(save_rows)
        except Exception as exc:
            db_module.log_action(
                conn, "timesheet", target_range, "fail", str(exc),
            )
            raise HTTPException(500, str(exc)) from exc

        db_module.log_action(
            conn, "timesheet", target_range, "ok",
            f"{len(save_rows)} rows",
        )
        return {
            "items": items,
            "results": [{**e, "status": "ok"} for e in ready],
            "missing": [],
        }

    @app.post("/api/actions/timesheet-push-one")
    async def action_timesheet_push_one(
        payload: TimesheetPushOneInput,
        conn=Depends(get_conn),
        client: TimesheetClient = Depends(get_client),
    ) -> dict:
        """단일 (date, task_name, hours) 를 회사 시스템에 push.

        hours=0 이면 그 셀의 시간을 0 으로 update → 사실상 삭제.
        회사 시스템의 task_id 는 매월 다를 수 있으므로 매번 search 호출로 확인.
        """
        from fastapi import HTTPException

        ym = payload.date[:7]
        try:
            tasks = await client.list_jobtime_tasks(year_month=ym)
        except Exception as exc:
            raise HTTPException(500, f"task 목록 조회 실패: {exc}") from exc

        by_name = {t["name"]: t["task_id"] for t in tasks}
        task_id = by_name.get(payload.task_name)
        if not task_id:
            raise HTTPException(
                400,
                f"task '{payload.task_name}' 가 회사 시스템에 등록되어 있지 않습니다.",
            )

        rows = [{
            "task_id": task_id,
            "work_hour": payload.hours,
            "work_day": payload.date.replace("-", ""),
            "user_id": client.user_id,
        }]
        try:
            await client.submit_jobtimes(rows)
        except Exception as exc:
            db_module.log_action(
                conn, "timesheet", payload.date, "fail",
                f"push-one {payload.task_name}: {exc}",
            )
            raise HTTPException(500, str(exc)) from exc

        action_label = "delete" if payload.hours == 0 else "push"
        db_module.log_action(
            conn, "timesheet", payload.date, "ok",
            f"{action_label} {payload.task_name} = {payload.hours}h",
        )
        return {"ok": True}
