"""timesheet.uangel.com Spring REST 클라이언트.

angelnet/src/angeldash/client.py 의 login() 흐름을 그대로 가져와 사용한다.
세션 쿠키(JSESSIONID) 는 httpx.AsyncClient 가 자동 보관해 후속 호출에 자동 포함.

jobtime API 메서드는 Phase 7 (DevTools 캡처 후) 에서 추가된다.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from .._common.http_relogin import AutoReloginHttp
from .._common.errors import ApiError, AuthError, BotBlockedError
from .models import User

logger = logging.getLogger(__name__)

# Timesheet 인증
TS_LOGIN = "https://timesheet.uangel.com/home/login.json"
TS_REDIRECT_PATH = "/times/timesheet/jobtime/create.htm"
TS_REDIRECT_PARAMS: dict[str, str] = {}

# Spring REST base (angelnet 과 같은 도메인)
SPRING_BASE = "https://timesheet.uangel.com/times/application/meeting_room/api"

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X)"
HTTP_TIMEOUT = 15.0
BOT_BLOCK_MARKER = "Automated requests are not allowed"
SESSION_TTL = 24 * 3600  # 24h


def _is_bot_blocked(payload: Any) -> bool:
    """응답 본문에 자동화 차단 메시지가 포함되어 있는지."""
    if isinstance(payload, dict):
        msg = payload.get("error") or payload.get("message") or ""
        return BOT_BLOCK_MARKER in str(msg)
    return False


class TimesheetClient:
    """timesheet.uangel.com Spring REST 호출 캡슐화.

    angelnet 의 AngelNetClient 와 같은 인증 흐름. 향후 두 도구를 통합하면
    공통 base class 로 추출 가능.
    """

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self._user: User | None = None
        self._session_ready = False
        self._session_expires = 0.0
        # 자동 재로그인 시 사용할 password 캐시. 최초 로그인 성공 시에만 채워짐.
        self._password: str | None = None
        # 만료 감지 + 1회 재시도 래퍼로 모든 HTTP 호출을 보낸다.
        raw_http = httpx.AsyncClient(
            verify=False,
            timeout=HTTP_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
        self._http = AutoReloginHttp(
            raw_http,
            can_refresh=lambda: self._password is not None,
            refresh=self._refresh_session,
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def _refresh_session(self) -> None:
        """만료 감지 시 호출되는 재로그인 훅. 캐시 무효화 후 login 재실행."""
        if self._password is None:
            raise AuthError("cannot refresh session without cached password")
        self._session_ready = False
        self._session_expires = 0.0
        self._user = None
        # join 페이지 hidden 값도 새 세션에서 재취득해야 안전
        self._join_ctx = None
        await self.login(self._password)

    # ─── 인증 ────────────────────────────────────────

    async def login(self, password: str) -> User:
        """Timesheet 로그인 후 current-user 호출하여 User 반환.

        캐시된 세션이 살아있으면 네트워크 호출 없이 캐시를 반환한다.
        """
        if self._user and self._session_ready and time.time() < self._session_expires:
            return self._user

        # angelnet 과 동일한 redirectUrl 형식. params 가 비면 query 없이 path 만.
        if TS_REDIRECT_PARAMS:
            rq = urlencode(TS_REDIRECT_PARAMS)
            redirect = f"{TS_REDIRECT_PATH}?{rq}"
        else:
            redirect = TS_REDIRECT_PATH

        resp = await self._http.post(
            TS_LOGIN,
            data={
                "userId": self.user_id,
                "password": password,
                "redirectUrl": redirect,
            },
        )
        body = self._safe_json(resp)
        if _is_bot_blocked(body):
            raise BotBlockedError(body.get("error") or body.get("message"))
        if resp.status_code >= 500:
            raise ApiError(
                f"server error on login: status={resp.status_code}",
                status_code=resp.status_code,
                payload=body,
            )
        if resp.status_code >= 400:
            raise AuthError(f"login failed: status={resp.status_code} body={body}")

        # current-user 로 사용자 정보 확보
        cu = await self._http.get(f"{SPRING_BASE}/meeting-rooms/current-user")
        cu_body = self._safe_json(cu)
        if _is_bot_blocked(cu_body):
            raise BotBlockedError(cu_body.get("error") or cu_body.get("message"))
        if cu.status_code >= 500:
            raise ApiError(
                f"server error on current-user: status={cu.status_code}",
                status_code=cu.status_code,
                payload=cu_body,
            )
        if cu.status_code >= 400:
            raise AuthError(
                f"current-user failed: status={cu.status_code} body={cu_body}"
            )
        if not (isinstance(cu_body, dict) and cu_body.get("userId")):
            raise AuthError(f"current-user missing userId: {cu_body}")

        # name 은 별도 endpoint. 실패는 fatal 아님 (userId fallback)
        name = cu_body["userId"]
        try:
            nu = await self._http.get(
                f"{SPRING_BASE}/meeting-rooms/user-name",
                params={"userId": cu_body["userId"]},
            )
            if nu.status_code == 200:
                nb = nu.json()
                if isinstance(nb, dict) and nb.get("name"):
                    name = nb["name"]
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("user-name fetch failed (non-fatal): %s", exc)

        self._user = User(user_id=cu_body["userId"], name=name)
        self._session_ready = True
        self._session_expires = time.time() + SESSION_TTL
        # 성공한 password 만 캐시 → 첫 로그인 실패는 자동 재시도 트리거하지 않음.
        self._password = password
        logger.info("Spring session established for user=%s", self.user_id)
        return self._user

    # ─── 타임시트 jobtime API ──────────────────────
    # spec 부록 A 참조. 시스템은 task × 날짜 매트릭스 모델.

    JOBTIME_SEARCH_URL = (
        "https://timesheet.uangel.com/times/timesheet/jobtime/search.json"
    )
    JOBTIME_SAVE_URL = "https://timesheet.uangel.com/times/timesheet/jobtime/save.json"

    JOIN_PAGE_URL = "https://timesheet.uangel.com/times/timesheet/join/searchForm.htm"
    JOIN_SEARCH_URL = "https://timesheet.uangel.com/times/timesheet/join/search.json"
    JOIN_USER_MAP_SAVE_URL = (
        "https://timesheet.uangel.com/times/timesheet/join/UserMapJoinSave.json"
    )

    # 페이지 hidden 값 캐시 (인스턴스 단위)
    _join_ctx: dict[str, str] | None = None

    async def list_jobtime_tasks(
        self, *, year_month: str, dept_code: str = ""
    ) -> list[dict[str, str]]:
        """그 달의 task 목록 조회 (search.json).

        Args:
            year_month: 'YYYY-MM' 형식.
            dept_code: 일반적으로 빈 문자열 — 서버가 세션의 user 로 결정.

        Returns:
            [{"task_id": "11113", "name": "...", "work_type": "개발"}, ...]
            합계/소계 행 (id 가 음수 또는 이름 비어있음) 은 제외.
        """
        resp = await self._http.post(
            self.JOBTIME_SEARCH_URL,
            data={"dept_code": dept_code, "year_month": year_month},
        )
        body = self._safe_json(resp, exc_type=ApiError)
        if _is_bot_blocked(body):
            raise BotBlockedError(str(body))
        if resp.status_code >= 400:
            raise ApiError(
                f"list_jobtime_tasks failed: status={resp.status_code}",
                status_code=resp.status_code,
                payload=body,
            )
        rows = body.get("rows", []) if isinstance(body, dict) else []
        out: list[dict[str, str]] = []
        for r in rows:
            rid = str(r.get("id", ""))
            try:
                if int(rid) < 0:
                    continue
            except ValueError:
                continue
            data = r.get("data", [])
            if len(data) < 2:
                continue
            name = (data[0] or "").strip()
            if not name:
                continue
            out.append(
                {
                    "task_id": rid,
                    "name": name,
                    "work_type": (data[1] or "").strip(),
                }
            )
        return out

    HOLIDAY_TAG_SEARCH_URL = (
        "https://timesheet.uangel.com/times/timesheet/jobtime/holidayTagSearch.json"
    )

    async def list_holidays(self, *, year_month: str) -> list[dict[str, Any]]:
        """그 달의 공휴일/대체휴일/회사 행정휴일 등 태그 목록 조회.

        Returns:
            [{"date": "YYYY-MM-DD", "label": "노동절", "types": ["public"]}, ...]
        """
        import datetime as _dt

        resp = await self._http.post(
            self.HOLIDAY_TAG_SEARCH_URL,
            data={"year_month": year_month},
        )
        body = self._safe_json(resp, exc_type=ApiError)
        if _is_bot_blocked(body):
            raise BotBlockedError(str(body))
        if resp.status_code >= 400:
            raise ApiError(
                f"list_holidays failed: status={resp.status_code}",
                status_code=resp.status_code,
                payload=body,
            )
        # 응답 형태: {"days": {"20260501": {"label": "...", "types": [...]}, ...}}
        days = body.get("days", {}) if isinstance(body, dict) else {}
        out: list[dict[str, Any]] = []
        for ymd, info in days.items():
            # ymd = 'YYYYMMDD'
            if len(ymd) != 8 or not ymd.isdigit():
                continue
            try:
                date_iso = _dt.date(
                    int(ymd[0:4]), int(ymd[4:6]), int(ymd[6:8])
                ).isoformat()
            except ValueError:
                continue
            label = (info.get("label") if isinstance(info, dict) else None) or ""
            types = (info.get("types") if isinstance(info, dict) else None) or []
            out.append({"date": date_iso, "label": label, "types": list(types)})
        out.sort(key=lambda x: x["date"])
        return out

    VACATION_SEARCH_URL = (
        "https://timesheet.uangel.com/times/timesheet/jobtime/vacationSearch.json"
    )

    async def list_vacations(self, *, year_month: str) -> list[dict[str, Any]]:
        """그 달의 휴가 (연차/반차 등) 목록 조회.

        Returns:
            [{"date": "YYYY-MM-DD", "type": "연차", "hours": 8.0}, ...]
            시간이 0 인 셀은 결과에 포함되지 않는다.
        """
        import datetime as _dt

        resp = await self._http.post(
            self.VACATION_SEARCH_URL,
            data={"year_month": year_month},
        )
        body = self._safe_json(resp, exc_type=ApiError)
        if _is_bot_blocked(body):
            raise BotBlockedError(str(body))
        if resp.status_code >= 400:
            raise ApiError(
                f"list_vacations failed: status={resp.status_code}",
                status_code=resp.status_code,
                payload=body,
            )
        rows = body.get("rows", []) if isinstance(body, dict) else []

        year_str, month_str = year_month.split("-")
        year, month = int(year_str), int(month_str)

        out: list[dict[str, Any]] = []
        for r in rows:
            data = r.get("data", [])
            if not data:
                continue
            type_name = (data[0] or "").strip()
            if not type_name:
                continue
            # data[1..-1] 은 일별 시간 (마지막은 월 합계라 제외)
            for day, value in enumerate(data[1:-1], start=1):
                try:
                    hours = float(value)
                except (TypeError, ValueError):
                    continue
                if hours <= 0:
                    continue
                try:
                    date_iso = _dt.date(year, month, day).isoformat()
                except ValueError:
                    continue  # 그 달에 없는 일자 (예: 4월 31일)
                out.append({"date": date_iso, "type": type_name, "hours": hours})
        return out

    async def fetch_jobtime_grid_detailed(
        self, *, year_month: str
    ) -> list[dict[str, Any]]:
        """그 달의 task 메타 + 일별 시간을 분리 보존해서 반환.

        회사 시스템의 row 형식이 회계 항목에 따라 텍스트 컬럼 수가 다르다
        (단순 task: [name, work_type, 1일, …], 트리 구조: [root, sub, leaf, 1일, …]
         처럼 1~3개). 첫 float 변환 가능한 위치부터 일별 시간으로 간주하고,
        그 앞까지의 텍스트들을 메타로 모은다.

        label 규칙:
        - texts 가 1개   → "{texts[0]}"
        - texts 가 2개+  → "{texts[0]} [{texts[-1]}]" (root + leaf, 같으면 root만)

        Returns:
            [{"task_name": <root>, "label": <표시 라벨>, "work_type": <leaf or "">,
              "days": {day: hours}}, ...]
        """
        resp = await self._http.post(
            self.JOBTIME_SEARCH_URL,
            data={"dept_code": "", "year_month": year_month},
        )
        body = self._safe_json(resp, exc_type=ApiError)
        if _is_bot_blocked(body):
            raise BotBlockedError(str(body))
        if resp.status_code >= 400:
            raise ApiError(
                f"fetch_jobtime_grid_detailed failed: status={resp.status_code}",
                status_code=resp.status_code,
                payload=body,
            )
        rows = body.get("rows", []) if isinstance(body, dict) else []
        out: list[dict[str, Any]] = []
        for r in rows:
            rid = str(r.get("id", ""))
            try:
                if int(rid) < 0:
                    continue
            except ValueError:
                continue
            data = r.get("data", [])
            if not data:
                continue

            # 텍스트 메타 / 일별 시간 분리 — 첫 float-가능 셀까지 텍스트로 모음
            texts: list[str] = []
            nums: list[float] = []
            for v in data:
                if not nums:
                    try:
                        nums.append(float(v))
                    except (TypeError, ValueError):
                        texts.append(str(v or "").strip())
                else:
                    try:
                        nums.append(float(v))
                    except (TypeError, ValueError):
                        nums.append(0.0)

            if not texts or not texts[0]:
                continue  # 합계/소계 행 등

            # 마지막 num 은 월합계, 그 앞이 일별
            day_hours: dict[int, float] = {}
            for day, h in enumerate(nums[:-1], start=1):
                if h > 0:
                    day_hours[day] = h

            root = texts[0]
            leaf = texts[-1] if len(texts) > 1 else ""
            if leaf and leaf != root:
                label = f"{root} [{leaf}]"
            else:
                label = root

            out.append({
                "task_name": root,
                "label": label,
                "work_type": leaf,
                "days": day_hours,
            })
        return out

    async def fetch_jobtime_grid(
        self, *, year_month: str
    ) -> dict[str, dict[int, float]]:
        """그 달의 task 별 일별 시간 매트릭스를 반환.

        Returns:
            {"task_name": {day_of_month: hours}, ...}
            시간이 0 인 셀은 포함되지 않는다. 합계/소계 행은 제외.
        """
        resp = await self._http.post(
            self.JOBTIME_SEARCH_URL,
            data={"dept_code": "", "year_month": year_month},
        )
        body = self._safe_json(resp, exc_type=ApiError)
        if _is_bot_blocked(body):
            raise BotBlockedError(str(body))
        if resp.status_code >= 400:
            raise ApiError(
                f"fetch_jobtime_grid failed: status={resp.status_code}",
                status_code=resp.status_code,
                payload=body,
            )
        rows = body.get("rows", []) if isinstance(body, dict) else []
        out: dict[str, dict[int, float]] = {}
        for r in rows:
            rid = str(r.get("id", ""))
            try:
                if int(rid) < 0:
                    continue
            except ValueError:
                continue
            data = r.get("data", [])
            if len(data) < 2:
                continue
            name = (data[0] or "").strip()
            if not name:
                continue
            day_hours: dict[int, float] = {}
            # jobtime grid 의 data 형식: [task_name, work_type, 1일, 2일, ..., 말일, 월합계]
            # data[2..-2] 가 일별 시간. (vacation grid 는 work_type 컬럼이 없어 data[1..-1].)
            for day, value in enumerate(data[2:-1], start=1):
                try:
                    h = float(value)
                except (TypeError, ValueError):
                    continue
                if h > 0:
                    day_hours[day] = h
            out[name] = day_hours
        return out

    # ─── 휴가계 조회 (read-only) ──────────────────
    VACATION_ANNUAL_URL = (
        "https://timesheet.uangel.com/times/application/vacation/getAnnualVacation.json"
    )
    VACATION_APPLICATION_SEARCH_URL = (
        "https://timesheet.uangel.com/times/application/vacation/search.htm"
    )

    async def get_annual_vacation_summary(
        self,
        *,
        year: int,
    ) -> dict[str, float | None]:
        """연간 휴가 사용/잔여 일수.

        Returns:
            {"total": 23.0, "used": 9.0, "remaining": 14.0} — 파싱 실패 시 raw_text 포함.
            서버 응답은 따옴표로 감싸진 URL-encoded 문자열 (예: '"23.0+-+9.0+%3D+14.0+%EC%9D%BC"').
        """
        from urllib.parse import unquote
        import re as _re

        resp = await self._http.get(
            self.VACATION_ANNUAL_URL,
            params={"user_id": self.user_id, "searchYear": str(year)},
        )
        if resp.status_code >= 400:
            raise ApiError(
                f"get_annual_vacation_summary failed: status={resp.status_code}",
                status_code=resp.status_code,
                payload=resp.text[:200],
            )
        raw = resp.text.strip()
        # 양 끝의 큰따옴표 제거 후 URL-decode
        if raw.startswith('"') and raw.endswith('"'):
            raw = raw[1:-1]
        text = unquote(raw.replace("+", " ")).strip()
        if BOT_BLOCK_MARKER in text:
            raise BotBlockedError(text[:200])
        # 'X - Y = Z 일' 패턴 추출
        m = _re.search(r"([\d.]+)\s*-\s*([\d.]+)\s*=\s*([\d.]+)", text)
        if not m:
            return {"total": None, "used": None, "remaining": None, "raw_text": text}
        return {
            "total": float(m.group(1)),
            "used": float(m.group(2)),
            "remaining": float(m.group(3)),
            "raw_text": text,
        }

    async def list_vacation_applications(
        self,
        *,
        year: int,
        dept_code: str = "DADABF",
        position: str = "",
    ) -> list[dict[str, str]]:
        """연간 휴가계 목록 조회 (read-only).

        search.htm 가 HTML 페이지를 반환하므로 응답에서 `<table id="list">` 의
        9개 컬럼(기안일/유형/사유/기간/일수/등록일/이름/상태/명령) 을 파싱한다.

        Returns:
            [{"draft_date","vacation_type","reason","from_date","to_date",
              "days","registered_date","name","status","vacation_id"}, ...]
            vacation_id 는 상세보기 버튼의 인자에서 추출.
        """
        resp = await self._http.post(
            self.VACATION_APPLICATION_SEARCH_URL,
            data={
                "searchYear": str(year),
                "cmd": "user",
                "page": "1",
                "startDate": "",
                "endDate": "",
                "name": "",
                "status": "",
                "deptCode": dept_code,
                "position": position,
            },
        )
        if resp.status_code >= 400:
            raise ApiError(
                f"list_vacation_applications failed: status={resp.status_code}",
                status_code=resp.status_code,
                payload=resp.text[:300],
            )
        html = resp.text
        if BOT_BLOCK_MARKER in html:
            raise BotBlockedError(html[:300])
        return _parse_vacation_list_html(html)

    EXCEL_DOWNLOAD_URL = (
        "https://timesheet.uangel.com/times/timesheet/jobtime/excelbyday.json"
    )

    async def download_jobtime_excel(self, *, year_month: str) -> tuple[bytes, str]:
        """그 달의 jobtime Excel(xlsx) 을 받아 (content, filename) 반환.

        filename 은 회사 서버가 Content-Disposition 으로 알려주는 그대로 (URL 디코드 적용).
        """
        from urllib.parse import unquote

        resp = await self._http.post(
            self.EXCEL_DOWNLOAD_URL,
            data={"year_month": year_month},
        )
        if resp.status_code >= 400:
            raise ApiError(
                f"download_jobtime_excel failed: status={resp.status_code}",
                status_code=resp.status_code,
                payload=resp.text[:300],
            )
        body = resp.content
        # 응답이 비어있거나 너무 작으면 이상
        if not body or len(body) < 100:
            raise ApiError(
                f"unexpected empty excel response (len={len(body)})",
                status_code=resp.status_code,
                payload=resp.text[:300],
            )
        # XLSX 매직 바이트 (PK\x03\x04) 확인
        if not body.startswith(b"PK\x03\x04"):
            # bot block 같은 텍스트 응답일 수도
            try:
                text_head = body[:300].decode("utf-8", errors="ignore")
            except Exception:
                text_head = ""
            if BOT_BLOCK_MARKER in text_head:
                raise BotBlockedError(text_head)
            raise ApiError(
                f"unexpected response (not xlsx): {text_head[:200]}",
                status_code=resp.status_code,
            )

        # Content-Disposition 에서 filename 추출
        cd = resp.headers.get("content-disposition", "")
        filename = f"jobtime_{year_month}.xlsx"
        # filename="..."; 형태에서 값 추출
        if "filename=" in cd:
            raw = cd.split("filename=", 1)[1].strip()
            # 양쪽 큰따옴표 제거 + URL 디코드
            raw = raw.split(";", 1)[0].strip().strip('"')
            try:
                decoded = unquote(raw)
                if decoded:
                    filename = decoded
            except Exception:
                pass
        return body, filename

    async def submit_jobtimes(self, rows: list[dict[str, Any]]) -> str:
        """jobtime 일괄 저장 (save.json).

        Args:
            rows: 각 element 는
                {"task_id": str, "work_hour": int|float,
                 "work_day": "YYYYMMDD", "user_id": str}.

        Returns:
            성공 시 응답 본문 (text).

        Raises:
            ApiError: 응답이 'error:' 로 시작하거나 4xx/5xx.
            BotBlockedError: 자동화 차단.
        """
        import json as _json

        resp = await self._http.post(
            self.JOBTIME_SAVE_URL,
            data={"rows": _json.dumps(rows, ensure_ascii=False)},
        )
        if resp.status_code >= 400:
            raise ApiError(
                f"submit_jobtimes failed: status={resp.status_code}",
                status_code=resp.status_code,
                payload=resp.text[:500],
            )
        text = resp.text
        # bot block 메시지가 text 로 올 가능성도 검사
        if BOT_BLOCK_MARKER in text:
            raise BotBlockedError(text[:300])
        if text.lstrip().startswith("error:"):
            msg = text.split(":", 1)[1].strip() if ":" in text else "save error"
            raise ApiError(f"jobtime save failed: {msg}", payload=text[:500])
        return text

    # ─── 프로젝트 가입 API ─────────────────────────

    async def _fetch_join_page_context(self) -> dict[str, str]:
        """프로젝트 가입 페이지의 hidden inputs (position, dept_code 등) 를 캐시.

        매 검색/저장 호출에 필요한 사용자별 값들. 인스턴스 단위로 1회 fetch.
        """
        if self._join_ctx is not None:
            return self._join_ctx
        resp = await self._http.get(self.JOIN_PAGE_URL)
        if resp.status_code >= 400:
            raise ApiError(
                f"join page fetch failed: status={resp.status_code}",
                status_code=resp.status_code,
            )
        import re

        html = resp.text
        ctx: dict[str, str] = {}
        for field in ("user_id", "position", "status", "dept_code", "group_id"):
            # name="X" value="V" 또는 id="X" value="V" 패턴
            m = re.search(
                rf"(?:name|id)=[\"\']{field}[\"\'][^>]*value=[\"\']([^\"\']*)[\"\']",
                html,
            )
            if not m:
                # value 가 앞에 있는 경우
                m = re.search(
                    rf"value=[\"\']([^\"\']*)[\"\'][^>]*(?:name|id)=[\"\']{field}[\"\']",
                    html,
                )
            if m:
                ctx[field] = m.group(1)
        self._join_ctx = ctx
        return ctx

    async def search_joinable_projects(
        self, *, keyword: str = "", page: int = 1, page_size: int = 50
    ) -> dict[str, Any]:
        """회사 시스템에서 프로젝트 검색 (사용자 부서/직위 기준).

        Returns:
            {"rows": [{"project_id", "code", "name", "joined": bool}, ...],
             "total": N, "page": N, "page_size": N}
        """
        ctx = await self._fetch_join_page_context()
        data = {
            "status": ctx.get("status", "C002001"),
            "dept_code": ctx.get("dept_code", "") + "%",
            "position": ctx.get("position", ""),
            "user_id": ctx.get("user_id", self.user_id),
            "keyword": keyword,
            "group_id": ctx.get("group_id", "USER"),
            "page": str(page),
            "pageSize": str(page_size),
        }
        resp = await self._http.post(self.JOIN_SEARCH_URL, data=data)
        body = self._safe_json(resp, exc_type=ApiError)
        if _is_bot_blocked(body):
            raise BotBlockedError(str(body))
        if resp.status_code >= 400:
            raise ApiError(
                f"search_joinable_projects failed: status={resp.status_code}",
                status_code=resp.status_code,
                payload=body,
            )
        # 실제 응답: {"pageSize", "page", "rows": {"rows": [...]}, "totalCount"}
        # 즉 페이징 wrapper 안에 dhtmlxgrid 형식 ({"rows": [...]}) 이 한 번 더 감싸짐.
        rows_payload: Any = body.get("rows", []) if isinstance(body, dict) else []
        if isinstance(rows_payload, dict):
            rows_payload = rows_payload.get("rows", []) or []
        if not isinstance(rows_payload, list):
            rows_payload = []
        out_rows: list[dict[str, Any]] = []
        for r in rows_payload:
            if not isinstance(r, dict):
                continue
            row_data = r.get("data", [])
            if not isinstance(row_data, list) or len(row_data) < 3:
                continue
            joined_flag = str(row_data[3]) if len(row_data) >= 4 else "0"
            out_rows.append(
                {
                    "project_id": str(row_data[0]),
                    "code": str(row_data[1]),
                    "name": str(row_data[2]),
                    "joined": joined_flag in ("1", "true", "True"),
                }
            )
        return {
            "rows": out_rows,
            "total": int(body.get("totalCount", len(out_rows)))
            if isinstance(body, dict)
            else len(out_rows),
            "page": int(body.get("page", page)) if isinstance(body, dict) else page,
            "page_size": int(body.get("pageSize", page_size))
            if isinstance(body, dict)
            else page_size,
        }

    async def join_project(self, *, project_id: str) -> None:
        """프로젝트 가입 (UserMapJoinSave.json + status=C002001).

        탈퇴 경로는 회사 시스템에 존재하지 않음 (UserMapJoinSave 가 단방향 insert).
        탈퇴 시에는 unjoin_project() 를 사용 — tasksMapDelAll 의 cascade 로 처리.
        """
        import json as _json

        ctx = await self._fetch_join_page_context()
        rows = [
            {
                "project_id": project_id,
                "user_id": ctx.get("user_id", self.user_id),
                "status": "C002001",
            }
        ]
        resp = await self._http.post(
            self.JOIN_USER_MAP_SAVE_URL,
            data={"rows": _json.dumps(rows)},
        )
        if resp.status_code >= 400:
            raise ApiError(
                f"join_project failed: status={resp.status_code}",
                status_code=resp.status_code,
                payload=resp.text[:300],
            )
        text = resp.text
        if BOT_BLOCK_MARKER in text:
            raise BotBlockedError(text[:300])
        if text.lstrip().startswith("error:"):
            msg = text.split(":", 1)[1].strip()
            raise ApiError(f"project join save failed: {msg}", payload=text[:500])

    JOIN_TASKS_SEARCH_URL = (
        "https://timesheet.uangel.com/times/timesheet/join/tasks_search.json"
    )
    JOIN_TASKS_SAVE_URL = (
        "https://timesheet.uangel.com/times/timesheet/join/tasksMapJoinSave.json"
    )

    async def list_project_tasks(self, *, project_id: str) -> list[dict[str, Any]]:
        """프로젝트의 task 목록 + 가입 여부.

        Returns:
            [{"task_id": "11131", "name": "개발", "joined": True}, ...]
        """
        ctx = await self._fetch_join_page_context()
        resp = await self._http.post(
            self.JOIN_TASKS_SEARCH_URL,
            data={
                "project_id": project_id,
                "user_id": ctx.get("user_id", self.user_id),
            },
        )
        body = self._safe_json(resp, exc_type=ApiError)
        if _is_bot_blocked(body):
            raise BotBlockedError(str(body))
        if resp.status_code >= 400:
            raise ApiError(
                f"list_project_tasks failed: status={resp.status_code}",
                status_code=resp.status_code,
                payload=body,
            )
        rows = body.get("rows", []) if isinstance(body, dict) else []
        out: list[dict[str, Any]] = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            data = r.get("data", [])
            if not isinstance(data, list) or len(data) < 2:
                continue
            joined_flag = str(data[2]) if len(data) >= 3 else "0"
            out.append(
                {
                    "task_id": str(data[0]),
                    "name": str(data[1]),
                    "joined": joined_flag in ("1", "true", "True"),
                }
            )
        return out

    async def set_project_task_joined(self, *, project_id: str, task_id: str) -> None:
        """프로젝트의 특정 task 에 가입. tasksMapJoinSave.json 호출.

        회사 페이지 로직에 따라 'rows' 의 각 항목 status='C0000001'.
        """
        import json as _json

        ctx = await self._fetch_join_page_context()
        rows = [
            {
                "task_id": task_id,
                "user_id": ctx.get("user_id", self.user_id),
                "project_id": project_id,
                "status": "C0000001",
            }
        ]
        resp = await self._http.post(
            self.JOIN_TASKS_SAVE_URL,
            data={"rows": _json.dumps(rows)},
        )
        if resp.status_code >= 400:
            raise ApiError(
                f"set_project_task_joined failed: status={resp.status_code}",
                status_code=resp.status_code,
                payload=resp.text[:300],
            )
        text = resp.text
        if BOT_BLOCK_MARKER in text:
            raise BotBlockedError(text[:300])
        if text.lstrip().startswith("error:"):
            msg = text.split(":", 1)[1].strip()
            raise ApiError(f"task join save failed: {msg}", payload=text[:500])

    JOIN_TASKS_DEL_ALL_URL = (
        "https://timesheet.uangel.com/times/timesheet/join/tasksMapDelAll.htm"
    )

    async def unjoin_project(self, *, project_id: str) -> None:
        """프로젝트 + 모든 task 동시 탈퇴.

        회사 시스템에는 프로젝트 단독 탈퇴 API 가 없음 (UserMapJoinSave C002002 는 no-op).
        실제 동작: tasksMapDelAll.htm 가 task 전부 삭제 + 프로젝트도 자동 탈퇴 (cascade).
        단 가입 task 가 0개면 tasksMapDelAll 이 success=false 를 반환하므로,
        그 경우엔 임의 task 1개를 임시로 가입한 뒤 즉시 DelAll 로 같이 삭제.
        """
        ctx = await self._fetch_join_page_context()
        user_id = ctx.get("user_id", self.user_id)

        # task 가 가입돼 있어야 DelAll cascade 가 동작 → 없으면 임시 가입
        tasks = await self.list_project_tasks(project_id=project_id)
        if not tasks:
            raise ApiError(
                f"unjoin_project: project {project_id} has no tasks; "
                "cannot trigger cascade unjoin"
            )
        if not any(t.get("joined") for t in tasks):
            await self.set_project_task_joined(
                project_id=project_id,
                task_id=tasks[0]["task_id"],
            )

        resp = await self._http.post(
            self.JOIN_TASKS_DEL_ALL_URL,
            data={"user_id": user_id, "project_id": project_id},
        )
        if resp.status_code >= 400:
            raise ApiError(
                f"unjoin_project failed: status={resp.status_code}",
                status_code=resp.status_code,
                payload=resp.text[:300],
            )
        text = resp.text
        if BOT_BLOCK_MARKER in text:
            raise BotBlockedError(text[:300])
        try:
            body = resp.json()
        except ValueError:
            raise ApiError(f"unjoin_project: non-json response: {text[:200]}")
        if not (isinstance(body, dict) and body.get("success") is True):
            raise ApiError(
                f"unjoin_project: server rejected (body={body})",
                payload=body,
            )

    # ─── 내부 헬퍼 ─────────────────────────────────

    @staticmethod
    def _safe_json(
        resp: httpx.Response,
        exc_type: type[Exception] = AuthError,
    ) -> Any:
        """JSON 파싱 실패 시 지정 예외로 변환."""
        try:
            return resp.json()
        except ValueError as exc:
            if exc_type is ApiError:
                raise ApiError(
                    f"non-json response: status={resp.status_code}",
                    status_code=resp.status_code,
                ) from exc
            raise exc_type(f"non-json response: status={resp.status_code}") from exc


# ─── 휴가계 HTML 파서 ────────────────────────────────────


def _parse_vacation_list_html(html: str) -> list[dict[str, str]]:
    """search.htm 응답에서 `<table id="list">` 의 데이터 row 들을 dict 리스트로.

    각 row 는 9 td. 마지막 td 의 `goSubmit('detail','35115','detail')` 에서 id 추출.
    stdlib html.parser 만 사용 (외부 의존성 추가 없음).
    """
    import re as _re
    from html.parser import HTMLParser

    class _ListParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.in_list_table = False
            self.in_tbody = False
            self.depth = 0  # nested table 대응
            self.cur_row: list[str] | None = None
            self.cur_cell: list[str] | None = None
            self.rows: list[list[str]] = []
            self.last_button_onclick: str = ""

        def handle_starttag(self, tag, attrs):
            attrd = dict(attrs)
            if tag == "table":
                self.depth += 1
                if attrd.get("id") == "list":
                    self.in_list_table = True
            elif self.in_list_table and tag == "tbody":
                self.in_tbody = True
            elif self.in_list_table and self.in_tbody and tag == "tr":
                self.cur_row = []
            elif self.cur_row is not None and tag == "td":
                self.cur_cell = []
            elif self.cur_cell is not None and tag == "button":
                self.last_button_onclick = attrd.get("onclick", "")

        def handle_endtag(self, tag):
            if tag == "table":
                if self.in_list_table and self.depth == 1:
                    self.in_list_table = False
                    self.in_tbody = False
                self.depth -= 1
            elif self.in_list_table and tag == "tbody":
                self.in_tbody = False
            elif self.in_list_table and tag == "tr" and self.cur_row is not None:
                # 명령 컬럼의 onclick 을 마지막 셀에 부가
                if self.last_button_onclick:
                    self.cur_row.append(self.last_button_onclick)
                self.rows.append(self.cur_row)
                self.cur_row = None
                self.last_button_onclick = ""
            elif tag == "td" and self.cur_cell is not None and self.cur_row is not None:
                text = " ".join("".join(self.cur_cell).split()).strip()
                self.cur_row.append(text)
                self.cur_cell = None

        def handle_data(self, data):
            if self.cur_cell is not None:
                self.cur_cell.append(data)

        def handle_entityref(self, name):
            if self.cur_cell is not None:
                self.cur_cell.append(" " if name == "nbsp" else f"&{name};")

    p = _ListParser()
    p.feed(html)

    out: list[dict[str, str]] = []
    for row in p.rows:
        # 9 데이터 셀 + (onclick) → 10. 누락된 row 는 skip.
        if len(row) < 9:
            continue
        draft, vtype, reason, period, days, regd, name, status, *_rest = row
        onclick = row[-1] if len(row) >= 10 else ""
        # 기간: "2026-12-31 ~ 2026-12-31" → from / to 분리
        m = _re.match(r"\s*(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})", period)
        from_date, to_date = (m.group(1), m.group(2)) if m else (period, "")
        # onclick: goSubmit('detail','35115','detail') → 35115 추출
        vid_m = _re.search(r"goSubmit\([^,]+,\s*['\"](\d+)['\"]", onclick)
        out.append(
            {
                "draft_date": draft,
                "vacation_type": vtype,
                "reason": reason,
                "from_date": from_date,
                "to_date": to_date,
                "days": days,
                "registered_date": regd,
                "name": name,
                "status": status,
                "vacation_id": vid_m.group(1) if vid_m else "",
            }
        )
    return out
