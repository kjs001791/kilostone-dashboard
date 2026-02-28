"""
입력 데이터 검증
"""


def validate_driving_log(data: dict) -> list[str]:
    """
    운행 기록 유효성 검사.
    경고 메시지 리스트 반환. 비어있으면 문제 없음.
    """
    warnings = []

    distance = data.get('distance') or 0
    fuel = data.get('consumed_fuel') or 0
    efficiency = data.get('fuel_efficiency') or 0
    speed = data.get('speed') or 0

    # 1. 연비 범위 (화물트럭 기준 1.0 ~ 5.0)
    if efficiency > 0 and not 1.0 <= efficiency <= 5.0:
        warnings.append(
            f"연비 {efficiency} km/L 가 일반 범위(1.0~5.0)를 벗어났습니다."
        )

    # 2. 주행거리 범위
    if distance > 0 and not 10 <= distance <= 1500:
        warnings.append(
            f"주행거리 {distance} km 가 비정상적입니다."
        )

    # 3. 속도 범위
    if speed > 0 and not 5 <= speed <= 120:
        warnings.append(
            f"평균속도 {speed} km/h 가 비정상적입니다."
        )

    # 4. 교차 검증: 연비 = 거리 / 연료
    if distance > 0 and fuel > 0:
        calc_eff = round(distance / fuel, 2)
        if efficiency > 0:
            diff = abs(calc_eff - efficiency)
            if diff > 0.3:
                warnings.append(
                    f"입력 연비({efficiency})와 "
                    f"계산 연비({calc_eff})가 다릅니다. "
                    f"(거리÷연료 = {calc_eff})"
                )

    # 5. 연료소모량 범위
    if fuel > 0 and not 5 <= fuel <= 500:
        warnings.append(
            f"연료소모량 {fuel} L 가 비정상적입니다."
        )

    return warnings