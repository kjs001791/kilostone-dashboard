# Pipeline - Claude Development Guide

## 파이프라인 흐름
messy(구조 문제) → dirty(값 오류) 순서로 처리.
Excel → Step1(구조표준화) → Step2(범위검증) → Step3(Gemini AI 오류탐지) → 사람검토 → Step4(제안반영) → Step5(최종검증+DB적재)

## 차량 이력 (확정)
- MAN TGX: 2016.01 ~ 2019.03
- 대우프리마: 2019.04 ~ 2023.11
- 스카니아: 2023.12 ~ 현재

## 마스터 스키마 (확정)

### 컬럼 전체 목록
```
[식별]
date                  DATE
vehicle_id            VARCHAR(50)

[거리]
distance              FLOAT (km)
cumulative_distance   FLOAT (km)  -- MAN=NULL, 대우프리마=✓, 스카니아=✓

[속도/시간]
speed                 FLOAT (km/h)        -- 대우프리마=NULL
time                  VARCHAR (HH:MM)     -- 대우프리마=NULL
time_idle             VARCHAR (HH:MM)     -- 스카니아 전용
time_pto              VARCHAR (HH:MM)     -- 스카니아 전용

[연료 소모]
fuel_efficiency       FLOAT (km/l)        -- MAN 1기(2016~2017.05)=NULL
fuel_rate_per_hour    FLOAT (l/h)         -- 스카니아 전용
consumed_fuel         FLOAT (l)           -- MAN 1기=NULL
consumed_fuel_idle    FLOAT (l)           -- 스카니아 전용
consumed_fuel_pto     FLOAT (l)           -- 스카니아 전용

[연료 주입]
refuel                FLOAT (l)           -- MAN 1기=NULL
reurea                FLOAT (l)           -- MAN 1기=NULL

[메타]
source                VARCHAR(20)         -- 'pipeline' 또는 'manual'
created_at            TIMESTAMP
```

NULL = 해당 차량 계기판이 제공하지 않은 것 (오류 아님).

## 시트 탐지 방법 (Step 1)
시트명이 아닌 **내용 기반** 탐지.
상단 셀에 `트렉터 일일 운행기록` 포함 → 운행기록 시트로 처리.
(세명물류/기타거래처/데이터/대신산업 시트는 이 텍스트 없음 → 자동 제외)

## 스카니아 컬럼 매핑 (확정)
Excel 3중 헤더 구조: 카테고리(row3) / 서브(row4, TOT/AVG/IDL/PTO) / 단위(row5, 날짜 포함)
`스카니아 트렉터` 텍스트로 감지. 헤더 row index=5 (0-indexed).

```
DB 컬럼               ← 엑셀 위치                    예시값
────────────────────────────────────────────────────
date               ← 날짜                            2025-10-01
distance           ← 트립미터 TOT (km)               484.5
speed              ← 트립미터 AVG (km/h)             38
fuel_efficiency    ← 평균소비량 AVG (km/l)           3.5
fuel_rate_per_hour ← 평균소비량 AVG (l/h)            10.8
consumed_fuel      ← 연비개요 TOT (l)                139.2
consumed_fuel_idle ← 연비개요 IDL (l)                3.2
consumed_fuel_pto  ← 연비개요 PTO (l)                13.1
time               ← 구동시간 TOT (HH:MM)            12:50
time_idle          ← 구동시간 IDL (HH:MM)            3:01
time_pto           ← 구동시간 PTO (HH:MM)            1:51
refuel             ← 경유 TOT (l)                    140
reurea             ← 요소수 TOT (l)                  (빈값 가능)
cumulative_distance← 누적키로수 TOT (km)             192982
```

pandas가 중복 단위명을 자동 rename함: l→l, l→l.1, l→l.2, l→l.3, l→l.4 / h→h, h→h.1, h→h.2
위치(순서)로 매핑해야 함.

## Step 3 (Gemini) 검증 로직
모든 데이터는 수작업 입력 → 오류 가능성 높음. 버리지 말고 역산으로 검증.

기존 검산식 (전 차량 공통):
- distance ≈ speed × time (물리 검산)
- distance ≈ consumed_fuel × fuel_efficiency (연비 검산)

스카니아 추가 검산 (범위 제약):
- consumed_fuel_idle + consumed_fuel_pto ≤ consumed_fuel (초과 시 TOT 입력 오류)
- time_idle + time_pto ≤ time (초과 시 TOT 입력 오류)
- fuel_rate_per_hour ≈ consumed_fuel / time(h) (직접 역산)

## Step 2 스키마 시점 검증 (3구간)
- MAN (~2019.03): speed/time 있음, cumulative_distance 없음
- 대우프리마 (2019.04~2023.11): speed/time 없음(NULL 100%), cumulative_distance 있음
- 스카니아 (2023.12~): speed/time 있음, cumulative_distance 있음, 추가 컬럼 있음

## source 정책
- 파이프라인 최초 적재: `pipeline`
- 웹 UI에서 사용자 수정 시: `manual`로 변경
- 파이프라인 재실행: `source='pipeline'`만 삭제+재적재, `source='manual'`은 보호
