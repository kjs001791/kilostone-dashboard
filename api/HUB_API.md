# 허브 API 약속

API 를 고치는 사람과 화면을 만드는 사람이 이 파일 하나로 맞춘다.

## 바꿀 때는 이 파일을 먼저 고친다

- 주소나 칸을 바꾸는 사람: 이 파일을 먼저 고치고 API 시험과 화면을 맞춤
- 화면을 만드는 사람: 여기 없는 칸을 쓰지 않음

## 접속과 단위는 아래로 고정한다

- 대상: PostgreSQL 스키마 `hub` (`db/schema.sql`)
- 접속 문자열: 환경변수 `KILOSTONE_PG_DSN`
- 접속 문자열 기본값: `postgresql+psycopg://postgres@localhost:5432/kilostone`
- 비밀번호: 코드와 `.env` 에 두지 않음, libpq 비밀번호 파일(`%APPDATA%\postgresql\pgpass.conf`) 사용
- 시험 DB: `kilostone_dummy` (같은 스키마, 가짜 데이터)
- 인증: 로컬 전용 단계라 `/hub` 경로에 로그인 없음
- 주소 앞머리: `/hub`
- 날짜: `YYYY-MM-DD`, 월: `YYYY-MM`
- 매출: `delivery.supply_amount` 합(공급가액, 부가세 제외)
- 가로형 시트 행의 매출: 적재 때 계산한 값(`amount_source = 'computed_invoice'` 또는 `'computed_company'`)
- 계산식: `weight_kg / 1000 × 그달 거래처 발행단가`, 발행단가가 없는 달은 회사인정단가(2015~2019 시트는 단가가 회사인정단가 하나뿐)
- `revenue_has_computed`: 그달 매출에 위 계산값이 하나라도 있으면 `true`
- 운송량: `delivery.weight_kg` 합을 톤으로 표시

## GET /hub/months 는 데이터가 있는 달을 최근 달부터 준다

```json
{"months": ["2025-02", "2025-01"], "latest": "2025-02"}
```

## GET /hub/summary 는 한 달 요약을 준다

`?month=YYYY-MM` 가 없으면 `latest` 달이다.

```json
{
  "month": "2025-02",
  "revenue": {"this_month": 0, "prev_month": 0, "same_month_last_year": 0},
  "revenue_has_computed": true,
  "revenue_missing_ton": 0,
  "weight_ton": {"this_month": 0, "prev_month": 0, "same_month_last_year": 0},
  "by_client": [{"client_id": 1, "client_name": "", "weight_ton": 0, "revenue": 0, "days": 0}],
  "driving": {"days": 0, "distance_km": 0, "fuel_l": 0, "avg_efficiency": 0}
}
```

- `by_client`: 그달 매출 큰 순
- 거래처 없는 행: `client_name = "미지정"`
- `revenue_missing_ton`: 그달 운송 중 매출 칸이 비어 매출 합에서 빠진 운송량(톤), 없으면 `null`
- `revenue`, `weight_ton`, `by_client` 의 `revenue` 와 `weight_ton`: 값이 하나도 없으면 `0` 이 아니라 `null`
- 값이 없는 달의 비교 칸: `null`
- `avg_efficiency`: 그달 `distance` 합 ÷ `consumed_fuel` 합

## GET /hub/vehicles 는 차량 목록과 지금 타는 차를 준다

```json
[{"vehicle_id": "V04", "brand": "Scania", "model": null, "color": "흰색", "service_start": "2023-09-01", "service_end": null, "current": true}]
```

- `current`: `service_end` 가 비어 있는 차

## GET /hub/driving 은 한 차의 최근 운행 기록을 준다

`?vehicle_id=V04&limit=30` 이다. 최근 날짜 먼저 준다. 칸은 `driving` 행 그대로다(계기판 칸 전부, `flags`, `entered_via`).

## POST /hub/driving/check 는 저장 전 검사다

```json
{"vehicle_id": "V04", "date": "2025-02-10", "distance": 0, "cumulative_distance": 0, "consumed_fuel": 0,
 "fuel_efficiency": 0, "speed": 0, "time_h": 0, "time_idle_h": 0, "time_pto_h": 0, "refuel": 0, "reurea": 0}
```

`vehicle_id` 와 `date` 만 필수다. 나머지는 null 을 허용한다.

```json
{"warnings": [{"field": "cumulative_distance", "rule": "cumulative_decrease", "message": "직전 기록보다 누적거리가 줄었습니다"}]}
```

검사 규칙(AC-7)

- `cumulative_decrease`: 같은 차 직전 날짜 기록의 `cumulative_distance` 보다 작음
- `efficiency_mismatch`: `fuel_efficiency` 와 `distance / consumed_fuel` 차이 15% 초과
- `idle_pto_over_time`: `time_idle_h + time_pto_h > time_h`
- `digit_jump`: 같은 차 직전 30일 중앙값 대비 10배 이상 또는 10분의 1 이하(`distance`, `consumed_fuel`)
- `duplicate_date`: 같은 차 같은 날짜 기록이 이미 있음

## POST /hub/driving 은 확인된 입력만 저장한다

본문은 check 와 같다. `"confirm": true|false` 가 더 붙는다.

- 경고 없음: 저장, `{"driving_id": 1, "warnings": []}`
- 경고 있음, `confirm` false: 저장 안 함, HTTP 409, `{"warnings": [...]}`
- 경고 있음, `confirm` true: `flags` 에 경고를 담아 저장
- 저장할 때 `entered_via = 'app'`, `created_at_kst = now()`
- `duplicate_date`: `confirm` 이어도 저장 안 함, HTTP 409

## 한계는 계산한 매출과 로그인 없음이다

- 가로형 시트 행의 매출은 시트에 적힌 금액이 아니라 계산값이다. 그달 발행단가가 없으면 비어 있다.
- `/hub` 경로는 로그인이 없다. 로컬 밖에 띄우기 전에 인증을 붙여야 한다.
- 검사 규칙의 15% 와 10배는 합의 문서의 초안 값이다. 사용자 확인 전이다.
