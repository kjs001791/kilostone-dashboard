# ----------------------------------------------------------------------------------
# [Stage 1] 빌드 단계 (컴파일러 포함)
# ----------------------------------------------------------------------------------
FROM python:3.11-slim-bullseye AS builder

WORKDIR /app

# 1. [핵심] 구형 CPU(Athlon 64 X2)를 위한 컴파일 플래그 설정
# 최신 CPU 명령어(AVX 등)가 들어가지 않도록 'generic'한 x86-64 아키텍처로 제한합니다.
ENV CFLAGS="-march=x86-64 -mtune=k8 -O2"
ENV CXXFLAGS="-march=x86-64 -mtune=k8 -O2"

# 2. 시스템 패키지 설치 (빌드 도구)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    gfortran \
    libopenblas-dev \
    liblapack-dev \
    pkg-config \
    libssl-dev \
    default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

# 3. 파이썬 빌드 도구 업데이트
RUN pip install --no-cache-dir --upgrade pip setuptools wheel Cython pybind11

# 4. [중요] 핵심 라이브러리 소스 빌드
# Numpy, Pandas는 바이너리로 설치하면 AVX 오류가 나므로 소스에서 직접 컴파일합니다.
# 시간이 걸리지만 GitHub 서버가 대신 수행하므로 괜찮습니다.
RUN pip install --no-cache-dir --no-binary numpy,pandas \
    "numpy<1.27.0" \
    "pandas<2.2.0"

# 5. 나머지 라이브러리 설치
# requirements.txt에 있는 나머지 패키지들을 설치합니다.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ----------------------------------------------------------------------------------
# [Stage 2] 실행 단계 (경량화)
# ----------------------------------------------------------------------------------
FROM python:3.11-slim-bullseye

WORKDIR /app

# 1. 런타임에 필요한 최소 라이브러리만 설치
RUN apt-get update && apt-get install -y \
    libopenblas-base \
    libgfortran5 \
    default-libmysqlclient-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 2. 빌드 스테이지에서 완성된 패키지 복사
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 3. 프로젝트 소스 코드 복사
COPY . .

# 4. Streamlit 포트 노출
EXPOSE 8501

# 5. 헬스 체크 (서버가 살아있는지 주기적으로 확인)
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# 6. 실행 명령어
CMD ["streamlit", "run", "app/main.py", "--server.port=8501", "--server.address=0.0.0.0"]