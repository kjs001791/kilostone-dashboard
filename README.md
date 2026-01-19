# 🚛 KiloStone Dashboard
> **Legacy to Smart: Personalized Logistics Data Analytics System**

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.24.0-FF4B4B?style=flat&logo=streamlit&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Build_Source-2496ED?style=flat&logo=docker&logoColor=white)
![Gemini API](https://img.shields.io/badge/AI-Google_Gemini-8E75B2?style=flat&logo=google&logoColor=white)

## 📖 Project Overview
**KiloStone Dashboard**는 차량 운전자를 위해 개발된 **맞춤형 운행 기록 분석 시스템**입니다.
불규칙한 수기 입력 데이터와 오타를 AI 파이프라인으로 정제하고, 누구나 직관적으로 내역을 파악할 수 있는 시각화 대시보드를 제공합니다.

이 프로젝트는 특히 **AVX 명령어가 지원되지 않는 구형 홈 서버(AMD Athlon 64 X2)** 환경에서 최신 데이터 분석 스택을 구동하기 위해, **Docker 소스 컴파일 전략**과 **경량화 아키텍처**를 적용하여 하드웨어의 한계를 극복했습니다.

---

## 🛠 Tech Stack

| Category | Technology | Description |
| :--- | :--- | :--- |
| **Language** | Python 3.9 | Core Application Logic |
| **Frontend** | Streamlit | Data Visualization & Dashboard UI |
| **Data Proc** | Pandas, NumPy | Data Analysis & Preprocessing |
| **AI/LLM** | Google Gemini 2.5 Flash | **Asyncio** pipeline for Error Detection & Correction |
| **Infra** | Docker | Containerization (Source Compile Strategy for Legacy CPU) |
| **Server** | Xpenology (Linux) | Self-hosted Home Server |

---

## 💡 Key Features & Engineering Challenges

### 1. AI-Driven Data Cleaning Pipeline
- **Problem**: 운행 중 모바일/수기로 입력하여 오타(자릿수 실수, 키패드 인접 오타)와 누락이 빈번하게 발생.
- **Solution**: 
  - **Gemini API**를 활용한 Few-shot Learning 기반 에러 탐지 및 자동 보정.
  - `Asyncio`와 `Semaphore`를 적용한 **비동기 배치 처리**로 5년 치 대용량 데이터를 고속으로 정제.
  - 단순 규칙(Rule-based)과 AI 추론을 결합하여 데이터 정확도 99% 확보.

### 2. Optimization for Legacy Hardware (Non-AVX CPU)
- **Problem**: 배포 서버가 AVX 명령어를 지원하지 않는 구형 CPU(Athlon 64 X2) 탑재. 최신 TensorFlow/Pandas 바이너리 실행 불가(Illegal Instruction Error).
- **Solution**:
  - `Docker` 빌드 시 `--no-binary` 옵션을 사용하여 타겟 CPU 아키텍처에 맞춰 주요 라이브러리를 **직접 컴파일(Build from Source)**.
  - 무거운 차트 라이브러리 대신 경량화된 시각화 로직 적용 및 캐싱(`@st.cache_data`) 최적화.

### 3. User-Centric UX Design
- **Target User**: IT 기기 조작에 익숙하지 않은 60대 화물 차주.
- **Design**: 복잡한 필터링 없이 "접속하면 바로 핵심 지표(매출, 연비)가 보이는" 직관적인 UI 설계.

---

## 📸 Screenshots

| **Dashboard Main View** | **AI Cleaning Process (Log)** |
| :---: | :---: |
| <img src="assets/dashboard_screenshot.png" alt="Dashboard" width="400"/> | <img src="assets/cleaning_log.png" alt="Terminal Log" width="400"/> |

> *Note: 본 프로젝트의 스크린샷은 개인정보 보호를 위해 익명화된 샘플 데이터를 사용하였습니다.*

---

## 🚀 How to Run

### 1. Prerequisites
- Docker & Docker Compose installed
- Google Gemini API Key

### 2. Installation & Run
이 프로젝트는 구형 하드웨어 호환성을 위해 Docker 빌드를 권장합니다.

```bash
# 1. Repository Clone
git clone https://github.com/YourUsername/kilostone-dashboard.git

# 2. Setup Environment Variables
# Create .env file and add your Google API Key
echo "GOOGLE_API_KEY=your_api_key_here" > .env

# 3. Build & Run (Build time may vary on legacy hardware)
docker build -t kilostone-app .
docker run -d -p 8501:8501 --env-file .env kilostone-app
```

## 📂 Repository Structure
```bash
KiloStone-Dashboard/
├── data/
│   └── sample_data.csv     # Anonymized sample data for demonstration
├── scripts/
│   ├── fast_clean_ai.py    # Async AI cleaning logic
│   └── preprocessing.py    # Data transformation tools
├── app.py                  # Streamlit application entry point
├── Dockerfile              # Specialized build instruction for Legacy CPU
├── requirements.txt        # Python dependencies
└── README.md               # Project documentation
```