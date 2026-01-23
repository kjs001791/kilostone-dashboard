# ----------------------------------------------------------------------------------
# AWS EC2 (t3.micro) & Ubuntu 24.04 환경을 위한 최적화 Dockerfile
# ----------------------------------------------------------------------------------

# [변경] 회원님 환경에 맞춰 Python 3.12 Slim 버전 사용
FROM python:3.12-slim

WORKDIR /app

# 필수 시스템 패키지 설치
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# 파이썬 패키지 관리자(pip) 최신화
RUN pip install --no-cache-dir --upgrade pip

# 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY . .

# 포트 설정
EXPOSE 8501

# 헬스 체크
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# 실행 명령어
CMD ["streamlit", "run", "app/main.py", "--server.port=8501", "--server.address=0.0.0.0"]