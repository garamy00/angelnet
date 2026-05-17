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
    """미래의 첫 휴가가 오후 반차면 그 날 AM 이 근무로 끼므로 안내 책임이 그 날로 이동.

    반일 단위 규칙: base 종일 근무 → 다음날 AM = 근무(반차오후만 있음) → STOP.
    다음주 월 연차는 그 직전 금 PM 근무 후 시작되므로 금 보고에서 안내된다.
    """
    out = generate_misc_auto(
        "2026-05-14",  # 목
        vacations=[
            vac("2026-05-15", "반차(오후)", 4),  # 금 오후 반차
            vac("2026-05-18", "연차", 8),         # 다음주 월 연차
        ],
        holidays=[],
    )
    assert out == ""


def test_today_pm_half_still_reported_even_without_future() -> None:
    """오늘 오후 반차는 그대로 알린다 (오전이 끝나가는 시점에 보고)."""
    out = generate_misc_auto(
        "2026-05-14",  # 목, 오늘 오후 반차
        vacations=[vac("2026-05-14", "반차(오후)", 4)],
        holidays=[],
    )
    assert out == "오늘 오후 반차입니다"


def test_pm_half_today_continues_to_next_am_half() -> None:
    """오늘 오후 반차 + 내일 오전 반차 → 점심부터 다음날 점심까지 연속 off."""
    out = generate_misc_auto(
        "2026-05-14",  # 목
        vacations=[
            vac("2026-05-14", "반차(오후)", 4),
            vac("2026-05-15", "반차(오전)", 4),
        ],
        holidays=[],
    )
    assert out == "오늘 오후 반차~내일 오전 반차입니다"


def test_am_half_today_pm_works_announces_only_after_pm_end() -> None:
    """오늘 오전 반차 + 다음주 월 연차.

    오전 반차는 보고 시점 기준 과거(PM 근무 후 보고), 다음주 월요일 연차만 안내.
    """
    out = generate_misc_auto(
        "2026-05-15",  # 금
        vacations=[
            vac("2026-05-15", "반차(오전)", 4),  # 금 오전 반차
            vac("2026-05-18", "연차", 8),         # 다음주 월
        ],
        holidays=[],
    )
    assert out == "다음주 월요일 연차입니다"


def test_full_work_today_next_day_pm_half_means_no_announce() -> None:
    """오늘 종일 근무 + 내일 오후 반차만 → 내일 AM 근무가 끼므로 안내 없음."""
    out = generate_misc_auto(
        "2026-05-13",  # 수
        vacations=[vac("2026-05-14", "반차(오후)", 4)],
        holidays=[],
    )
    assert out == ""


# ─── 그룹 A — 휴가 사이에 공휴일이 끼는 경우 ─────────────────────


def test_a1_vacation_holiday_vacation_same_type() -> None:
    """다음주 월(연차)-화(공휴일)-수(연차) → '다음주 월요일~다음주 수요일까지 연차'."""
    out = generate_misc_auto(
        "2026-05-15",  # 금
        vacations=[
            vac("2026-05-18", "연차", 8),  # 월
            vac("2026-05-20", "연차", 8),  # 수
        ],
        holidays=[hol("2026-05-19", "임시공휴일")],  # 화
    )
    assert out == "다음주 월요일~다음주 수요일까지 연차입니다"


def test_a2_vacation_holiday_vacation_different_types() -> None:
    """양끝 휴가 type 이 다르면 각각 표시."""
    out = generate_misc_auto(
        "2026-05-15",  # 금
        vacations=[
            vac("2026-05-18", "연차", 8),  # 월 연차
            vac("2026-05-20", "공가", 8),  # 수 공가
        ],
        holidays=[hol("2026-05-19", "임시공휴일")],
    )
    assert out == "다음주 월요일 연차~다음주 수요일 공가입니다"


def test_a3_vacation_two_holidays_vacation() -> None:
    """월(연차)-화·수(공휴일 2일)-목(연차) → '월요일~목요일까지 연차'."""
    out = generate_misc_auto(
        "2026-05-15",  # 금
        vacations=[
            vac("2026-05-18", "연차", 8),  # 월
            vac("2026-05-21", "연차", 8),  # 목
        ],
        holidays=[
            hol("2026-05-19", "임시공휴일"),  # 화
            hol("2026-05-20", "임시공휴일"),  # 수
        ],
    )
    assert out == "다음주 월요일~다음주 목요일까지 연차입니다"


# ─── 그룹 B — 공휴일 근처에 반일 반차가 끼는 경우 ─────────────


def test_b1_holiday_then_am_half_next_day() -> None:
    """공휴일(월) → 다음날 오전 반차(화, PM 출근) → '다음주 화요일 오전 반차'."""
    out = generate_misc_auto(
        "2026-05-15",  # 금
        vacations=[vac("2026-05-19", "반차(오전)", 4)],  # 화 오전 반차
        holidays=[hol("2026-05-18", "임시공휴일")],  # 월 공휴일
    )
    assert out == "다음주 화요일 오전 반차입니다"


def test_b2_pm_half_today_then_holiday_tomorrow() -> None:
    """오늘 오후 반차(화) + 다음날 공휴일(수) → '오늘 오후 반차' (수는 implicit)."""
    out = generate_misc_auto(
        "2026-05-12",  # 화
        vacations=[vac("2026-05-12", "반차(오후)", 4)],
        holidays=[hol("2026-05-13", "임시공휴일")],
    )
    assert out == "오늘 오후 반차입니다"


def test_b3_pm_half_today_holiday_then_am_half() -> None:
    """월 PM 반차 + 화 공휴일 + 수 AM 반차 (점심부터 모레 점심까지 연속 off)."""
    out = generate_misc_auto(
        "2026-05-11",  # 월
        vacations=[
            vac("2026-05-11", "반차(오후)", 4),
            vac("2026-05-13", "반차(오전)", 4),
        ],
        holidays=[hol("2026-05-12", "임시공휴일")],
    )
    assert out == "오늘 오후 반차~모레 오전 반차입니다"


def test_b4_holiday_then_future_pm_half_only_no_announce() -> None:
    """공휴일(월) 후 화 오후 반차만 → 화 AM 이 근무라 span 끊김. 안내 없음."""
    out = generate_misc_auto(
        "2026-05-15",  # 금
        vacations=[vac("2026-05-19", "반차(오후)", 4)],  # 화 오후 반차
        holidays=[hol("2026-05-18", "임시공휴일")],  # 월 공휴일
    )
    assert out == ""


def test_b5_am_half_breaks_span_holiday_after_unannounced() -> None:
    """월 AM 반차(PM 근무) + 화 공휴일.

    월 PM 근무가 span 을 끊어 화 공휴일은 미언급.
    """
    out = generate_misc_auto(
        "2026-05-15",  # 금
        vacations=[vac("2026-05-18", "반차(오전)", 4)],
        holidays=[hol("2026-05-19", "임시공휴일")],
    )
    assert out == "다음주 월요일 오전 반차입니다"


# ─── 그룹 C — 미묘한 경계 ─────────────────────────────────────


def test_c1_weekend_overlapping_holiday() -> None:
    """공휴일이 주말과 겹쳐도 다음주 월 연차는 정상 안내."""
    out = generate_misc_auto(
        "2026-05-15",  # 금
        vacations=[vac("2026-05-18", "연차", 8)],
        holidays=[hol("2026-05-16", "임시공휴일")],  # 토 = 주말과 겹침
    )
    assert out == "다음주 월요일 연차입니다"


def test_c2_long_holiday_continues_to_next_next_week() -> None:
    """다음주 월-금 5일 공휴일 + 다다음주 월 연차 → '다다음주 월요일 연차'."""
    out = generate_misc_auto(
        "2026-05-15",  # 금
        vacations=[vac("2026-05-25", "연차", 8)],  # 다다음주 월
        holidays=[
            hol("2026-05-18", "임시공휴일"),  # 월
            hol("2026-05-19", "임시공휴일"),  # 화
            hol("2026-05-20", "임시공휴일"),  # 수
            hol("2026-05-21", "임시공휴일"),  # 목
            hol("2026-05-22", "임시공휴일"),  # 금
        ],
    )
    assert out == "다다음주 월요일 연차입니다"


def test_user_scenario_wed_thu_fri_continuous_half_then_next_week() -> None:
    """사용자 시나리오: 수(근무)→목(오후반차)→금(가정의날+오전반차)→다음주 월-금 연차.

    각 날짜의 보고 자동 안내:
    - 수: 빈 문자열 (목 AM 은 근무이므로 안내 없음)
    - 목: 오늘 오후 반차 ~ 내일 오전 반차 (점심부터 다음날 점심까지 연속)
    - 금: 다음주 월요일 ~ 다음주 금요일까지 연차
      (금 AM 반차는 과거, PM 근무 후 시작되는 다음 off-span)
    """
    # 2025-11-19 (수) / 11-20 (목) / 11-21 (금) / 11-24 (월) ... 11-28 (금)
    vacs = [
        vac("2025-11-20", "반차(오후)", 4),
        vac("2025-11-21", "반차(오전)", 4),
        vac("2025-11-24", "연차", 8),
        vac("2025-11-25", "연차", 8),
        vac("2025-11-26", "연차", 8),
        vac("2025-11-27", "연차", 8),
        vac("2025-11-28", "연차", 8),
    ]
    hols = [hol("2025-11-21", "가정의날")]
    excl = {"가정의날"}

    assert generate_misc_auto("2025-11-19", vacs, hols, excl) == ""
    assert generate_misc_auto("2025-11-20", vacs, hols, excl) == (
        "오늘 오후 반차~내일 오전 반차입니다"
    )
    assert generate_misc_auto("2025-11-21", vacs, hols, excl) == (
        "다음주 월요일~다음주 금요일까지 연차입니다"
    )
