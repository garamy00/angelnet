"""세션 만료 시 자동 재로그인 처리하는 httpx.AsyncClient 얇은 래퍼.

Timesheet Spring 서버의 JSESSIONID 는 짧은 idle 후 만료되지만, 클라이언트가
자체 캐시한 세션(SESSION_TTL=24h) 을 신뢰하면 만료된 쿠키로 호출이 계속
실패한다. 이 래퍼는 응답에서 만료 신호(401/403, 로그인 페이지 리디렉트,
로그인 HTML 본문) 를 감지하면 1회에 한해 재로그인 후 동일 요청을 재시도한다.

재진입 방지: 재로그인 자체도 self._http 를 거쳐 가므로, `_refreshing` 플래그가
켜져 있는 동안에는 만료 감지를 건너뛰어 무한 루프를 막는다.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# 현재 task 가 refresh 의 내부 HTTP 호출(예: login.json POST) 진행 중인지.
# ContextVar 는 같은 await 체인(task) 안에서만 전파되어 동시 task 에 영향 없음 —
# refresh 자기 호출만 정확히 식별해 lock·만료 감지 우회 가능.
_in_refresh: ContextVar[bool] = ContextVar("_in_refresh", default=False)

# 마지막 활동 이후 이 초만큼 idle 이면 다음 호출 직전에 사전 재로그인.
# 회사 Spring 서버의 idle session timeout 보다 충분히 짧게 잡아 stale cookie 가
# 회사 API 까지 도달하지 않게 한다. 5분 — 보수적 default.
DEFAULT_IDLE_TIMEOUT = 5 * 60  # 5분

# 세션 만료 시 서버가 보내는 로그인 리디렉트 경로 패턴
_LOGIN_PATH_MARKERS: tuple[str, ...] = ("/home/login", "/home/logout")
# 200 + text/html 응답이 사실은 만료 후 로그인 페이지인 케이스 감지용 marker
_LOGIN_HTML_MARKERS: tuple[str, ...] = ('id="userId"', 'name="userId"')


def is_session_expired(resp: httpx.Response) -> bool:
    """응답이 세션 만료로 보이면 True. 일반 4xx/5xx 와 정상 JSON 은 False."""
    code = resp.status_code
    if code in (401, 403):
        return True
    if 300 <= code < 400:
        loc = resp.headers.get("location", "")
        return any(m in loc for m in _LOGIN_PATH_MARKERS)
    # 200 + HTML 본문이면 만료 후 로그인 페이지일 가능성 확인
    if code == 200:
        ctype = resp.headers.get("content-type", "").lower()
        if "text/html" not in ctype:
            return False
        try:
            body = resp.text
        except (UnicodeDecodeError, httpx.ResponseNotRead):
            return False
        return any(m in body for m in _LOGIN_HTML_MARKERS)
    return False


class AutoReloginHttp:
    """httpx.AsyncClient 의 get/post/delete/request/aclose 만 노출하는 얇은 래퍼.

    응답이 만료로 판단되고 can_refresh() 가 True 면 refresh() 호출 후 동일 요청을
    1회 재시도한다. 한 인스턴스의 refresh 는 asyncio.Lock 으로 직렬화(single-flight)
    되어, 동시 요청들은 진행 중인 refresh 가 끝날 때까지 대기한 뒤 신선한 쿠키로
    출발한다. refresh 자기 자신의 login 호출은 ContextVar _in_refresh 로 식별해
    잠금·만료 감지를 우회한다 (재귀·교착 방지).
    """

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        can_refresh: Callable[[], bool],
        refresh: Callable[[], Awaitable[None]],
        idle_timeout: float = DEFAULT_IDLE_TIMEOUT,
    ) -> None:
        self._http = http
        self._can_refresh = can_refresh
        self._refresh = refresh
        self._idle_timeout = idle_timeout
        # 마지막 활동 시각 — 객체 생성 직후를 시작점으로
        self._last_active = time.time()
        # refresh 직렬화(single-flight) — 한 인스턴스 내 동시 refresh 1개로 제한
        self._refresh_lock = asyncio.Lock()
        # 직전 refresh 완료 시각 — double-check 으로 중복 refresh skip 판단
        self._last_refresh_at = 0.0

    @property
    def cookies(self) -> httpx.Cookies:
        return self._http.cookies

    async def get(self, url: str, **kw: Any) -> httpx.Response:
        return await self._call("GET", url, **kw)

    async def post(self, url: str, **kw: Any) -> httpx.Response:
        return await self._call("POST", url, **kw)

    async def delete(self, url: str, **kw: Any) -> httpx.Response:
        return await self._call("DELETE", url, **kw)

    async def request(self, method: str, url: str, **kw: Any) -> httpx.Response:
        return await self._call(method, url, **kw)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _call(self, method: str, url: str, **kw: Any) -> httpx.Response:
        return await self._call_with_depth(method, url, depth=0, **kw)

    async def _call_with_depth(
        self, method: str, url: str, *, depth: int, **kw: Any
    ) -> httpx.Response:
        # refresh 자기 자신의 HTTP 호출이면 잠금·감지 우회 (재귀·deadlock 방지).
        # ContextVar 는 같은 await 체인 안에서만 전파되므로 동시 task 에 영향 없음.
        if _in_refresh.get():
            return await self._http.request(method, url, **kw)

        # 사전 재로그인 (single-flight, _last_refresh_at capture-compare 로 검사)
        if depth == 0 and self._can_refresh() and self._idle_over():
            refresh_at_entry = self._last_refresh_at
            async with self._refresh_lock:
                if self._last_refresh_at == refresh_at_entry:
                    idle_secs = time.time() - self._last_active
                    logger.info(
                        "Idle %.0fs > timeout %ds — pre-emptive relogin (url=%s)",
                        idle_secs,
                        self._idle_timeout,
                        url,
                    )
                    await self._do_refresh()
        # 다른 task 가 refresh 진행 중이면 끝나길 기다림 (cookie 신선해진 뒤 발사)
        elif self._refresh_lock.locked():
            async with self._refresh_lock:
                pass

        # 사용자 액션 시점 — request 직전. 응답 만료든 정상이든 '활동' 으로 본다.
        self._last_active = time.time()
        resp = await self._http.request(method, url, **kw)
        # password 미보관(첫 로그인 시도 중) 이면 감지 건너뜀
        if not self._can_refresh():
            return resp
        if not is_session_expired(resp):
            return resp
        # 재시도 한도 — refresh 후에도 다시 만료 응답이면 caller 에게 그 응답 전달.
        # depth >= 1 일 때 한 번 더 refresh 시도하지 않아 무한 루프 방지.
        if depth >= 1:
            logger.warning(
                "Session still expired after refresh — giving up (url=%s)", url
            )
            return resp

        # 반응형 재로그인 (single-flight, _last_refresh_at capture-compare).
        # 동시 만료 응답 받은 다른 task 가 이미 refresh 했으면 skip 후 바로 재시도.
        logger.info(
            "Session expired (status=%s url=%s) — re-logging in", resp.status_code, url
        )
        refresh_at_entry = self._last_refresh_at
        async with self._refresh_lock:
            if self._last_refresh_at == refresh_at_entry:
                await self._do_refresh()
        return await self._call_with_depth(method, url, depth=depth + 1, **kw)

    def _idle_over(self) -> bool:
        """마지막 활동 이후 idle_timeout 초과 여부."""
        return (time.time() - self._last_active) > self._idle_timeout

    async def _do_refresh(self) -> None:
        """refresh 콜백을 _in_refresh ContextVar 컨텍스트에서 호출.

        refresh 내부 HTTP 호출이 잠금·감지 분기를 우회하게 한다.
        완료 시각을 _last_refresh_at 에 기록.
        """
        token = _in_refresh.set(True)
        try:
            await self._refresh()
        finally:
            _in_refresh.reset(token)
        self._last_refresh_at = time.time()
