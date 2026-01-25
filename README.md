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

초기에는 15년 된 구형 서버에서 시작했으나, 현재는 AWS EC2 인프라와 GitHub Actions CI/CD 파이프라인을 통해 자동 배포되는 구조로 운영 중이다.

---

## 주요 기능

### 운행 데이터 시각화
- 일별/주별/월별 연비 추이 및 주행 거리 분석
- 차량별 성능 비교 차트
- 주유량 대비 연료 소모량 추적

### 인증 및 보안
- Streamlit Authenticator 기반 로그인 시스템
- IP 기반 로그인 시도 제한 (5회 초과 시 자동 차단)
- 차단 목록 영구 저장 및 관리

### AI 데이터 정제
- Google Gemini API를 활용한 입력 오류 탐지 및 보정
- Asyncio 기반 비동기 배치 처리로 대용량 데이터 고속 정제
- Few-shot Learning 기법 적용

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
| AI | Google Gemini 2.0 Flash |
| Infrastructure | AWS EC2, Docker Compose |
| CI/CD | GitHub Actions |
| Reverse Proxy | Nginx Proxy Manager |

---

## 프로젝트 구조

```
kilostone-dashboard/
├── .github/
│   └── workflows/
│       └── deploy.yml          # CI/CD 워크플로우
├── .streamlit/
│   └── config.toml             # Streamlit 테마 설정
├── app/
│   ├── auth/
│   │   └── login_guard.py      # 로그인 시도 제한 및 IP 차단
│   ├── components/
│   │   ├── charts.py           # 차트 스타일링 헬퍼
│   │   ├── kpi_cards.py        # KPI 카드 컴포넌트
│   │   └── sidebar.py          # 사이드바 렌더링
│   ├── services/
│   │   ├── data_loader.py      # 데이터 로드 및 캐싱
│   │   ├── database.py         # DB 연결 관리
│   │   └── queries.py          # SQL 쿼리
│   ├── views/
│   │   ├── overview.py         # 전체 운행 현황 탭
│   │   └── vehicle.py          # 차량별 비교 탭
│   ├── config.py               # 전역 설정 및 상수
│   ├── main.py                 # 애플리케이션 엔트리포인트
│   └── styles.py               # CSS 스타일 정의
├── assets/                     # 로고 및 이미지
├── data/                       # 영구 데이터 저장소 (볼륨 마운트)
├── scripts/
│   ├── cleaning_*.py           # AI 데이터 정제 스크립트
│   ├── db_initializer.py       # DB 초기화
│   └── *_check.py              # 데이터 검증 스크립트
├── docker-compose.yml
├── dockerfile
├── requirements.txt
└── config.yaml                 # 인증 설정 (gitignore)
```

---

## 실행 방법

### 사전 요구사항
- Docker 및 Docker Compose
- Google Gemini API Key (데이터 정제 기능 사용 시)

### 설치

```bash
# 저장소 클론
git clone https://github.com/kjs001791/kilostone-dashboard.git
cd kilostone-dashboard

# 환경 변수 설정
cat <<EOF > .env
DB_PASSWORD=your_password
DB_NAME=kilostone
DB_USER=root
DB_HOST=db
GOOGLE_API_KEY=your_gemini_api_key
EOF

# 인증 설정 (config.yaml 생성 필요)
# hash_gen.py로 비밀번호 해시 생성 후 config.yaml에 추가

# 실행
docker compose up -d --build
```

### 접속
- 대시보드: `http://localhost:8501` 또는 설정된 도메인
- Nginx Proxy Manager: `http://localhost:81`

---

## 배포

main 브랜치에 push 시 GitHub Actions가 자동으로 서버에 배포한다.

```yaml
# .github/workflows/deploy.yml 주요 흐름
1. SSH로 서버 접속
2. git fetch && git reset --hard origin/main
3. docker compose build --no-cache
4. docker compose up -d --force-recreate
```

---

## 개발 히스토리

### 레거시 하드웨어 극복
초기 개발 환경은 AMD Athlon 64 X2 기반의 15년 된 서버였다. 해당 CPU는 AVX 명령어를 지원하지 않아 최신 Python 라이브러리(Pandas, NumPy 등)의 사전 빌드 바이너리 실행이 불가능했다.

Docker 빌드 시 `--no-binary` 옵션으로 소스 컴파일을 강제하여 해결했으며, 이후 AWS EC2로 마이그레이션하여 현재 구조에 이르렀다.

### 주요 개선 사항
- 단일 main.py(500줄) → 모듈별 분리 구조로 리팩토링
- IP 기반 로그인 시도 제한 기능 추가
- Nginx Proxy Manager를 통한 SSL 적용
- GitHub Actions CI/CD 파이프라인 구축