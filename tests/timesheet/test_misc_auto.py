"""generate_misc_auto 의 7가지 사용자 명시 케이스 검증."""

from __future__ import annotations

from angeldash.timesheet.misc_auto import generate_misc_auto


# 헬퍼: vacation dict
def vac(date: str, type_: str, hours: float = 8.0) -> dict:
    return {"date": date, "type": type_, "hours": hours}


def hol(date: str, label: str = "공휴일") -> dict:
    return {"date": date, "label": label, "types": ["public"]}


def test_case1_tomorrow_vacation_only() -> None:
    """내일 연차 → '내일 연차입니다'"""
    # 화요일 보고, 수요일 연차
    out = generate_misc_auto(
        "2026-05-12",  # 화
        vacations=[vac("2026-05-13", "연차", 8)],
        holidays=[],
    )
    assert out == "내일 연차입니다"


def test_case2_next_monday_vacation_on_friday_report() -> None:
    """금요일 보고 + 다음주 월요일 연차 → '다음주 월요일 연차입니다'"""
    out = generate_misc_auto(
        "2026-05-15",  # 금
        vacations=[vac("2026-05-18", "연차", 8)],  # 다음주 월
        holidays=[],
    )
    assert out == "다음주 월요일 연차입니다"


def test_case3_thursday_report_friday_to_monday_continuous() -> None:
    """목요일 보고 + 금/(주말)/월 연속 연차 → '내일~다음주 월요일까지 연차입니다'"""
    out = generate_misc_auto(
        "2026-05-14",  # 목
        vacations=[
            vac("2026-05-15", "연차", 8),  # 금
            vac("2026-05-18", "연차", 8),  # 다음주 월
        ],
        holidays=[],
    )
    assert out == "내일~다음주 월요일까지 연차입니다"


def test_case4_friday_report_monday_holiday_tuesday_vacation() -> None:
    """금요일 보고 + 다음주 월 공휴일 + 화요일 연차 → '다음주 화요일 연차입니다'"""
    out = generate_misc_auto(
        "2026-05-15",  # 금
        vacations=[vac("2026-05-19", "연차", 8)],  # 다음주 화
        holidays=[hol("2026-05-18", "임시공휴일")],  # 다음주 월
    )
    assert out == "다음주 화요일 연차입니다"


def test_case5_tuesday_report_wednesday_morning_half() -> None:
    """화요일 보고 + 수요일 오전 반차 → '내일 오전 반차입니다'"""
    out = generate_misc_auto(
        "2026-05-12",  # 화
        vacations=[vac("2026-05-13", "반차(오전)", 4)],
        holidays=[],
    )
    assert out == "내일 오전 반차입니다"


def test_case6_today_afternoon_half_only() -> None:
    """목요일 보고 + 오늘 오후 반차 → '오늘 오후 반차입니다'"""
    out = generate_misc_auto(
        "2026-05-14",  # 목
        vacations=[vac("2026-05-14", "반차(오후)", 4)],
        holidays=[],
    )
    assert out == "오늘 오후 반차입니다"


def test_case7_today_afternoon_half_plus_tomorrow_full() -> None:
    """수요일 보고 + 오늘 오후 반차 + 내일 연차 → '오늘 오후 반차~내일 연차입니다'"""
    out = generate_misc_auto(
        "2026-05-13",  # 수
        vacations=[
            vac("2026-05-13", "반차(오후)", 4),
            vac("2026-05-14", "연차", 8),
        ],
        holidays=[],
    )
    assert out == "오늘 오후 반차~내일 연차입니다"


def test_no_vacations_returns_empty() -> None:
    assert generate_misc_auto(
        "2026-05-12", vacations=[], holidays=[],
    ) == ""


def test_exclude_label_skipped_as_business_day() -> None:
    """가정의날 같은 회사 지정 단축일은 출근일로 취급."""
    # 가정의날 다음 영업일 = 그 다음 날 (가정의날 라벨 exclude)
    out = generate_misc_auto(
        "2026-05-21",  # 목
        vacations=[vac("2026-05-22", "연차", 8)],  # 금=가정의날인데 연차
        holidays=[hol("2026-05-22", "가정의날")],
        exclude_labels={"가정의날"},
    )
    # 가정의날을 출근일로 보면 5/22 (금) 가 영업일이고 그 날 연차 → "내일 연차"
    assert out == "내일 연차입니다"


def test_exclude_label_not_set_treats_as_real_holiday() -> None:
    """exclude_labels 비어있으면 가정의날도 공휴일로 취급."""
    # 5/22 (금) 가 공휴일이면 그 날 휴가는 건너뜀 → 다음 영업일 5/25 (월)
    out = generate_misc_auto(
        "2026-05-21",  # 목
        vacations=[vac("2026-05-25", "연차", 8)],
        holidays=[hol("2026-05-22", "가정의날")],
    )
    # 5/22 = 공휴일, 5/25 (월) 가 다음 영업일 → 연차
    assert out == "다음주 월요일 연차입니다"


def test_future_afternoon_half_alone_is_ignored() -> None:
    """미래의 오후 반차만 있는 날은 그 날 오전 정상 출근이므로 보고 안 함."""
    out = generate_misc_auto(
        "2026-05-14",  # 목
        vacations=[vac("2026-05-15", "반차(오후)", 4)],  # 금 오후 반차
        holidays=[],
    )
    assert out == ""


def test_future_afternoon_half_then_full_skips_to_next_with_vac() -> None:
    """미래의 첫 휴가가 오후 반차 + 그 다음 영업일에 연차면, 연차부터 보고."""
    out = generate_misc_auto(
        "2026-05-14",  # 목
        vacations=[
            vac("2026-05-15", "반차(오후)", 4),  # 금 오후 반차 (출근 가능, 건너뜀)
            vac("2026-05-18", "연차", 8),         # 다음주 월 연차
        ],
        holidays=[],
    )
    assert out == "다음주 월요일 연차입니다"


def test_today_pm_half_still_reported_even_without_future() -> None:
    """오늘 오후 반차는 그대로 알린다 (오전이 끝나가는 시점에 보고)."""
    out = generate_misc_auto(
        "2026-05-14",  # 목, 오늘 오후 반차
        vacations=[vac("2026-05-14", "반차(오후)", 4)],
        holidays=[],
    )
    assert out == "오늘 오후 반차입니다"
