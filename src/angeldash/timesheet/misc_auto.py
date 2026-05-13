"""자동 '기타' 문구 생성 — 반일(AM/PM) 단위 work/off 추적.

알고리즘:
1. base 날짜의 마지막 근무 종료점을 결정한다.
   - PM 반차 → 점심(AM 끝)
   - AM 반차 또는 종일 근무 → 종일 끝
   - 종일 부재(연차/공가/경조사/휴직 등) → 근무 segment 없음 → "" 반환
2. 그 직후 반일부터, work 가 끼는 순간 전까지 연속 off 반일을 모은다.
   주말·공휴일도 off 반일로 포함되지만 안내 문구에는 노출되지 않는다.
3. 그 구간에서 휴가가 실제로 있는 날(named)만 뽑아 안내 문구로 조립한다.

회사 지정 단축일(예: '가정의날')이 `exclude_labels` 에 포함되면 출근일로 취급되어
해당 날도 work segment 가 존재하는 것으로 본다.
"""

from __future__ import annotations

import datetime

_DAY_KR = ["월", "화", "수", "목", "금", "토", "일"]

# 휴가 type 한국어 라벨
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

# 종일 부재 (AM/PM 모두 off) 로 취급되는 type
_FULL_DAY_OFF_TYPES = {"연차", "공가", "경조사", "휴직"}
# 오전만 off 인 type
_AM_HALF_TYPES = {"반차(오전)", "공가(오전)"}
# 오후만 off 인 type
_PM_HALF_TYPES = {"반차(오후)", "공가(오후)"}


def _label_for_type(vac_type: str) -> str:
    return _VAC_TYPE_LABEL.get(vac_type, vac_type)


def _is_weekend(d: datetime.date) -> bool:
    return d.weekday() >= 5  # 5=토, 6=일


def _is_real_holiday(
    date_iso: str,
    holidays_by_date: dict[str, dict],
    exclude_labels: set[str],
) -> bool:
    """exclude_labels 에 들어있지 않은 진짜 공휴일이면 True."""
    info = holidays_by_date.get(date_iso)
    if not info:
        return False
    label = info.get("label") or ""
    return label not in exclude_labels


def _is_off_day(
    d: datetime.date,
    holidays_by_date: dict[str, dict],
    exclude_labels: set[str],
) -> bool:
    """그 날 전체가 무조건 off 인 일자 (주말 / 진짜 공휴일)."""
    if _is_weekend(d):
        return True
    return _is_real_holiday(d.isoformat(), holidays_by_date, exclude_labels)


def _vacs_on_date(date_iso: str, vacations: list[dict]) -> list[dict]:
    return [v for v in vacations if v.get("date") == date_iso]


def _vac_types_on(date_iso: str, vacations: list[dict]) -> set[str]:
    return {v.get("type", "") for v in _vacs_on_date(date_iso, vacations)}


def _is_am_off(
    d: datetime.date,
    vacations: list[dict],
    holidays_by_date: dict[str, dict],
    exclude_labels: set[str],
) -> bool:
    """그 날 AM 이 off (근무 안 함) 이면 True."""
    if _is_off_day(d, holidays_by_date, exclude_labels):
        return True
    types = _vac_types_on(d.isoformat(), vacations)
    if types & _FULL_DAY_OFF_TYPES:
        return True
    if types & _AM_HALF_TYPES:
        return True
    return False


def _is_pm_off(
    d: datetime.date,
    vacations: list[dict],
    holidays_by_date: dict[str, dict],
    exclude_labels: set[str],
) -> bool:
    """그 날 PM 이 off (근무 안 함) 이면 True."""
    if _is_off_day(d, holidays_by_date, exclude_labels):
        return True
    types = _vac_types_on(d.isoformat(), vacations)
    if types & _FULL_DAY_OFF_TYPES:
        return True
    if types & _PM_HALF_TYPES:
        return True
    return False


def _format_date_label(base: datetime.date, target: datetime.date) -> str:
    """base 기준 target 의 한국어 라벨. 같은 날이면 '오늘'."""
    diff = (target - base).days
    if diff == 0:
        return "오늘"
    if diff == 1:
        return "내일"
    if diff == 2:
        return "모레"
    base_iso = base.isocalendar()
    target_iso = target.isocalendar()
    if base_iso.year == target_iso.year and base_iso.week == target_iso.week:
        return f"{_DAY_KR[target.weekday()]}요일"
    if base_iso.year == target_iso.year and target_iso.week == base_iso.week + 1:
        return f"다음주 {_DAY_KR[target.weekday()]}요일"
    if base_iso.year == target_iso.year and target_iso.week > base_iso.week + 1:
        return f"다다음주 {_DAY_KR[target.weekday()]}요일"
    return f"{target.month}/{target.day}"


def _primary_vac(vacs_on_day: list[dict]) -> dict | None:
    """그 날 휴가 중 hours 가 가장 큰 것을 대표로. 없으면 None."""
    if not vacs_on_day:
        return None
    return max(vacs_on_day, key=lambda v: v.get("hours", 0))


def _build_off_half_span(
    start: tuple[datetime.date, str],
    vacations: list[dict],
    holidays_by_date: dict[str, dict],
    exclude_labels: set[str],
    max_halves: int = 60,  # 30일 분량 — 장기 연차 + 주말 padding 안전 margin
) -> list[tuple[datetime.date, str]]:
    """start 반일부터 work 가 끼는 직전까지의 (date, 'AM'|'PM') 리스트 반환."""
    span: list[tuple[datetime.date, str]] = []
    d, half = start
    for _ in range(max_halves):
        is_off = (
            _is_am_off(d, vacations, holidays_by_date, exclude_labels)
            if half == "AM"
            else _is_pm_off(d, vacations, holidays_by_date, exclude_labels)
        )
        if not is_off:
            break
        span.append((d, half))
        if half == "AM":
            half = "PM"
        else:
            half = "AM"
            d = d + datetime.timedelta(days=1)
    return span


def _named_days_in_span(
    span: list[tuple[datetime.date, str]],
    vacations: list[dict],
) -> list[tuple[datetime.date, dict]]:
    """span 안에서 휴가가 있는 날을 (date, primary_vac) 로. 같은 날 중복 제거."""
    seen: set[datetime.date] = set()
    out: list[tuple[datetime.date, dict]] = []
    for d, _ in span:
        if d in seen:
            continue
        primary = _primary_vac(_vacs_on_date(d.isoformat(), vacations))
        if primary is not None:
            out.append((d, primary))
            seen.add(d)
    return out


def _format_announcement(
    base: datetime.date,
    named: list[tuple[datetime.date, dict]],
) -> str:
    """named 휴가일 리스트로 안내 문구 조립.

    같은 type 이면 '시작~끝까지 type', 다르면 양끝 type 을 명시 ('시작 type~끝 type').
    """
    if not named:
        return ""
    if len(named) == 1:
        d, v = named[0]
        label = _format_date_label(base, d)
        type_label = _label_for_type(v.get("type", ""))
        return f"{label} {type_label}입니다"
    start_d, start_v = named[0]
    end_d, end_v = named[-1]
    start_type = _label_for_type(start_v.get("type", ""))
    end_type = _label_for_type(end_v.get("type", ""))
    start_label = _format_date_label(base, start_d)
    end_label = _format_date_label(base, end_d)
    if start_type == end_type:
        return f"{start_label}~{end_label}까지 {start_type}입니다"
    return f"{start_label} {start_type}~{end_label} {end_type}입니다"


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

    # base 가 주말/실제 공휴일이면 보고 자체가 없음 → 안내 없음
    if _is_off_day(base, holidays_by_date, excl):
        return ""

    base_types = _vac_types_on(base_date_iso, vacations)

    # base 가 종일 부재면 그 날 근무 segment 가 없으니 안내 없음
    if base_types & _FULL_DAY_OFF_TYPES:
        return ""

    has_am_half = bool(base_types & _AM_HALF_TYPES)
    has_pm_half = bool(base_types & _PM_HALF_TYPES)
    # 같은 날 AM/PM 반차가 모두 있는 edge case 도 종일 부재로 본다
    if has_am_half and has_pm_half:
        return ""

    # base 의 마지막 근무 종료점 → 그 직후 반일이 span 시작점
    if has_pm_half:
        # PM 반차: 점심 후 PM 부터 off. base PM 자체가 첫 off 반일.
        start = (base, "PM")
    else:
        # 종일 근무 또는 AM 반차(PM 근무): 종일 끝 → 다음날 AM 부터.
        start = (base + datetime.timedelta(days=1), "AM")

    span = _build_off_half_span(start, vacations, holidays_by_date, excl)
    if not span:
        return ""
    named = _named_days_in_span(span, vacations)
    return _format_announcement(base, named)
