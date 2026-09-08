# KiloStone Dashboard - TODO

> 마지막 업데이트: 2026-05-02
> 목표: 전 기간 운행 데이터 통합 + 실사용 가능한 웹앱 (모바일 지원)

---

## 마스터 스키마 (확정)

차량 이력: MAN (2016~2019.03) → 대우프리마 (2019.04~2023.11) → 스카니아 (2023.12~)

| 컬럼 | 타입 | MAN | 대우프리마 | 스카니아 | 앱 입력 |
|---|---|---|---|---|---|
| **[식별]** |
| date | DATE | ✓ | ✓ | ✓ | 필수 |
| vehicle_id | VARCHAR(50) | ✓ | ✓ | ✓ | 선택 (자동) |
| **[거리]** |
| distance | FLOAT (km) | ✓ | ✓ | ✓ | 필수 |
| cumulative_distance | FLOAT (km) | NULL | ✓ | ✓ | 선택 |
| **[속도 / 시간]** |
| speed | FLOAT (km/h) | ✓ | NULL | ✓ | 선택 |
| time | VARCHAR (HH:MM) | ✓ | NULL | ✓ | 선택 |
| time_idle | VARCHAR (HH:MM) | NULL | NULL | ✓ | 선택 |
| time_pto | VARCHAR (HH:MM) | NULL | NULL | ✓ | 선택 |
| **[연료 소모]** |
| fuel_efficiency | FLOAT (km/l) | NULL (1기) / ✓ (2기~) | ✓ | ✓ | 필수 |
| fuel_rate_per_hour | FLOAT (l/h) | NULL | NULL | ✓ | 선택 |
| consumed_fuel | FLOAT (l) | NULL (1기) / ✓ (2기~) | ✓ | ✓ | 필수 |
| consumed_fuel_idle | FLOAT (l) | NULL | NULL | ✓ | 선택 |
| consumed_fuel_pto | FLOAT (l) | NULL | NULL | ✓ | 선택 |
| **[연료 주입]** |
| refuel | FLOAT (l) | NULL (1기) / ✓ (2기~) | ✓ | ✓ | 선택 |
| reurea | FLOAT (l) | NULL (1기) / ✓ (2기~) | ✓ | ✓ | 선택 |
| **[메타]** |
| source | VARCHAR(20) | pipeline/manual | pipeline/manual | pipeline/manual | - |
| created_at | TIMESTAMP | auto | auto | auto | - |

**MAN 1기** (2016.01~2017.05): fuel/consumed_fuel/refuel/reurea 없음 (계기판 미제공)
**MAN 2기** (2017.06~2019.03): 연료 관련 컬럼 추가됨

**source 정책**:
- 최초 적재: `pipeline` (배치 파이프라인으로 일괄 적재)
- 웹 UI에서 수정 시: `manual`로 변경
- 파이프라인 재실행 시: `source='pipeline'`만 삭제+재적재, `source='manual'`은 보호
→ 즉, 사용자가 UI에서 수정한 레코드는 파이프라인이 덮어쓰지 않음

**스키마 설계 원칙**: NULL이 있는 것은 해당 차량 계기판이 제공하지 않은 것.
버리지 않는다 — 교차검증 가능한 필드가 많을수록 AI 오류 탐지 정확도가 높아짐.

**스카니아 컬럼 매핑** (실제 데이터 기준):

기존 컬럼에 매핑:
- `distance` ← 트립미터 TOT (km)
- `speed` ← 트립미터 AVG (km/h)
- `fuel_efficiency` ← 평균소비량 AVG (km/l)
- `consumed_fuel` ← 연비개요 TOT (l)
- `time` ← 구동시간 TOT (HH:MM)
- `refuel` ← 경유 TOT (l)
- `reurea` ← 요소수 TOT (l)
- `cumulative_distance` ← 누적키로수 TOT (km)

신규 컬럼 추가:
- `fuel_rate_per_hour` ← 평균소비량 AVG (l/h)
- `consumed_fuel_idle` ← 연비개요 IDL (l)
- `consumed_fuel_pto` ← 연비개요 PTO (l)
- `time_idle` ← 구동시간 IDL (HH:MM)
- `time_pto` ← 구동시간 PTO (HH:MM)

**Step 3 검증 활용 (스카니아 전용)**:
구조: TOT = 주행 + IDL + PTO (등식 검산 불가, 범위 제약 탐지만 가능)
- `consumed_fuel_idle + consumed_fuel_pto ≤ consumed_fuel` — TOT가 너무 작으면 탐지
- `time_idle + time_pto ≤ time` — TOT 시간이 너무 작으면 탐지
- `fuel_rate_per_hour ≈ consumed_fuel / time(h)` — 직접 역산 검증 가능

---

## Phase 1 — 데이터 파이프라인 완성 (최우선)

### 1-0. 사전 준비
- [ ] DB 스키마 변경: 스카니아 전용 컬럼 5개 추가 (`ALTER TABLE`)
  - `fuel_rate_per_hour`, `consumed_fuel_idle`, `consumed_fuel_pto`, `time_idle`, `time_pto`
- [ ] `schema_config.py`: `FINAL_COLUMNS` 업데이트, period_4/5 정의 추가
- [ ] raw 파일 구조 확인: 구 통합 Excel(2016-2020) 위치 + `data/raw/new/` 월별 파일 75개

### 1-1. Step 1 수정 (messy_clean)
- [ ] 시트 필터: 시트명이 아닌 **내용 기반** 탐지로 통일
  - 상단 셀에 `트렉터 일일 운행기록` 포함 시트만 처리
  - 이유: 구 통합 Excel(2016-2020)의 시트명을 모름. `일일운행기록` 키워드 필터는 구 파일에 적용 불가할 수 있음
- [ ] MAN/대우프리마 (period_1~4): `날짜 항목` 병합셀 → date 처리 (기존 컬럼 매핑 유지)
- [ ] 스카니아 (period_5, 2023.12~): 3중 헤더 위치 기반 매핑
  - `스카니아 트렉터` 텍스트로 감지, 헤더 row 5 (0-indexed)
  - 확정 매핑: km→distance, km/h→speed, km/l→fuel_efficiency, l/h→fuel_rate_per_hour, l(TOT)→consumed_fuel, l(IDL)→consumed_fuel_idle, l(PTO)→consumed_fuel_pto, h(TOT)→time, h(IDL)→time_idle, h(PTO)→time_pto, l(경유)→refuel, l(요소수)→reurea, km(누적)→cumulative_distance

### 1-2. Step 2 수정 (messy_check)
- [ ] Check 4 로직: 2019-05 기준 이분법 → 3개 구간으로 수정
  - MAN (~2019.03): speed/time ✓, cumulative NULL
  - 대우프리마 (2019.04~2023.11): speed/time NULL, cumulative ✓
  - 스카니아 (2023.12~): speed/time ✓, cumulative ✓, 추가 컬럼 ✓

### 1-3. Step 3 수정 (dirty_clean - AI)
- [ ] **AI 모델 유연성 확보**: Gemini 외 Claude, OpenAI 등 타 LLM으로 쉽게 교체 가능하도록 추상화 레이어 도입
- [ ] 스카니아 전용 few-shot 추가 (범위 제약 탐지):
  - `consumed_fuel_idle + consumed_fuel_pto ≤ consumed_fuel`
  - `time_idle + time_pto ≤ time`
  - `fuel_rate_per_hour ≈ consumed_fuel / time(h)` (직접 역산 검증)

### 1-4. 파이프라인 실행
- [ ] 구 파일(2016-2020) + 신 파일(2020-2024) 합쳐서 한 번에 실행
- [ ] Step 1 → Step 2 → Step 3 → 제안서 검토 → Step 4 → Step 5 → DB 적재
- [ ] `source='pipeline'` 전체 교체, `source='manual'` 보호 확인

---

## Phase 2 — 백엔드 API (FastAPI)

- [ ] `api/` 디렉토리 생성, FastAPI 앱 구조 설계
- [ ] 엔드포인트: `GET/POST/PUT/DELETE /logs`, `GET /stats`
- [ ] 기존 `app/services/` 로직 재사용 (Python 유지)
- [ ] JWT 인증
- [ ] Docker Compose에 FastAPI 서비스 추가

---

## Phase 3 — 프론트엔드 (Next.js)

**확정 사항**: Next.js + Tailwind + shadcn/ui, 모바일 우선 설계

- [ ] `frontend/` 디렉토리, Next.js 프로젝트 초기화
- [ ] 페이지 구성:
  - 대시보드 (차트, KPI — 연비 추이, 주행거리, 연료비)
  - 운행기록 입력 (모바일 최적화, 차량별 폼)
  - 기록 조회/수정
- [ ] 차량별 입력 폼: 현재 차량(스카니아) 기준 전체 필드, 구 차량은 핵심 필드만
- [ ] NextAuth.js 또는 JWT 직접 구현

---

## Phase 4 — 데이터 엔지니어링 고도화 (포트폴리오)

- [ ] 파이프라인 실행 이력 테이블: `pipeline_runs (run_id, started_at, file_count, rows_processed, rows_rejected, rejection_rate, status)`
- [ ] 대시보드에 데이터 품질 메트릭 노출: "이번 배치 dirty 비율 X%"
- [ ] 이상치 비율 임계치 초과 시 알림 (이메일 또는 앱 내 알림)

---

## 보안 개선 (Phase 2 진행 중 함께)

- [ ] DB 연결: connection pooling + parameterized query 강제 (SQLAlchemy)
- [ ] JWT + refresh token 구조 (streamlit-authenticator 대체)
- [ ] IP 차단 로직 FastAPI 미들웨어로 이전

---

## 미결 결정 사항

- [ ] 구 통합 Excel 파일 (`driving_log_2016_2020.xlsx`) 위치 확인
- [ ] 스카니아 `cumulative_distance`: NULL로 두기 vs 일별 거리 누적합으로 계산해서 채우기
- [ ] 앱 입력 폼에서 vehicle_id 고정값 vs 사용자 선택

---

## 보류 (나중에)

- AI 데이터 분석 에이전트 ("왜 지난주 연비가 낮았나?" 자연어 질의)
- 예지 정비 (historical 데이터로 다음 정비 시기 예측)
- 비용 분석 (유가 연동 km당 비용)
