"""AutoReloginHttp 의 만료 감지 + 재시도 동작 단위 테스트.

httpx mock 으로 응답 시퀀스를 제어해서 재로그인 1회 동작과 무한 루프 방지를 검증.
"""

from __future__ import annotations

import time

import httpx
import pytest

from angeldash._common.http_relogin import AutoReloginHttp, is_session_expired


def _make_resp(status: int = 200, text: str = "OK", **kw) -> httpx.Response:
    """httpx.Response 빠른 생성."""
    return httpx.Response(status_code=status, text=text, **kw)


class _ScriptedHttp:
    """request 호출에 미리 정의한 응답 시퀀스를 순서대로 반환하는 fake."""

    def __init__(self, responses: list[httpx.Response]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    async def request(self, method: str, url: str, **_kw) -> httpx.Response:
        self.calls.append((method, url))
        if not self._responses:
            raise AssertionError("No more scripted responses")
        return self._responses.pop(0)

    async def aclose(self) -> None:
        pass


def test_is_session_expired_detects_401():
    assert is_session_expired(_make_resp(401))


def test_is_session_expired_detects_login_redirect():
    resp = _make_resp(302, headers={"location": "/home/login.jsp"})
    assert is_session_expired(resp)


def test_is_session_expired_detects_html_login_page():
    resp = _make_resp(
        200, text='<html><input id="userId"></html>',
        headers={"content-type": "text/html"},
    )
    assert is_session_expired(resp)


def test_is_session_expired_ignores_normal_200_json():
    resp = _make_resp(
        200, text='{"ok": true}',
        headers={"content-type": "application/json"},
    )
    assert not is_session_expired(resp)


@pytest.mark.anyio
async def test_auto_relogin_retries_once_on_first_expiry():
    """첫 요청이 401 → refresh → 재시도 → 200 OK 가 정상 반환된다."""
    refresh_calls = 0

    async def refresh():
        nonlocal refresh_calls
        refresh_calls += 1

    scripted = _ScriptedHttp([
        _make_resp(401, text=""),    # 첫 호출 — 만료
        _make_resp(200, text="OK"),  # refresh 후 재시도 — 성공
    ])
    wrapper = AutoReloginHttp(
        scripted, can_refresh=lambda: True, refresh=refresh,
    )
    resp = await wrapper.get("https://example/api")
    assert resp.status_code == 200
    assert refresh_calls == 1
    assert len(scripted.calls) == 2


@pytest.mark.anyio
async def test_auto_relogin_does_not_loop_when_refresh_also_expires():
    """refresh 후 두 번째 응답도 만료면 — 더 재시도하지 않고 caller 에게 전달.

    무한 루프 방어. depth 가드.
    """
    refresh_calls = 0

    async def refresh():
        nonlocal refresh_calls
        refresh_calls += 1

    scripted = _ScriptedHttp([
        _make_resp(401),    # 첫 호출
        _make_resp(401),    # refresh 후도 만료 — depth 가드로 caller 에 그대로 반환
    ])
    wrapper = AutoReloginHttp(
        scripted, can_refresh=lambda: True, refresh=refresh,
    )
    resp = await wrapper.get("https://example/api")
    # depth>=1 에서 또 만료 감지해도 추가 refresh 안 함 → 두 번째 401 그대로
    assert resp.status_code == 401
    assert refresh_calls == 1  # 정확히 1번만
    assert len(scripted.calls) == 2  # 첫 호출 + 재시도 1번


@pytest.mark.anyio
async def test_auto_relogin_preemptive_refresh_when_idle_exceeds_timeout(
    monkeypatch,
):
    """idle 시간이 idle_timeout 을 초과하면 응답 받기 전에 사전 재로그인."""
    refresh_calls = 0

    async def refresh():
        nonlocal refresh_calls
        refresh_calls += 1

    scripted = _ScriptedHttp([_make_resp(200, text="OK")])
    wrapper = AutoReloginHttp(
        scripted, can_refresh=lambda: True, refresh=refresh,
        idle_timeout=60,  # 60초
    )

    # _last_active 를 70초 전으로 강제 — idle 70s > timeout 60s
    wrapper._last_active = time.time() - 70

    # time.time() 은 mock 안 함 — 실제 진행. 호출 직전 idle 검사가 true
    resp = await wrapper.get("https://example/api")
    assert resp.status_code == 200
    # 사전 refresh 1회 발동
    assert refresh_calls == 1


@pytest.mark.anyio
async def test_auto_relogin_skips_preemptive_when_idle_under_timeout():
    """idle 이 timeout 보다 짧으면 사전 재로그인 안 함."""
    refresh_calls = 0

    async def refresh():
        nonlocal refresh_calls
        refresh_calls += 1

    scripted = _ScriptedHttp([_make_resp(200, text="OK")])
    wrapper = AutoReloginHttp(
        scripted, can_refresh=lambda: True, refresh=refresh,
        idle_timeout=60,
    )
    # 방금 생성된 wrapper — idle 0초, timeout 60초

    resp = await wrapper.get("https://example/api")
    assert resp.status_code == 200
    assert refresh_calls == 0  # 사전 refresh 없음


@pytest.mark.anyio
async def test_auto_relogin_updates_last_active_each_call():
    """매 호출마다 _last_active 가 갱신되어 다음 호출의 idle 측정 기준이 된다."""
    scripted = _ScriptedHttp([
        _make_resp(200, text="OK"),
        _make_resp(200, text="OK"),
    ])

    async def refresh():
        pass

    wrapper = AutoReloginHttp(
        scripted, can_refresh=lambda: True, refresh=refresh,
        idle_timeout=60,
    )
    first = wrapper._last_active
    # 짧은 sleep 으로 시간 진행
    import asyncio
    await asyncio.sleep(0.05)
    await wrapper.get("https://example/api")
    second = wrapper._last_active
    assert second > first  # 첫 호출 후 갱신


@pytest.mark.anyio
async def test_auto_relogin_skips_when_password_not_cached():
    """can_refresh()=False (첫 로그인 미완료) 면 만료 감지 건너뜀."""
    scripted = _ScriptedHttp([_make_resp(401)])

    async def refresh():
        raise AssertionError("refresh should not be called")

    wrapper = AutoReloginHttp(
        scripted, can_refresh=lambda: False, refresh=refresh,
    )
    resp = await wrapper.get("https://example/api")
    assert resp.status_code == 401
    assert len(scripted.calls) == 1


@pytest.mark.anyio
async def test_concurrent_requests_during_pre_emptive_refresh_share_single_login():
    """idle 초과 상태 동시 N 요청 → refresh 1회, 동시 요청은 refresh 완료까지 대기."""
    import asyncio
    refresh_calls = 0
    refresh_started = asyncio.Event()
    refresh_can_complete = asyncio.Event()

    async def slow_refresh():
        nonlocal refresh_calls
        refresh_calls += 1
        refresh_started.set()
        await refresh_can_complete.wait()

    scripted = _ScriptedHttp([
        _make_resp(200, text="A"),
        _make_resp(200, text="B"),
        _make_resp(200, text="C"),
    ])
    wrapper = AutoReloginHttp(
        scripted, can_refresh=lambda: True, refresh=slow_refresh,
        idle_timeout=60,
    )
    wrapper._last_active = time.time() - 120  # idle 초과 상태

    # A 시작 → refresh 진입 대기
    task_a = asyncio.create_task(wrapper.get("https://example/a"))
    await refresh_started.wait()

    # A 가 refresh 중인 동안 B, C 시작
    task_b = asyncio.create_task(wrapper.get("https://example/b"))
    task_c = asyncio.create_task(wrapper.get("https://example/c"))
    await asyncio.sleep(0.02)  # B, C 가 lock 대기에 진입할 시간

    # 핵심: single-flight 면 B, C 는 lock 에서 대기 중이라 HTTP 요청을 아직 못 함
    # 현재 _refreshing boolean 코드에서는 B, C 가 stale 쿠키로 이미 발사됨 → assert 실패
    assert len(scripted.calls) == 0, (
        f"refresh 중에 동시 요청이 stale 쿠키로 발사됨 (calls={scripted.calls})"
    )

    refresh_can_complete.set()
    results = await asyncio.gather(task_a, task_b, task_c)
    assert all(r.status_code == 200 for r in results)
    assert refresh_calls == 1
    assert len(scripted.calls) == 3


@pytest.mark.anyio
async def test_concurrent_requests_during_reactive_refresh_wait_for_single_login():
    """첫 요청이 401 받고 refresh 진행 중일 때 도착한 동시 요청은 lock 대기 후 신선한
    쿠키로 발사 — stale 호출 자체가 발생하지 않고 refresh 도 1회만."""
    import asyncio
    refresh_calls = 0
    refresh_started = asyncio.Event()
    refresh_can_complete = asyncio.Event()

    async def slow_refresh():
        nonlocal refresh_calls
        refresh_calls += 1
        refresh_started.set()
        await refresh_can_complete.wait()

    scripted = _ScriptedHttp([
        _make_resp(401),                # A first (stale)
        _make_resp(200, text="A2"),     # A retry (refresh 후, fresh)
        _make_resp(200, text="B"),      # B first (A의 refresh 대기 후, fresh)
        _make_resp(200, text="C"),      # C first (대기 후, fresh)
    ])
    wrapper = AutoReloginHttp(
        scripted, can_refresh=lambda: True, refresh=slow_refresh,
        idle_timeout=10_000,  # idle 트리거 안 함 — 반응형만
    )

    task_a = asyncio.create_task(wrapper.get("https://example/a"))
    await refresh_started.wait()  # A 가 401 받고 refresh 진입

    task_b = asyncio.create_task(wrapper.get("https://example/b"))
    task_c = asyncio.create_task(wrapper.get("https://example/c"))
    await asyncio.sleep(0.02)  # B, C 가 elif wait-for-refresh 에 진입할 시간

    # 핵심: single-flight 면 B, C 는 lock 대기 중이라 HTTP 요청 미발사 (1 = A first 만)
    # 옛 _refreshing boolean 코드는 B, C 가 stale 호출 발사 → calls 가 1 초과
    assert len(scripted.calls) == 1, (
        f"B/C 가 refresh 대기 안 하고 stale 호출 발사 (calls={scripted.calls})"
    )

    refresh_can_complete.set()
    results = await asyncio.gather(task_a, task_b, task_c)
    assert all(r.status_code == 200 for r in results), (
        f"statuses={[r.status_code for r in results]}"
    )
    assert refresh_calls == 1, f"refresh 가 {refresh_calls}회 — single-flight 위반"


@pytest.mark.anyio
async def test_refresh_internal_request_does_not_deadlock():
    """refresh callback 이 wrapper 를 통해 login 호출해도 lock 재진입 deadlock 없음."""
    import asyncio
    refresh_call_count = 0

    scripted = _ScriptedHttp([
        _make_resp(401),  # user GET 첫 호출 — 만료
        _make_resp(  # refresh 내부 login.json POST — 정상 JSON
            200, text='{"ok": true}',
            headers={"content-type": "application/json"},
        ),
        _make_resp(200, text="data"),  # user GET 재시도
    ])
    wrapper_holder: dict = {}

    async def refresh():
        nonlocal refresh_call_count
        refresh_call_count += 1
        # 실제 클라이언트 패턴: refresh 가 자기 자신을 통해 login 호출
        await wrapper_holder["w"].post(
            "https://example/home/login.json",
            json={"userId": "x", "password": "y"},
        )

    wrapper = AutoReloginHttp(
        scripted, can_refresh=lambda: True, refresh=refresh, idle_timeout=10_000,
    )
    wrapper_holder["w"] = wrapper

    # 2초 안에 끝나야 함 — deadlock 이면 타임아웃
    resp = await asyncio.wait_for(
        wrapper.get("https://example/api"), timeout=2.0,
    )
    assert resp.status_code == 200
    assert refresh_call_count == 1
    # 3 calls: 첫 GET, refresh 안의 login POST, GET 재시도
    assert len(scripted.calls) == 3


@pytest.fixture
def anyio_backend():
    return "asyncio"
