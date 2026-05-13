"""Pydantic 모델 단위 테스트."""

import pytest
from pydantic import ValidationError

from angeldash._common.models import User
from angeldash.rooms.models import Reservation, ReservationCreate

SAMPLE_GQL_ROW = {
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
    "reason": "KT 기가지니앱",
    "end_date": "2026-05-31",
}


def test_reservation_parses_graphql_row():
    res = Reservation.model_validate(SAMPLE_GQL_ROW)
    assert res.id == "28"
    assert res.duration == 1440
    assert res.is_all_day is True
    assert res.end_date == "2026-05-31"


def test_reservation_accepts_empty_end_date_as_none():
    row = {**SAMPLE_GQL_ROW, "end_date": ""}
    res = Reservation.model_validate(row)
    assert res.end_date is None


def test_reservation_create_rejects_invalid_duration():
    valid_payload = {
        "date": "2026-06-01",
        "time": "10:00:00",
        "duration": 60,
        "room_id": "11",
        "reason": "테스트 회의",
        "participants": 3,
    }
    ReservationCreate.model_validate(valid_payload)

    with pytest.raises(ValidationError):
        ReservationCreate.model_validate({**valid_payload, "duration": 0})

    with pytest.raises(ValidationError):
        ReservationCreate.model_validate({**valid_payload, "duration": 800})

    # 경계값 성공 케이스
    r1 = ReservationCreate.model_validate({**valid_payload, "duration": 1})
    assert r1.duration == 1
    r720 = ReservationCreate.model_validate({**valid_payload, "duration": 720})
    assert r720.duration == 720


def test_reservation_create_rejects_bad_time_format():
    payload = {
        "date": "2026-06-01",
        "time": "10:00",  # 초 누락
        "duration": 60,
        "room_id": "11",
        "reason": "x",
        "participants": 1,
    }
    with pytest.raises(ValidationError):
        ReservationCreate.model_validate(payload)

    # valid 시간/짧은 reason 통과 케이스
    r = ReservationCreate.model_validate({**payload, "time": "10:00:00"})
    assert r.time == "10:00:00"
    assert r.reason == "x"


def test_reservation_create_rejects_invalid_calendar_date():
    payload = {
        "date": "2026-13-01",  # 13월
        "time": "10:00:00",
        "duration": 60,
        "room_id": "11",
        "reason": "x",
        "participants": 1,
    }
    with pytest.raises(ValidationError):
        ReservationCreate.model_validate(payload)

    payload["date"] = "2026-06-31"  # 6월 31일 없음
    with pytest.raises(ValidationError):
        ReservationCreate.model_validate(payload)


def test_reservation_create_rejects_empty_room_id():
    payload = {
        "date": "2026-06-01",
        "time": "10:00:00",
        "duration": 60,
        "room_id": "",
        "reason": "x",
        "participants": 1,
    }
    with pytest.raises(ValidationError):
        ReservationCreate.model_validate(payload)


def test_user_model_basic():
    user = User(user_id="testuser", name="Test User", email="testuser@example.com")
    assert user.user_id == "testuser"


SAMPLE_SPRING_ROW = {
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
    "creatorName": "Bob",
}


def test_reservation_from_spring_normalizes_camel_to_snake_and_epoch_to_iso():
    res = Reservation.from_spring(SAMPLE_SPRING_ROW)
    assert res.id == "27"
    assert res.room_id == "13"
    assert res.creator_id == "thehighwind"
    assert res.creator_name == "Bob"
    assert res.is_all_day is True
    assert res.is_repeat is False
    # epoch ms 1743433200000 = 2025-04-01 (KST)
    assert res.date == "2025-04-01"
    # epoch 1806418800000 = 2027-04-29 KST 라고 가정 — 실제 변환 결과를 동적으로 확인
    import datetime
    from zoneinfo import ZoneInfo

    expected_end = datetime.datetime.fromtimestamp(
        1806418800000 / 1000, tz=ZoneInfo("Asia/Seoul")
    ).strftime("%Y-%m-%d")
    assert res.end_date == expected_end


def test_reservation_from_spring_handles_null_end_date():
    row = {**SAMPLE_SPRING_ROW, "endDate": None}
    res = Reservation.from_spring(row)
    assert res.end_date is None


def test_reservation_from_spring_handles_missing_creator_id():
    row = {**SAMPLE_SPRING_ROW}
    del row["creatorId"]
    res = Reservation.from_spring(row)
    assert res.creator_id is None


def test_reservation_creator_id_field_optional():
    # 기존 GraphQL 응답 형태에는 creator_id 없어도 model_validate 통과해야 함
    res = Reservation.model_validate(
        {
            "id": "1",
            "creator_name": "x",
            "room_id": "11",
            "room": "8층",
            "date": "2026-06-01",
            "time": "10:00:00",
            "duration": 60,
            "is_all_day": False,
            "is_repeat": False,
            "weekdays": 0,
            "reason": "x",
        }
    )
    assert res.creator_id is None


# ─── Reservation.occurs_on() — multi-day, 반복, 단일 처리 ─────────


def _make(**overrides) -> Reservation:
    """Reservation 인스턴스 빌더 (테스트 헬퍼)."""
    base = {
        "id": "1",
        "creator_name": "x",
        "room_id": "11",
        "room": "8층",
        "date": "2026-05-11",
        "time": "10:00:00",
        "duration": 60,
        "is_all_day": False,
        "is_repeat": False,
        "weekdays": 0,
        "reason": "x",
    }
    base.update(overrides)
    return Reservation.model_validate(base)


def test_occurs_on_single_day_matches_only_start_date():
    r = _make(date="2026-05-11")
    assert r.occurs_on("2026-05-11") is True
    assert r.occurs_on("2026-05-10") is False
    assert r.occurs_on("2026-05-12") is False


def test_occurs_on_multi_day_all_day_spans_entire_range():
    """비반복 종일 multi-day (AngelNet 의 종일 기간 예약 케이스).

    isRepeat=0 이지만 endDate 가 있어 매일 발생하는 형태.
    """
    r = _make(
        date="2026-05-01",
        end_date="2026-05-31",
        is_all_day=True,
        is_repeat=False,
    )
    assert r.occurs_on("2026-04-30") is False
    assert r.occurs_on("2026-05-01") is True
    assert r.occurs_on("2026-05-04") is True
    assert r.occurs_on("2026-05-11") is True
    assert r.occurs_on("2026-05-31") is True
    assert r.occurs_on("2026-06-01") is False


def test_occurs_on_multi_day_non_all_day_also_spans_range():
    """비반복 시간대 multi-day — 드물지만 (0,0,True,0,None) 케이스 존재."""
    r = _make(
        date="2026-05-01",
        end_date="2026-05-15",
        is_all_day=False,
        is_repeat=False,
    )
    assert r.occurs_on("2026-05-08") is True


def test_occurs_on_repeat_weekly_monday_only():
    """매주 월요일 반복 — weekdays bit 1 = 월."""
    r = _make(
        date="2025-04-27",
        end_date="2027-04-27",
        is_repeat=True,
        weekdays=1,
    )
    assert r.occurs_on("2026-05-11") is True  # 월
    assert r.occurs_on("2026-05-12") is False  # 화


def test_occurs_on_repeat_weekly_weekdays_all_returns_true_on_weekdays():
    """월~금 반복 — weekdays bitmask 31 = 1+2+4+8+16."""
    r = _make(
        date="2026-05-01",
        end_date="2026-12-31",
        is_repeat=True,
        weekdays=31,
    )
    for iso in ("2026-05-11", "2026-05-12", "2026-05-13", "2026-05-14", "2026-05-15"):
        assert r.occurs_on(iso) is True
    assert r.occurs_on("2026-05-16") is False  # 토
    assert r.occurs_on("2026-05-17") is False  # 일


def test_occurs_on_repeat_with_no_weekdays_matches_every_day_in_range():
    """is_repeat=true 이고 weekdays=0 이면 범위 내 매일 발생."""
    r = _make(
        date="2026-05-01",
        end_date="2026-05-31",
        is_repeat=True,
        weekdays=0,
    )
    assert r.occurs_on("2026-05-04") is True
    assert r.occurs_on("2026-05-16") is True
    assert r.occurs_on("2026-06-01") is False


def test_occurs_on_repeat_respects_start_and_end_bounds():
    r = _make(
        date="2026-05-04",
        end_date="2026-05-15",
        is_repeat=True,
        weekdays=1,
    )
    assert r.occurs_on("2026-04-27") is False  # 시작 전
    assert r.occurs_on("2026-05-18") is False  # 끝 후
