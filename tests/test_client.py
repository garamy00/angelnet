"""AngelNetClient (Spring REST) 단위 테스트 (httpx mock)."""

import json

import httpx
import pytest

from angeldash._common.errors import ApiError, AuthError, BotBlockedError
from angeldash.models import Reservation, ReservationCreate

PAYLOAD = ReservationCreate(
    date="2026-06-01",
    time="14:00:00",
    duration=60,
    room_id="11",
    reason="테스트 회의",
    participants=3,
)


SAMPLE_SPRING_RES = {
    "id": 27,
    "originalId": None,
    "roomId": 13,
    "room": "12층 3번 회의실",
    "date": 1743433200000,
    "time": "00:00:00",
    "duration": 1440,
    "isAllDay": 1,
    "isRepeat": 0,
    "repetitionPeriod": "weekly",
    "weekdays": 8,
    "endDate": 1806418800000,
    "reason": "KT 기가지니",
    "createdAt": 1743476408000,
    "creatorId": "thehighwind",
    "creatorName": "Alice",
}


CURRENT_USER_RESP = {
    "groupName": "USER",
    "success": True,
    "groupId": 4,
    "isAdmin": False,
    "userId": "testuser",
}


# ─── login (Timesheet + current-user) ───────────────────────


async def _setup_login_mocks(mock_router):
    mock_router.post("https://timesheet.uangel.com/home/login.json").respond(
        status_code=200,
        json={"redirectUrl": "/times/...", "success": True},
        headers={"set-cookie": "JSESSIONID=abc; Path=/; Secure; HttpOnly"},
    )
    mock_router.get(
        "https://timesheet.uangel.com/times/application/meeting_room/api/meeting-rooms/current-user"
    ).respond(json=CURRENT_USER_RESP)
    # user-name endpoint: 헬퍼 기반 테스트에선 userId 로 fallback (500 응답)
    mock_router.get(
        "https://timesheet.uangel.com/times/application/meeting_room/api/meeting-rooms/user-name",
    ).respond(status_code=500)


async def test_login_posts_to_timesheet_and_caches_session(mock_router, client):
    await _setup_login_mocks(mock_router)
    user = await client.login("pwd")
    assert user.user_id == "testuser"

    # 두 번째 호출은 캐시 hit — login.json 추가 호출 없음
    await client.login("pwd")
    paths = [str(c.request.url.path) for c in mock_router.calls]
    assert paths.count("/home/login.json") == 1


async def test_login_failure_raises_auth_error(mock_router, client):
    mock_router.post("https://timesheet.uangel.com/home/login.json").respond(
        status_code=401, json={"success": False, "message": "invalid"}
    )
    with pytest.raises(AuthError):
        await client.login("pwd")


async def test_login_5xx_raises_api_error(mock_router, client):
    mock_router.post("https://timesheet.uangel.com/home/login.json").respond(
        status_code=503, json={"err": "down"}
    )
    with pytest.raises(ApiError) as exc:
        await client.login("pwd")
    assert exc.value.status_code == 503


# ─── list_reservations ──────────────────────────────────────


async def _logged_in(mock_router, client):
    await _setup_login_mocks(mock_router)
    await client.login("pwd")


async def test_list_reservations_unwraps_data_and_normalizes(mock_router, client):
    await _logged_in(mock_router, client)
    mock_router.get(
        "https://timesheet.uangel.com/times/application/meeting_room/api/reservations",
        params__contains={"start": "2026-05-01", "end": "2026-08-01"},
    ).respond(json={"data": [SAMPLE_SPRING_RES], "success": True, "message": ""})

    items = await client.list_reservations("2026-05-01", "2026-08-01")
    assert len(items) == 1
    assert isinstance(items[0], Reservation)
    assert items[0].id == "27"
    assert items[0].room_id == "13"
    assert items[0].creator_id == "thehighwind"
    assert items[0].is_all_day is True


async def test_list_reservations_5xx_raises_api_error(mock_router, client):
    await _logged_in(mock_router, client)
    mock_router.get(
        "https://timesheet.uangel.com/times/application/meeting_room/api/reservations",
        params__contains={"start": "2026-05-01"},
    ).respond(status_code=502)
    with pytest.raises(ApiError) as exc:
        await client.list_reservations("2026-05-01", "2026-08-01")
    assert exc.value.status_code == 502


async def test_list_reservations_bot_blocked(mock_router, client):
    await _logged_in(mock_router, client)
    mock_router.get(
        "https://timesheet.uangel.com/times/application/meeting_room/api/reservations",
    ).respond(
        json={
            "error": (
                "Automated requests are not allowed for this user or token is invalid"
            )
        }
    )
    with pytest.raises(BotBlockedError):
        await client.list_reservations("2026-05-01", "2026-08-01")


# ─── create_reservation ─────────────────────────────────────


async def test_create_reservation_sends_correct_spring_payload(mock_router, client):
    await _logged_in(mock_router, client)
    captured = {}

    def _capture(req: httpx.Request):
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={"success": True, "data": {"id": 9999}})

    mock_router.post(
        "https://timesheet.uangel.com/times/application/meeting_room/api/reservations",
    ).mock(side_effect=_capture)

    event_id = await client.create_reservation("pwd", PAYLOAD)
    assert event_id == 9999
    body = captured["body"]
    # camelCase + 타입 정규화 검증 (Task 1 JS 조사 결과 반영)
    assert body["roomId"] == 11  # int
    assert body["date"] == "2026-06-01"  # ISO string
    assert body["time"] == "14:00:00"
    assert body["endTime"] == "15:00:00"
    assert body["duration"] == 60
    assert body["reason"] == "테스트 회의"
    assert body["isAllDay"] is False  # boolean
    assert body["isRepeat"] is False
    assert body["weekdays"] == 0
    assert body["repetitionPeriod"] is None
    assert body["endDate"] is None
    assert body["pushNotification"] is False
    assert body["id"] is None
    # participants 는 JSON string "[]" (빈 배열)
    assert body["participants"] == "[]"
    # creator 정보 inject
    assert body["creatorId"] == "testuser"
    assert body["creatorName"] == "testuser"  # User.name = userId (fallback)


async def test_create_reservation_conflict_raises_api_error(mock_router, client):
    await _logged_in(mock_router, client)
    mock_router.post(
        "https://timesheet.uangel.com/times/application/meeting_room/api/reservations",
    ).respond(json={"success": False, "conflict": True, "message": "이미 예약됨"})
    with pytest.raises(ApiError, match="이미 예약"):
        await client.create_reservation("pwd", PAYLOAD)


async def test_create_reservation_accepts_id_at_top_level(mock_router, client):
    """일부 응답이 data wrapper 없이 {success, id} 형태일 수도 — 둘 다 지원."""
    await _logged_in(mock_router, client)
    mock_router.post(
        "https://timesheet.uangel.com/times/application/meeting_room/api/reservations",
    ).respond(json={"success": True, "id": 5555})
    event_id = await client.create_reservation("pwd", PAYLOAD)
    assert event_id == 5555


# ─── delete_reservation ─────────────────────────────────────


async def test_delete_reservation_calls_spring_delete(mock_router, client):
    await _logged_in(mock_router, client)
    mock_router.delete(
        "https://timesheet.uangel.com/times/application/meeting_room/api/reservations/9999",
    ).respond(json={"success": True})
    await client.delete_reservation("pwd", event_id=9999, event_date="2026-06-01")


async def test_delete_reservation_failure_raises_api_error(mock_router, client):
    await _logged_in(mock_router, client)
    mock_router.delete(
        "https://timesheet.uangel.com/times/application/meeting_room/api/reservations/9999",
    ).respond(json={"success": False, "message": "권한 없음"})
    with pytest.raises(ApiError, match="권한"):
        await client.delete_reservation("pwd", event_id=9999, event_date="2026-06-01")


# ─── send_event_email ──────────────────────────────────────


async def test_send_email_does_not_raise_on_5xx(mock_router, client):
    await _logged_in(mock_router, client)
    mock_router.post(
        "https://timesheet.uangel.com/times/application/meeting_room/api/meeting-rooms/send-email",
    ).respond(status_code=502)
    await client.send_event_email(
        event_id=1234,
        payload=PAYLOAD,
        room_name="8층 3번 LAB",
        event_type="create",
        creator_name="Test User",
    )


async def test_send_email_subject_and_body_for_create(mock_router, client):
    await _logged_in(mock_router, client)
    captured = {}

    def _capture(req):
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={"success": True})

    mock_router.post(
        "https://timesheet.uangel.com/times/application/meeting_room/api/meeting-rooms/send-email",
    ).mock(side_effect=_capture)

    await client.send_event_email(
        event_id=1234,
        payload=PAYLOAD,
        room_name="8층 3번 LAB",
        event_type="create",
        creator_name="Test User",
    )

    body = captured["body"]
    assert body["recipients"] == ["testuser"]
    assert body["eventType"] == "create"
    assert "예약 등록" in body["subject"]
    assert "테스트 회의" in body["htmlBody"]


# ─── _hhmmss_plus_minutes 헬퍼 ─────────────────────────────


async def test_hhmmss_plus_minutes_rejects_midnight_overflow():
    from angeldash.rooms.client import AngelNetClient as AC

    with pytest.raises(ValueError, match="crosses midnight"):
        AC._hhmmss_plus_minutes("23:00:00", 120)


# ─── login current-user 5xx 회귀 테스트 ────────────────────


async def test_login_current_user_5xx_raises_api_error(mock_router, client):
    mock_router.post("https://timesheet.uangel.com/home/login.json").respond(
        status_code=200,
        json={"success": True},
        headers={"set-cookie": "JSESSIONID=abc; Path=/"},
    )
    mock_router.get(
        "https://timesheet.uangel.com/times/application/meeting_room/api/meeting-rooms/current-user"
    ).respond(status_code=503, json={"err": "down"})

    with pytest.raises(ApiError) as exc:
        await client.login("pwd")
    assert exc.value.status_code == 503


async def test_login_fetches_user_name_endpoint(mock_router, client):
    """login 이 user-name endpoint 까지 호출해 name 을 채운다."""
    mock_router.post("https://timesheet.uangel.com/home/login.json").respond(
        status_code=200,
        json={"success": True},
        headers={"set-cookie": "JSESSIONID=abc; Path=/"},
    )
    mock_router.get(
        "https://timesheet.uangel.com/times/application/meeting_room/api/meeting-rooms/current-user"
    ).respond(json=CURRENT_USER_RESP)
    mock_router.get(
        "https://timesheet.uangel.com/times/application/meeting_room/api/meeting-rooms/user-name",
        params__contains={"userId": "testuser"},
    ).respond(json={"success": True, "name": "Test User"})

    user = await client.login("pwd")
    assert user.name == "Test User"


# ─── 자동 재로그인 (세션 만료 감지) ──────────────────────────


async def test_api_call_auto_relogins_on_session_expired(mock_router, client):
    """로그인 성공 후 API 호출이 401 을 받으면 자동 재로그인 + 재시도한다.

    회사 Timesheet 세션(JSESSIONID) 이 idle 만료된 케이스. 클라이언트가 캐시한
    SESSION_TTL 가 살아있어도, 응답이 만료 신호면 1회에 한해 재로그인 후 재시도.
    """
    await _setup_login_mocks(mock_router)
    await client.login("pwd")

    # 첫 호출: 401 (세션 만료), 두 번째 호출: 정상 응답
    mock_router.get(
        "https://timesheet.uangel.com/times/application/meeting_room/api/reservations",
    ).mock(
        side_effect=[
            httpx.Response(401, json={"error": "session expired"}),
            httpx.Response(200, json={"data": [SAMPLE_SPRING_RES], "success": True}),
        ]
    )

    items = await client.list_reservations("2026-05-01", "2026-08-01")
    assert len(items) == 1
    assert items[0].id == "27"

    # login.json 이 자동 재로그인으로 한 번 더 호출됐는지 (초기 1 + 재로그인 1 = 2)
    login_paths = [
        c.request.url.path
        for c in mock_router.calls
        if c.request.url.path == "/home/login.json"
    ]
    assert len(login_paths) == 2


async def test_login_4xx_does_not_trigger_relogin_loop(mock_router, client):
    """최초 로그인 실패는 자동 재로그인 트리거 없이 즉시 AuthError 로 surface.

    password 캐시는 로그인 성공 후에만 채워지므로, 첫 시도가 401 이면 재시도
    하지 않고 한 번만 실패해야 한다.
    """
    mock_router.post("https://timesheet.uangel.com/home/login.json").respond(
        status_code=401, json={"success": False, "message": "invalid"}
    )
    with pytest.raises(AuthError):
        await client.login("badpwd")
    # 정확히 한 번만 호출 (재시도 없음)
    login_calls = [
        c for c in mock_router.calls if c.request.url.path == "/home/login.json"
    ]
    assert len(login_calls) == 1


async def test_login_user_name_failure_falls_back_to_user_id(mock_router, client):
    """user-name endpoint 실패해도 login 자체는 성공 (name=user_id fallback)."""
    mock_router.post("https://timesheet.uangel.com/home/login.json").respond(
        status_code=200,
        json={"success": True},
        headers={"set-cookie": "JSESSIONID=abc; Path=/"},
    )
    mock_router.get(
        "https://timesheet.uangel.com/times/application/meeting_room/api/meeting-rooms/current-user"
    ).respond(json=CURRENT_USER_RESP)
    mock_router.get(
        "https://timesheet.uangel.com/times/application/meeting_room/api/meeting-rooms/user-name",
    ).respond(status_code=500)

    user = await client.login("pwd")
    assert user.name == "testuser"  # fallback
