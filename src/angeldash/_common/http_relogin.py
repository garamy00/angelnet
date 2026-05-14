"""세션 만료 시 자동 재로그인 처리하는 httpx.AsyncClient 얇은 래퍼.

Timesheet Spring 서버의 JSESSIONID 는 짧은 idle 후 만료되지만, 클라이언트가
자체 캐시한 세션(SESSION_TTL=24h) 을 신뢰하면 만료된 쿠키로 호출이 계속
실패한다. 이 래퍼는 응답에서 만료 신호(401/403, 로그인 페이지 리디렉트,
로그인 HTML 본문) 를 감지하면 1회에 한해 재로그인 후 동일 요청을 재시도한다.

재진입 방지: 재로그인 자체도 self._http 를 거쳐 가므로, `_refreshing` 플래그가
켜져 있는 동안에는 만료 감지를 건너뛰어 무한 루프를 막는다.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

logger = logging.getLogger(__name__)

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
    1회 재시도한다. refresh 가 자기 자신을 통해 새 login 호출을 보낼 수 있도록
    _refreshing 플래그로 감지를 일시 정지한다.
    """

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        can_refresh: Callable[[], bool],
        refresh: Callable[[], Awaitable[None]],
    ) -> None:
        self._http = http
        self._can_refresh = can_refresh
        self._refresh = refresh
        self._refreshing = False

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
        resp = await self._http.request(method, url, **kw)
        # refresh 진행 중이거나 password 미보관(첫 로그인 시도 중) 이면 감지 건너뜀
        if self._refreshing or not self._can_refresh():
            return resp
        if not is_session_expired(resp):
            return resp
        # 재시도 한도 — refresh 후에도 다시 만료 응답이면 caller 에게 그 응답 전달.
        # depth >= 1 일 때 한 번 더 refresh 시도하지 않아 무한 루프 방지.
        if depth >= 1:
            logger.warning(
                "Session still expired after refresh — giving up (url=%s)", url,
            )
            return resp
        logger.info(
            "Session expired (status=%s url=%s) — re-logging in",
            resp.status_code, url,
        )
        self._refreshing = True
        try:
            await self._refresh()
        finally:
            self._refreshing = False
        return await self._call_with_depth(method, url, depth=depth + 1, **kw)
