"""자동 '기타' 문구 생성 — 휴가/공휴일 기반.

알고리즘:
1. 보고 대상 날짜 (base_date) 의 휴가가 있으면 '오늘 X' 부분 만듬
2. 다음 영업일 (주말 + 진짜 공휴일 건너뛰기) 의 휴가 시작점부터
   연속 구간을 찾아 미래 부분 만듬
3. 둘 다 있으면 '오늘 X~미래 Y' 로 결합

회사 지정 단축일 (예: '가정의날') 은 settings.misc.holiday_exclude_labels 에
포함되어 있으면 출근일로 취급 (영업일).
"""

from __future__ import annotations

import datetime
from typing import Any

_DAY_KR = ["월", "화", "수", "목", "금", "토", "일"]


# 휴가 타입 한국어 표현
_VAC_TYPE_LABEL = {
    "연차": "연차",
    "반차(오전)": "오전 반차",
    "반차(오후)": "오후 반차",
    "공가": "공가",
    "공가(오전)": "오전 공가",
    "공가(오후)": "오후 공가",
    "경조사": "경조사",
    "휴직": "휴직",
}


def _label_for_type(vac_type: str) -> str:
    return _VAC_TYPE_LABEL.get(vac_type, vac_type)


def _is_real_holiday(
    date_iso: str,
    holidays_by_date: dict[str, dict],
    exclude_labels: set[str],
) -> bool:
    """공휴일이면 True. exclude_labels 의 label 은 출근일 (False)."""
    info = holidays_by_date.get(date_iso)
    if not info:
        return False
    label = info.get("label") or ""
    return label not in exclude_labels


def _is_weekend(d: datetime.date) -> bool:
    return d.weekday() >= 5  # 5=토, 6=일


def _is_off_day(
    d: datetime.date,
    holidays_by_date: dict[str, dict],
    exclude_labels: set[str],
) -> bool:
    """그 날이 휴일 (주말 or 진짜 공휴일) 인가."""
    if _is_weekend(d):
        return True
    return _is_real_holiday(d.isoformat(), holidays_by_date, exclude_labels)


def _next_business_day(
    base: datetime.date,
    holidays_by_date: dict[str, dict],
    exclude_labels: set[str],
    max_lookahead: int = 14,
) -> datetime.date | None:
    """base 다음 날부터 첫 영업일을 반환. max_lookahead 일 안에 없으면 None."""
    for i in range(1, max_lookahead + 1):
        d = base + datetime.timedelta(days=i)
        if not _is_off_day(d, holidays_by_date, exclude_labels):
            return d
    return None


def _vacs_on_date(
    date_iso: str, vacations: list[dict]
) -> list[dict]:
    return [v for v in vacations if v.get("date") == date_iso]


def _find_continuous_range_end(
    start: datetime.date,
    vacations: list[dict],
    holidays_by_date: dict[str, dict],
    exclude_labels: set[str],
    max_span: int = 14,
) -> datetime.date:
    """start 부터 연속된 휴가 구간의 마지막 영업일을 반환.

    영업일이면 그 날 휴가가 있어야 연속. 휴일 (주말/공휴일) 은 건너뛰고
    다음 영업일에 휴가 있으면 연결.
    """
    end = start
    cursor = start
    for _ in range(max_span):
        # 다음 날
        next_day = cursor + datetime.timedelta(days=1)
        # 다음 날이 휴일이면 건너뛰면서 다음 영업일 찾기
        while _is_off_day(next_day, holidays_by_date, exclude_labels):
            next_day = next_day + datetime.timedelta(days=1)
            if (next_day - start).days > max_span:
                return end
        # 그 영업일에 휴가가 있으면 연결
        if _vacs_on_date(next_day.isoformat(), vacations):
            end = next_day
            cursor = next_day
            continue
        break
    return end


def _format_date_label(
    base: datetime.date, target: datetime.date
) -> str:
    """base 기준 target 의 한국어 표현."""
    diff = (target - base).days
    if diff == 1:
        return "내일"
    if diff == 2:
        return "모레"
    # 같은 ISO 주 안인지 확인
    base_iso = base.isocalendar()  # (year, week, weekday)
    target_iso = target.isocalendar()
    if base_iso.year == target_iso.year and base_iso.week == target_iso.week:
        return f"{_DAY_KR[target.weekday()]}요일"
    # 다음 주
    if base_iso.year == target_iso.year and target_iso.week == base_iso.week + 1:
        return f"다음주 {_DAY_KR[target.weekday()]}요일"
    # 그 외 (다다음주 이상)
    if base_iso.year == target_iso.year and target_iso.week > base_iso.week + 1:
        return f"다다음주 {_DAY_KR[target.weekday()]}요일"
    # 연도 넘어가는 경우 등은 M/D
    return f"{target.month}/{target.day}"


def _format_vac_single(vacs_on_day: list[dict]) -> str:
    """한 날의 휴가들을 한 라벨로 표현. 가장 큰 hours 의 type 우선."""
    if not vacs_on_day:
        return ""
    # 가장 시간 큰 것 우선 (보통 한 날 하나)
    primary = max(vacs_on_day, key=lambda v: v.get("hours", 0))
    return _label_for_type(primary.get("type", ""))


def generate_misc_auto(
    base_date_iso: str,
    vacations: list[dict],
    holidays: list[dict],
    exclude_labels: set[str] | None = None,
) -> str:
    """자동 '기타' 문구를 생성.

    Args:
        base_date_iso: 보고 대상 날짜 'YYYY-MM-DD'
        vacations: [{date, type, hours}, ...]
        holidays: [{date, label, types}, ...]
        exclude_labels: 출근일로 취급할 공휴일 라벨 set ('가정의날' 등)
    """
    base = datetime.date.fromisoformat(base_date_iso)
    excl = set(exclude_labels or ())
    holidays_by_date = {h["date"]: h for h in holidays if h.get("date")}

    # 오늘 휴가
    today_vacs = _vacs_on_date(base_date_iso, vacations)
    today_label = _format_vac_single(today_vacs)
    today_part = f"오늘 {today_label}" if today_label else ""

    # 다음 영업일 시작 연속 구간.
    # 시작점이 '반차(오후)' 만 있는 날이면 그 날 오전엔 출근하므로 미리 알릴 필요 없음 → 건너뜀.
    next_biz = _next_business_day(base, holidays_by_date, excl)
    while next_biz is not None:
        start_vacs = _vacs_on_date(next_biz.isoformat(), vacations)
        if not start_vacs:
            next_biz = None
            break
        non_pm_half = [v for v in start_vacs if v.get("type") != "반차(오후)"]
        if non_pm_half:
            # 오전 반차 / 연차 등 그 날 오전부터 부재 → 시작점으로 채택
            break
        # 그 날은 오후 반차만 — 건너뛰고 다음 영업일로
        next_biz = _next_business_day(next_biz, holidays_by_date, excl)

    future_part = ""
    if next_biz is not None:
        start_vacs = _vacs_on_date(next_biz.isoformat(), vacations)
        if start_vacs:
            end = _find_continuous_range_end(
                next_biz, vacations, holidays_by_date, excl,
            )
            start_label = _format_date_label(base, next_biz)
            start_vac_label = _format_vac_single(start_vacs)
            if end == next_biz:
                future_part = f"{start_label} {start_vac_label}"
            else:
                # 연속 구간 — 마지막 날 표현 + 같은/다른 타입 여부
                end_vacs = _vacs_on_date(end.isoformat(), vacations)
                end_label = _format_date_label(base, end)
                end_vac_label = _format_vac_single(end_vacs)
                if start_vac_label == end_vac_label:
                    future_part = f"{start_label}~{end_label}까지 {start_vac_label}"
                else:
                    future_part = (
                        f"{start_label} {start_vac_label}~"
                        f"{end_label} {end_vac_label}"
                    )

    # 조합 + 어미
    if today_part and future_part:
        # '오늘 오후 반차~내일 연차' 같이 — '입니다' 는 끝에만
        return f"{today_part}~{future_part}입니다"
    if today_part:
        return f"{today_part}입니다"
    if future_part:
        return f"{future_part}입니다"
    return ""
