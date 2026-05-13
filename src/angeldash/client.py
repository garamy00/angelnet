"""AngelNet 호출 캡슐화 — Spring REST (Boan PHP/GraphQL 흐름 제거 후)."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Literal
from urllib.parse import urlencode

import httpx

from ._http_relogin import AutoReloginHttp
from .errors import AngelNetError, ApiError, AuthError, BotBlockedError
from .models import Reservation, ReservationCreate, User

logger = logging.getLogger(__name__)

# Timesheet 인증
TS_LOGIN = "https://timesheet.uangel.com/home/login.json"
TS_REDIRECT_PATH = "/times/application/meeting_room/search.htm"
TS_REDIRECT_PARAMS = {"pid": "105"}

# Spring REST base
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


class AngelNetClient:
    """AngelNet 의 Spring REST 엔드포인트를 캡슐화.

    인증: Timesheet `POST /home/login.json` 으로 받은 JSESSIONID 쿠키를
    httpx.AsyncClient 가 자동 보관하여 모든 후속 호출에 자동 포함.
    Boan PHP / boan:4000 GraphQL / Boan SSO 흐름은 모두 제거됨.
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
        """HTTP 클라이언트를 닫는다."""
        await self._http.aclose()

    async def _refresh_session(self) -> None:
        """만료 감지 시 호출되는 재로그인 훅. 캐시 무효화 후 login 재실행."""
        if self._password is None:
            raise AuthError("cannot refresh session without cached password")
        self._session_ready = False
        self._session_expires = 0.0
        self._user = None
        await self.login(self._password)

    # ─── 인증 ────────────────────────────────────────────

    async def login(self, password: str) -> User:
        """Timesheet 로그인 후 current-user 호출하여 User 반환.

        캐시된 세션이 살아있으면 HTTP 호출 없이 캐시를 반환한다.
        """
        if self._user and self._session_ready and time.time() < self._session_expires:
            return self._user

        # Timesheet form login (cookies 자동 보관)
        rq = urlencode(TS_REDIRECT_PARAMS)
        resp = await self._http.post(
            TS_LOGIN,
            data={
                "userId": self.user_id,
                "password": password,
                "redirectUrl": f"{TS_REDIRECT_PATH}?{rq}",
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

        # name 은 별도 endpoint. 실패는 fatal 아님 (userId 로 fallback)
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

        self._user = User(
            user_id=cu_body["userId"],
            name=name,
            email=None,
        )
        self._session_ready = True
        self._session_expires = time.time() + SESSION_TTL
        # 성공한 password 만 캐시 → 첫 로그인 실패는 자동 재시도 트리거하지 않음.
        self._password = password
        logger.info("Spring session established for user=%s", self.user_id)
        return self._user

    # ─── 예약 조회 ───────────────────────────────────────

    async def list_reservations(
        self,
        start_date: str,
        end_date: str,
        room_id: str | None = None,
    ) -> list[Reservation]:
        """기간 내 예약 조회 (Spring). room_id 는 클라이언트 측 필터."""
        params = {"start": start_date, "end": end_date}
        resp = await self._http.get(f"{SPRING_BASE}/reservations", params=params)
        body = self._safe_json(resp, exc_type=ApiError)

        if _is_bot_blocked(body):
            raise BotBlockedError(body.get("error") or body.get("message"))
        if resp.status_code >= 500:
            raise ApiError(
                f"server error on list_reservations: status={resp.status_code}",
                status_code=resp.status_code,
                payload=body,
            )
        if resp.status_code >= 400:
            raise ApiError(
                "list_reservations failed",
                status_code=resp.status_code,
                payload=body,
            )

        rows = (body.get("data") if isinstance(body, dict) else None) or []
        results = [Reservation.from_spring(r) for r in rows]
        if room_id is not None:
            results = [r for r in results if r.room_id == str(room_id)]
        return results

    # ─── 예약 생성 ───────────────────────────────────────

    async def create_reservation(
        self, password: str, payload: ReservationCreate
    ) -> int:
        """예약 생성 후 event id 반환. password 는 호환성 위해 받지만 세션 쿠키 사용."""
        del password  # 세션 쿠키 사용 — 추가 인증 불필요
        body = self._to_spring_create_payload(payload)
        resp = await self._http.post(f"{SPRING_BASE}/reservations", json=body)
        data = self._safe_json(resp, exc_type=ApiError)

        if not (isinstance(data, dict) and data.get("success")):
            msg = data.get("message") if isinstance(data, dict) else str(data)
            raise ApiError(
                f"reserve failed: {msg}",
                status_code=resp.status_code,
                payload=data,
            )

        # 응답 형식: {"success":True,"data":{"id":...}} 또는 {"success":True,"id":...}
        nested = data.get("data") if isinstance(data.get("data"), dict) else None
        rid = (nested or {}).get("id") if nested else data.get("id")
        if rid is None:
            raise ApiError(
                "reserve response missing id",
                status_code=resp.status_code,
                payload=data,
            )
        return int(rid)

    # ─── 예약 삭제 ───────────────────────────────────────

    async def delete_reservation(
        self, password: str, *, event_id: int, event_date: str
    ) -> None:
        """예약 삭제 — Spring API 는 path id 만 사용."""
        del password, event_date
        resp = await self._http.delete(f"{SPRING_BASE}/reservations/{event_id}")
        data = self._safe_json(resp, exc_type=ApiError)
        if not (isinstance(data, dict) and data.get("success")):
            msg = data.get("message") if isinstance(data, dict) else str(data)
            raise ApiError(
                f"delete failed: {msg}",
                status_code=resp.status_code,
                payload=data,
            )

    # ─── 이메일 (fire-and-forget) ────────────────────────

    async def send_event_email(
        self,
        *,
        event_id: int,
        payload: ReservationCreate,
        room_name: str,
        event_type: Literal["create", "delete"],
        creator_name: str,
    ) -> None:
        """예약/취소 이메일 발송. 실패해도 예외를 올리지 않는다."""
        end_time = self._hhmmss_plus_minutes(payload.time, payload.duration)
        hours = payload.duration // 60
        if event_type == "create":
            subject = f"[AngelNet] 회의실: {room_name} 예약 등록 - {payload.reason}"
            intro = "새로운 회의실 예약 등록"
            extra = ""
            id_line = ""
        else:
            subject = (
                f"[AngelNet] 회의실: {room_name} 예약 취소 "
                f"- [{creator_name}] {payload.reason}"
            )
            intro = "회의실 예약 취소"
            extra = "회의실 예약이 취소되었습니다.<br/><br/>"
            id_line = f"<br/>예약ID  : {event_id}"

        html_body = (
            f"{intro}<br/><br/>안녕하세요, {creator_name}님<br/><br/>"
            f"{extra}"
            f"예약 제목 : {payload.reason}<br/>회의실   : {room_name}<br/>"
            f"날짜     : {payload.date}<br/>"
            f"시간     : {payload.time} ~ {end_time} ({hours}시간)<br/>"
            f"예약자   : {creator_name}<br/>"
            f"참석자   : {payload.participants}명"
            f"{id_line}"
        )
        spring_body = {
            "recipients": [self.user_id],
            "subject": subject,
            "htmlBody": html_body,
            "eventType": event_type,
        }
        try:
            await self._http.post(
                f"{SPRING_BASE}/meeting-rooms/send-email", json=spring_body
            )
        except httpx.HTTPError as exc:
            logger.warning("Email send failed (non-fatal): %s", exc)

    # ─── 내부 헬퍼 ──────────────────────────────────────

    def _to_spring_create_payload(self, p: ReservationCreate) -> dict:
        """ReservationCreate → Spring POST body (JS 분석 결과 반영)."""
        end_time = self._hhmmss_plus_minutes(p.time, p.duration)
        # 본 도구는 참석자 수만 받음 — Spring 의 participants 는 JSON 배열 string 필요
        # 빈 배열로 보낸다 (서버가 creator 를 자동 포함하리라 기대)
        return {
            "id": None,
            "roomId": int(p.room_id),
            "date": p.date,
            "time": p.time,
            "endTime": end_time,
            "duration": p.duration,
            "reason": p.reason,
            "participants": json.dumps([]),
            "isAllDay": False,
            "isRepeat": False,
            "weekdays": 0,
            "repetitionPeriod": None,
            "endDate": None,
            "pushNotification": False,
            "creatorId": self.user_id,
            "creatorName": self._user.name if self._user else self.user_id,
        }

    @staticmethod
    def _hhmmss_plus_minutes(start: str, minutes: int) -> str:
        """HH:MM:SS 시작 시각에 분(minutes)을 더해 HH:MM:SS 종료 시각 반환."""
        h, m, s = (int(x) for x in start.split(":"))
        total = h * 3600 + m * 60 + s + minutes * 60
        end_h, rem = divmod(total, 3600)
        end_m, end_s = divmod(rem, 60)
        if end_h >= 24:
            raise ValueError(
                f"reservation end time crosses midnight:"
                f" start={start} duration={minutes}"
            )
        return f"{end_h:02d}:{end_m:02d}:{end_s:02d}"

    @staticmethod
    def _safe_json(
        resp: httpx.Response,
        exc_type: type[AngelNetError] = AuthError,
    ) -> Any:
        """JSON 파싱 실패 시 지정 도메인 예외(기본 AuthError)로 변환."""
        try:
            return resp.json()
        except ValueError as exc:
            if exc_type is ApiError:
                raise ApiError(
                    f"non-json response: status={resp.status_code}",
                    status_code=resp.status_code,
                ) from exc
            raise exc_type(f"non-json response: status={resp.status_code}") from exc
