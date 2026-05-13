"""server 라우터 단위 테스트 (TestClient + 의존성 오버라이드)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from angeldash._common.errors import ApiError, AuthError, BotBlockedError
from angeldash._common.models import User
from angeldash.models import Reservation
from angeldash.rooms.client import AngelNetClient
from angeldash.server import build_app, get_client, get_password

SAMPLE_RES = {
    "id": "28",
    "creator_name": "Alice",
    "room_id": "14",
    "room": "12층 4번 회의실",
    "date": "2025-04-01",
    "time": "00:00:00",
    "duration": 1440,
    "is_all_day": True,
    "is_repeat": False,
    "weekdays": 4,
    "reason": "x",
    "end_date": None,
}


@pytest.fixture
def app_client():
    fake = MagicMock(spec=AngelNetClient)
    fake.user_id = "testuser"
    fake.login = AsyncMock(
        return_value=User(user_id="testuser", name="Test User", email="x@y")
    )
    fake.list_reservations = AsyncMock(
        return_value=[Reservation.model_validate(SAMPLE_RES)]
    )
    fake.create_reservation = AsyncMock(return_value=999)
    fake.delete_reservation = AsyncMock(return_value=None)
    fake.send_event_email = AsyncMock(return_value=None)
    fake.close = AsyncMock(return_value=None)

    app = build_app(user_id="testuser")
    app.dependency_overrides[get_client] = lambda: fake
    app.dependency_overrides[get_password] = lambda: "pwd"
    # TestClient 를 with 블록 없이 사용해 lifespan 을 트리거하지 않는다
    # (with 시 keychain/env 접근을 시도해 테스트 환경에서 실패함)
    return TestClient(app), fake


def test_me_returns_user(app_client):
    client, _ = app_client
    r = client.get("/api/me")
    assert r.status_code == 200
    data = r.json()
    assert data["user_id"] == "testuser"
    assert data["name"] == "Test User"


def test_rooms_returns_full_list(app_client):
    client, _ = app_client
    r = client.get("/api/rooms")
    assert r.status_code == 200
    rooms = r.json()
    assert len(rooms) == 14
    assert any(room["floor"] == 8 for room in rooms)


def test_rooms_filtered_by_floor(app_client):
    client, _ = app_client
    r = client.get("/api/rooms?floor=8")
    assert r.status_code == 200
    rooms = r.json()
    assert {room["floor"] for room in rooms} == {8}
    assert len(rooms) == 6


def test_static_index_served_at_root(app_client):
    client, _ = app_client
    r = client.get("/")
    assert r.status_code == 200
    assert "AngelNet" in r.text or r.headers["content-type"].startswith("text/html")


def test_get_reservations_returns_list(app_client):
    client, fake = app_client
    r = client.get("/api/reservations?start=2026-05-01&end=2026-08-01")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["id"] == "28"
    fake.list_reservations.assert_awaited_once_with(
        "2026-05-01", "2026-08-01", room_id=None
    )


def test_get_reservations_with_room_id(app_client):
    client, fake = app_client
    r = client.get("/api/reservations?start=2026-05-01&end=2026-08-01&room_id=11")
    assert r.status_code == 200
    fake.list_reservations.assert_awaited_once_with(
        "2026-05-01", "2026-08-01", room_id="11"
    )


def test_post_reservations_creates_without_email(app_client):
    """서버는 직접 이메일을 보내지 않는다 (AngelNet Spring 서버가 자동 발송)."""
    client, fake = app_client
    payload = {
        "date": "2026-06-01",
        "time": "14:00:00",
        "duration": 60,
        "room_id": "11",
        "reason": "테스트",
        "participants": 3,
    }
    r = client.post("/api/reservations", json=payload)
    assert r.status_code == 201
    assert r.json() == {"id": 999}
    fake.create_reservation.assert_awaited_once()
    fake.send_event_email.assert_not_awaited()


def test_post_reservations_validation_error(app_client):
    client, _ = app_client
    payload = {
        "date": "2026-06-01",
        "time": "14:00",
        "duration": 60,
        "room_id": "11",
        "reason": "x",
        "participants": 3,
    }
    r = client.post("/api/reservations", json=payload)
    assert r.status_code == 422


def test_delete_reservation(app_client):
    client, fake = app_client
    r = client.delete("/api/reservations/999?event_date=2026-06-01")
    assert r.status_code == 204
    fake.delete_reservation.assert_awaited_once_with(
        "pwd", event_id=999, event_date="2026-06-01"
    )


def test_delete_reservation_invalid_event_date_returns_422(app_client):
    client, _ = app_client
    r = client.delete("/api/reservations/999?event_date=2026-13-01")
    assert r.status_code == 422


def test_bot_blocked_maps_to_429(app_client):
    client, fake = app_client
    fake.list_reservations.side_effect = BotBlockedError("blocked")
    r = client.get("/api/reservations?start=2026-05-01&end=2026-08-01")
    assert r.status_code == 429
    body = r.json()
    assert body["error"] == "bot_blocked"


def test_auth_error_maps_to_401(app_client):
    client, fake = app_client
    fake.list_reservations.side_effect = AuthError("token gone")
    r = client.get("/api/reservations?start=2026-05-01&end=2026-08-01")
    assert r.status_code == 401
    body = r.json()
    assert "Keychain" in body["hint"]


def test_api_error_uses_carried_status(app_client):
    client, fake = app_client
    fake.list_reservations.side_effect = ApiError(
        "bad", status_code=502, payload={"x": 1}
    )
    r = client.get("/api/reservations?start=2026-05-01&end=2026-08-01")
    assert r.status_code == 502


def test_angelnet_generic_error_maps_to_500(app_client):
    from angeldash._common.errors import AngelNetError

    client, fake = app_client
    fake.list_reservations.side_effect = AngelNetError("unknown")
    r = client.get("/api/reservations?start=2026-05-01&end=2026-08-01")
    assert r.status_code == 500
    body = r.json()
    assert body["error"] == "angelnet"
