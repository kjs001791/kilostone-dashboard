# KiloStone Dashboard

**화물 운송 차량의 운행 기록을 분석하고 시각화하는 웹 대시보드**

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.45-FF4B4B?style=flat&logo=streamlit&logoColor=white)
![AWS](https://img.shields.io/badge/AWS-EC2-FF9900?style=flat&logo=amazon-aws&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat&logo=docker&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/CI/CD-GitHub_Actions-2088FF?style=flat&logo=github-actions&logoColor=white)

---

## 개요

KiloStone Dashboard는 개인 화물 트럭 차주를 위한 운행 기록 관리 시스템이다. 수기로 입력되어 오류가 잦은 운행 데이터를 Google Gemini API 기반 파이프라인으로 정제하고, 연비 및 운행 지표를 직관적으로 시각화한다.

배치 파이프라인(Excel 일괄 적재)과 실시간 입력(대시보드 CRUD)을 통해 데이터를 수집하며, source 태깅으로 데이터 출처를 관리한다.

---

## 아키텍처

    [입구 A] 배치 파이프라인 (비정기, CLI)
     Excel → run_pipeline.py
              ├── Step 1. Messy 정제 (구조 표준화)
              ├── Step 2. Messy 검증 (범위/스키마 체크)
              ├── Step 3. Dirty 정제 (Gemini API) → 정지
              │   ★ 사람이 제안서 CSV 검토 ★
              ├── Step 4. 제안 승인 → dirty_applied.csv
              └── Step 5. 최종 검증 → DB 적재 (source='pipeline')
                   ※ source='manual' 데이터 보호
                   ※ 적재 전 자동 백업

    [입구 B] 실시간 입력 (매일, 대시보드)
     대시보드 폼 → Validation → DB 적재 (source='manual')

    [백업] 자동 CSV 백업 + 복구 기능
    [출구] DB → 10분 캐싱 → Streamlit 대시보드

---

## 주요 기능

### 운행 데이터 시각화
- 일별/주별/월별 연비 추이 및 주행 거리 분석
- 차량별 성능 비교 차트
- 주유량 대비 연료 소모량 추적

### 운행기록 관리 (CRUD)
- 대시보드에서 운행 기록 추가/수정/삭제
- 입력 시 실시간 유효성 검증 (범위, 교차 검증)
- DB 백업 및 복구 기능

### AI 데이터 정제
- Google Gemini API를 활용한 입력 오류 탐지 및 보정
- Asyncio 기반 비동기 배치 처리로 대용량 데이터 고속 정제
- Few-shot Learning 기법 적용 (10가지 오류 패턴)
- 자동 정지 후 사람 검토 → 최종 검증 → 승인 적재 구조

### 인증 및 보안
- Streamlit Authenticator 기반 로그인 시스템
- IP 기반 로그인 시도 제한 (5회 초과 시 자동 차단)
- 차단 목록 영구 저장 및 관리

### 인프라
- Docker Compose 기반 멀티 컨테이너 구성 (App + DB + Nginx)
- GitHub Actions를 통한 push 시 자동 배포
- Let's Encrypt SSL 인증서 적용

---

## 기술 스택

| 분류 | 기술 |
|------|------|
| Language | Python 3.12 |
| Framework | Streamlit |
| Database | MariaDB 10.6 |
| AI | Google Gemini 2.5 Flash |
| Infrastructure | AWS EC2, Docker Compose |
| CI/CD | GitHub Actions |
| Reverse Proxy | Nginx Proxy Manager |

---

## 프로젝트 구조

    kilostone-dashboard/
    ├── .github/
    │   └── workflows/
    │       └── deploy.yml              # CI/CD 워크플로우
    ├── .streamlit/
    │   └── config.toml                 # Streamlit 테마 설정
    ├── app/
    │   ├── auth/
    │   │   └── login_guard.py          # 로그인 시도 제한 및 IP 차단
    │   ├── components/
    │   │   ├── charts.py               # 차트 스타일링 헬퍼
    │   │   ├── kpi_cards.py            # KPI 카드 컴포넌트
    │   │   └── sidebar.py             # 사이드바 렌더링
    │   ├── services/
    │   │   ├── backup.py               # DB 백업 및 복구
    │   │   ├── database.py             # DB 연결 관리
    │   │   ├── data_loader.py          # 데이터 로드 및 캐싱
    │   │   ├── data_validator.py       # 입력 데이터 검증
    │   │   └── data_writer.py          # DB 쓰기 (INSERT/UPDATE/DELETE)
    │   ├── views/
    │   │   ├── data_entry.py           # 운행기록 관리 (CRUD + 백업)
    │   │   ├── overview.py             # 전체 운행 현황 탭
    │   │   └── vehicle.py              # 차량별 비교 탭
    │   ├── config.py                   # 전역 설정 및 상수
    │   ├── main.py                     # 애플리케이션 엔트리포인트
    │   └── styles.py                   # CSS 스타일 정의
    ├── assets/                         # 로고 및 이미지
    ├── data/
    │   ├── backups/                    # DB 백업 CSV
    │   ├── staging/                    # 파이프라인 중간 산출물
    │   ├── processed/                  # 최종 정제 데이터 (DB 적재 원본)
    │   └── raw/                        # 원본 데이터 (Excel)
    ├── scripts/
    │   ├── run_pipeline.py             # 통합 배치 파이프라인 (CLI 진입점)
    │   ├── db_initializer.py           # DB 테이블 생성 및 초기 적재
    │   ├── pipeline/                   # 파이프라인 모듈
    │   │   ├── schema_config.py        # 공유 설정 및 유틸리티
    │   │   ├── step1_messy_clean.py    # Messy 정제 (구조 표준화)
    │   │   ├── step2_messy_check.py    # Messy 검증 (범위/스키마)
    │   │   ├── step3_dirty_clean.py    # Dirty 정제 (Gemini API)
    │   │   ├── step4_apply_proposal.py # 제안 승인/반영
    │   │   └── step5_dirty_check.py    # 최종 검증 + DB 적재
    │   └── legacy/                     # 아카이브 (통합 전 원본 스크립트)
    │       ├── README.md
    │       ├── cleaning_messy.py
    │       ├── cleaning_dirty.py
    │       ├── messy_check.py
    │       ├── dirty_check.py
    │       └── apply_corrections.py
    ├── .env                            # 환경변수 (gitignore)
    ├── docker-compose.yml
    ├── Dockerfile
    ├── requirements.txt
    └── config.yaml                     # 인증 설정 (gitignore)

---

## 데이터 파이프라인

### 입구 A: 배치 파이프라인 (Excel 일괄 적재)

    # 전체 실행 (Step 1~3, 제안서까지)
    python scripts/run_pipeline.py --input data/raw/파일.xlsx

    # AI 생략 (Step 1~2만)
    python scripts/run_pipeline.py --input data/raw/파일.xlsx --skip-ai

    # 검토 완료 후 승인 (Step 4~5)
    python scripts/run_pipeline.py --approve data/staging/cleaning_proposal_xxx.csv

    # 이슈 감수하고 강제 적재
    python scripts/run_pipeline.py --approve data/staging/cleaning_proposal_xxx.csv --force

| 단계 | 처리 내용 | 산출물 | 자동/수동 |
|------|----------|--------|----------|
| Step 1 | Messy 정제 (컬럼 표준화, 타입 변환) | staging/messy_cleaned.csv | 자동 |
| Step 2 | Messy 검증 (범위, 스키마 시점 체크) | 콘솔 리포트 | 자동 |
| Step 3 | Dirty 정제 (Gemini API 이상치 탐지) | staging/cleaning_proposal.csv | 자동 → 정지 |
| 검토 | 사람이 제안서 CSV 검토 | - | 수동 |
| Step 4 | 제안 반영 | staging/dirty_applied.csv | 수동 트리거 |
| Step 5 | 최종 무결성 검증 + DB 적재 | processed/driving_log_final.csv | 자동 |

- 재처리 시 `source='pipeline'` 데이터만 교체, `source='manual'` 데이터는 보호
- 적재 전 자동 백업 생성
- Step 5 검증 실패 시 적재 중단, `--force`로 강제 적재 가능

### 입구 B: 실시간 입력 (대시보드 CRUD)

대시보드에서 직접 운행 기록을 추가/수정/삭제하며, 입력 시 실시간 유효성 검증을 수행한다.

- 연비 범위 검증 (1.0~5.0 km/L)
- 교차 검증 (입력 연비 vs 계산 연비)
- 거리/속도/연료소모량 범위 검증
- 모든 입력은 `source='manual'`로 태깅

---

## DB 스키마

### driving_logs

| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| id | INT (PK) | Auto Increment |
| date | DATE | 운행 일자 |
| vehicle_id | VARCHAR(50) | 차량 ID |
| fuel_efficiency | FLOAT | 연비 (km/L) |
| speed | FLOAT | 평균 속도 (km/h) |
| time | VARCHAR(20) | 운행 시간 |
| distance | FLOAT | 주행 거리 (km) |
| cumulative_distance | FLOAT | 누적 거리 (km) |
| consumed_fuel | FLOAT | 연료 소모량 (L) |
| refuel | FLOAT | 주유량 (L) |
| reurea | FLOAT | 요소수 (L) |
| source | VARCHAR(20) | 데이터 출처 (pipeline/manual) |
| created_at | TIMESTAMP | 생성 시각 |

---

## 실행 방법

### 사전 요구사항
- Docker 및 Docker Compose
- Google Gemini API Key (배치 파이프라인 사용 시)

### 설치

    # 저장소 클론
    git clone https://github.com/kjs001791/kilostone-dashboard.git
    cd kilostone-dashboard

    # 환경 변수 설정
    cat <<EOF > .env
    DB_HOST=db
    DB_PORT=3306
    DB_USER=root
    DB_PASSWORD=your_password
    DB_NAME=kilostone
    GOOGLE_API_KEY=your_gemini_api_key
    EOF

    # 인증 설정 (config.yaml 생성 필요)
    # 실행
    docker compose up -d --build

### 접속
- 대시보드: `http://localhost:8501` 또는 설정된 도메인

### 배치 파이프라인 사용

    # 전체 실행 (Step 1~3 → 제안서 출력 후 자동 정지)
    python scripts/run_pipeline.py --input data/raw/파일.xlsx

    # AI 생략 (Step 1~2만)
    python scripts/run_pipeline.py --input data/raw/파일.xlsx --skip-ai

    # 검토 완료 후 승인 (Step 4~5 → 검증 통과 시 DB 적재)
    python scripts/run_pipeline.py --approve data/staging/cleaning_proposal_xxx.csv

    # 이슈 감수하고 강제 적재
    python scripts/run_pipeline.py --approve data/staging/cleaning_proposal_xxx.csv --force

---

## 배포

main 브랜치에 push 시 GitHub Actions가 자동으로 서버에 배포한다.

    # .github/workflows/deploy.yml 주요 흐름
    1. SSH로 서버 접속
    2. git fetch && git reset --hard origin/main
    3. docker compose build --no-cache
    4. docker compose up -d --force-recreate

---

## 개발 히스토리

### 레거시 하드웨어 극복
초기 개발 환경은 AMD Athlon 64 X2 기반의 15년 된 서버였다. 해당 CPU는 AVX 명령어를 지원하지 않아 최신 Python 라이브러리(Pandas, NumPy 등)의 사전 빌드 바이너리 실행이 불가능했다.

Docker 빌드 시 --no-binary 옵션으로 소스 컴파일을 강제하여 해결했으며, 이후 AWS EC2로 마이그레이션하여 현재 구조에 이르렀다.

### 주요 개선 사항
- 단일 main.py(500줄) → 모듈별 분리 구조로 리팩토링
- 배치 파이프라인 모듈화 (run_pipeline.py → 5개 step 모듈 분리)
- Step 5 최종 무결성 검증 추가 (누적거리 역전, 물리적 한계, 수학적 정합성)
- 파이프라인 중간 산출물 관리 체계 (data/staging/)
- IP 기반 로그인 시도 제한 기능 추가
- 대시보드 CRUD 및 데이터 검증 기능 추가
- 배치 + 실시간 이중 수집 파이프라인 구축 (source 태깅)
- DB 백업/복구 기능
- Nginx Proxy Manager를 통한 SSL 적용
- GitHub Actions CI/CD 파이프라인 구축