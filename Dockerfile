# ==============================================================================
# [Dockerfile] Streamlit Dashboard for AWS EC2 (t3.micro)
#
# - Base Image: Python 3.12 Slim (Debian Bookworm)
# - Optimization: Layer Caching, Non-root execution ready
# - Port: 8501 (Streamlit Default)
# ==============================================================================

# [1] Base Image
# 호환성이 좋은 Debian 기반의 경량화 이미지(Slim)를 사용합니다.
# (Alpine 리눅스는 Python C-extension 호환성 문제로 권장하지 않습니다.)
FROM python:3.12-slim

# [2] Environment Variables (Optimization)
# - PYTHONDONTWRITEBYTECODE: .pyc 파일 생성 방지 (컨테이너 이미지 크기 절감 & I/O 감소)
# - PYTHONUNBUFFERED: 버퍼링 없이 로그 즉시 출력 (실시간 디버깅 필수 설정)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# [3] Working Directory
# 컨테이너 내 작업 경로를 설정합니다. 모든 명령어는 이 경로를 기준으로 실행됩니다.
WORKDIR /app

# [4] System Dependencies
# 런타임 및 빌드에 필요한 최소 시스템 패키지를 설치합니다.
# - build-essential: 일부 Python 패키지 컴파일용
# - curl: Healthcheck용
# - git: Git 의존성 설치 대비
# - clean up: 설치 후 apt 캐시를 삭제하여 이미지 크기 최소화
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# [5] Python Dependencies (Layer Caching Strategy)
# [중요] requirements.txt만 먼저 복사하여 패키지를 설치합니다.
# 소스 코드가 변경되더라도 의존성 목록이 같다면, 이 레이어는 캐시(Cache)되어 빌드 속도가 비약적으로 상승합니다.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# [6] Application Code
# 나머지 소스 코드를 복사합니다. (.dockerignore에 명시된 파일은 제외됨)
COPY . .

# [7] Port Configuration
# 컨테이너가 8501 포트를 리스닝하고 있음을 명시합니다.
EXPOSE 8501

# [8] Healthcheck
# 컨테이너 상태를 주기적으로 확인합니다. (30초 간격, 3회 실패 시 Unhealthy 판정)
# 서버가 멈추거나 응답하지 않을 경우, 오케스트레이터(Docker Compose 등)가 이를 감지할 수 있게 합니다.
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# [9] Entrypoint
# 외부 접속(0.0.0.0)을 허용하며 Streamlit 앱을 실행합니다.
CMD ["streamlit", "run", "app/main.py", "--server.port=8501", "--server.address=0.0.0.0"]