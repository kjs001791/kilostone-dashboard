# 🚛 KiloStone Dashboard
> **레거시 환경에서 클라우드 자동화로 진화한 지능형 화물 운행 분석 시스템**

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat&logo=python&logoColor=white)
![AWS](https://img.shields.io/badge/AWS-EC2-FF9900?style=flat&logo=amazon-aws&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat&logo=docker&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/CI/CD-GitHub_Actions-2088FF?style=flat&logo=github-actions&logoColor=white)
![Gemini API](https://img.shields.io/badge/AI-Google_Gemini-8E75B2?style=flat&logo=google&logoColor=white)

---

## 목차
1. [프로젝트 개요](#프로젝트-개요)
2. [기술 스택](#기술-스택)
3. [핵심 기능 및 엔지니어링 도전 과제](#핵심-기능-및-엔지니어링-도전-과제)
4. [프로젝트 히스토리: 레거시 하드웨어 극복 과정](#프로젝트-히스토리-레거시-하드웨어-극복-과정)
5. [스크린샷](#스크린샷)
6. [실행 방법](#실행-방법)
7. [폴더 구조](#폴더-구조)

---

## 프로젝트 개요
**KiloStone Dashboard**는 개인 화물 트럭 차주를 위한 지능형 운행 기록 관리 및 분석 시스템입니다. 
수기로 입력되어 오차가 잦은 운행 데이터를 AI(Gemini) 파이프라인으로 정제하고, 매출 및 연비 지표를 직관적으로 시각화합니다.

초기에는 15년 된 구형 서버 환경에서 시작되었으나, 현재는 **AWS 클라우드 마이그레이션**과 **GitHub Actions를 통한 CI/CD 파이프라인**을 구축하여 배포 자동화와 시스템 가용성을 확보한 현대적인 아키텍처로 진화하였습니다.

---

## 기술 스택

| Category | Technology | Description |
| :--- | :--- | :--- |
| **Language** | Python 3.12 | 전체 애플리케이션 로직 및 데이터 처리 |
| **Framework** | Streamlit | 데이터 분석 결과 시각화 및 인터랙티브 웹 대시보드 구현 |
| **Database** | MariaDB 10.6 | 운행 기록 데이터 및 정제 결과 저장 (Docker 컨테이너 기반) |
| **AI / LLM** | Google Gemini 2.0 Flash | **Asyncio** 기반의 비동기 데이터 에러 탐지 및 자동 보정 엔진 |
| **Infrastructure** | AWS EC2 | Ubuntu 24.04 기반 클라우드 호스팅 환경 |
| **DevOps** | Docker Compose, GitHub Actions | 멀티 컨테이너 통합 관리 및 CI/CD 배포 자동화 구축 |

---

## 핵심 기능 및 엔지니어링 도전 과제

### 1. AI 기반 데이터 정제 파이프라인 (Gemini API)
- **현안**: 주행 중 입력된 데이터의 특성상 자릿수 누락, 키패드 인접 오타 등 휴먼 에러로 인한 통계 왜곡 발생.
- **해결**: 
  - Gemini API 기반의 **Few-shot Learning** 기법을 적용하여 데이터 에러 탐지 및 보정 로직 구현.
  - `Asyncio` 및 `Semaphore`를 활용한 **비동기 배치 처리** 시스템을 구축하여 5년 치 대용량 데이터를 고속 정제.
  - 규칙 기반(Rule-based) 검증과 AI 추론을 결합하여 데이터 정합성 및 신뢰성 극대화.

### 2. AWS 클라우드 마이그레이션 및 CI/CD 자동화
- **현안**: 노후 하드웨어 기반 배포 환경의 낮은 성능과 네트워크 불안정성으로 인한 서비스 가용성 저하.
- **해결**: 
  - **AWS EC2** 인프라로 마이그레이션하여 24/7 안정적인 운영 환경 확보.
  - **GitHub Actions**를 도입하여 코드 변경 시 빌드, 테스트, AWS 배포까지 전 과정을 자동화한 **CI/CD 파이프라인** 구축.
  - 환경 변수 및 시크릿 관리 도구를 통해 클라우드 환경의 보안성 강화.

### 3. 멀티 컨테이너 기반 데이터 영속성 설계
- **내용**: 
  - **Docker Compose**를 활용해 애플리케이션 프레임워크와 MariaDB를 독립된 컨테이너로 오케스트레이션.
  - 데이터 볼륨(Volume) 매핑 전략을 적용하여 컨테이너 생명 주기와 무관한 **데이터 영속성(Persistence)** 확보.
  - 격리된 네트워크 구성을 통해 컨테이너 간 통신 보안 및 관리 효율성 제고.

---

## 프로젝트 히스토리: 레거시 하드웨어 극복 과정

본 프로젝트는 현업에서 운용되던 15년 전 구형 시스템(AMD Athlon 64 X2 CPU) 환경에서 시작되었습니다.

- **기술적 제약**: 해당 CPU의 **AVX 명령어 세트 부재**로 인해 최신 데이터 과학 라이브러리(Pandas, NumPy 등)의 공식 바이너리 실행 불가(Illegal Instruction Error 발생).
- **해결 방안**: Docker 빌드 단계에서 `--no-binary` 옵션을 강제하여 타겟 아키텍처에 최적화된 **소스 코드 직접 컴파일(Build from Source) 전략** 수립 및 실행.
- **의의**: 하드웨어의 물리적 한계를 소프트웨어 엔지니어링 최적화로 극복한 경험을 확보하였으며, 이는 추후 시스템을 클라우드 아키텍처로 진화시키는 데 기술적 기반이 됨.

---

## 스크린샷

| 대시보드 메인 화면 | AI 데이터 정제 프로세스 |
| :---: | :---: |
| <img src="assets/dashboard_screenshot.png" alt="Dashboard" width="400"/> | <img src="assets/cleaning_log.png" alt="Terminal Log" width="400"/> |

> *참고: 위 스크린샷은 개인정보 보호를 위해 익명화된 테스트 데이터를 사용하였습니다.*

---

## 실행 방법

### 1. 사전 요구사항
- Docker 및 Docker Compose 설치
- Google Gemini API Key 발급

### 2. 설치 및 실행

```bash
# 1. 저장소 복제
git clone [https://github.com/kjs001791/kilostone-dashboard.git](https://github.com/kjs001791/kilostone-dashboard.git)
cd kilostone-dashboard

# 2. 환경 변수 설정
# .env 파일을 생성하고 API 키 및 DB 설정을 입력합니다.
cat <<EOF > .env
DB_PASSWORD=your_password
DB_NAME=kilostone
DB_USER=root
DB_HOST=db
GOOGLE_API_KEY=your_gemini_api_key
EOF

# 3. Docker Compose를 이용한 실행
docker compose up -d --build
```

---

## 폴더 구조
```bash
KiloStone-Dashboard/
├── .github/workflows/      # GitHub Actions CI/CD 워크플로우
├── app/
│   ├── main.py             # Streamlit 애플리케이션 엔트리 포인트
│   └── database.py         # DB 연결 및 쿼리 로직
├── data/                   # 데이터 볼륨 (CSV 등)
├── mysql/                  # 데이터베이스 영속성 볼륨
├── scripts/
│   ├── fast_clean_ai.py    # 비동기 AI 정제 스크립트
│   └── db_initializer.py   # 초기 DB 스키마 생성 및 초기화
├── docker-compose.yml      # 멀티 컨테이너 정의 파일
├── Dockerfile              # Python 3.12-slim 기반 최적화 이미지
└── requirements.txt        # 프로젝트 의존성 목록
```