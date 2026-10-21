"""운행 기록 입력 검사 규칙(HUB_API.md AC-7). DB 없이 시험하는 순수 함수.

15% 와 10배는 합의 문서의 초안 값이다(사용자 확인 전).
"""
from statistics import median
from typing import Any, Iterable, Optional

EFFICIENCY_TOLERANCE = 0.15
DIGIT_JUMP_FACTOR = 10


def _w(field: str, rule: str, message: str) -> dict:
    return {"field": field, "rule": rule, "message": message}


def check_cumulative_decrease(cumulative_distance, prev_cumulative) -> Optional[dict]:
    if cumulative_distance is None or prev_cumulative is None:
        return None
    if cumulative_distance < prev_cumulative:
        return _w("cumulative_distance", "cumulative_decrease", "직전 기록보다 누적거리가 줄었습니다")
    return None


def check_efficiency_mismatch(fuel_efficiency, distance, consumed_fuel) -> Optional[dict]:
    if fuel_efficiency is None or distance is None or not consumed_fuel:
        return None
    calc = distance / consumed_fuel
    if calc == 0:
        return None
    if abs(fuel_efficiency - calc) / abs(calc) > EFFICIENCY_TOLERANCE:
        return _w("fuel_efficiency", "efficiency_mismatch", "연비가 주행거리÷연료 소모량과 15% 넘게 다릅니다")
    return None


def check_idle_pto_over_time(time_h, time_idle_h, time_pto_h) -> Optional[dict]:
    if time_h is None or (time_idle_h is None and time_pto_h is None):
        return None
    if (time_idle_h or 0) + (time_pto_h or 0) > time_h:
        return _w("time_h", "idle_pto_over_time", "공회전 시간과 PTO 시간의 합이 운행 시간보다 큽니다")
    return None


def check_digit_jump(field: str, value, recent_values: Iterable[Any]) -> Optional[dict]:
    """직전 30일 값의 중앙값 대비 10배 이상 또는 10분의 1 이하. 중앙값은 0 초과 값으로 구한다."""
    if value is None:
        return None
    vals = [v for v in recent_values if v is not None and v > 0]
    if not vals:
        return None
    med = median(vals)
    if value >= med * DIGIT_JUMP_FACTOR or value <= med / DIGIT_JUMP_FACTOR:
        return _w(field, "digit_jump", "최근 30일 중앙값과 10배 이상 차이납니다(자릿수 확인)")
    return None


def check_duplicate_date(duplicate: bool) -> Optional[dict]:
    if duplicate:
        return _w("date", "duplicate_date", "같은 차량의 같은 날짜 기록이 이미 있습니다")
    return None


def run_checks(rec: dict, prev_cumulative=None, recent: Iterable[dict] = (), duplicate: bool = False) -> list:
    """rec: 본문 칸. recent: 직전 30일 기록들(distance, consumed_fuel 키). 경고 목록을 돌려준다."""
    recent = list(recent)
    found = [
        check_cumulative_decrease(rec.get("cumulative_distance"), prev_cumulative),
        check_efficiency_mismatch(rec.get("fuel_efficiency"), rec.get("distance"), rec.get("consumed_fuel")),
        check_idle_pto_over_time(rec.get("time_h"), rec.get("time_idle_h"), rec.get("time_pto_h")),
        check_digit_jump("distance", rec.get("distance"), [r.get("distance") for r in recent]),
        check_digit_jump("consumed_fuel", rec.get("consumed_fuel"), [r.get("consumed_fuel") for r in recent]),
        check_duplicate_date(duplicate),
    ]
    return [w for w in found if w]
