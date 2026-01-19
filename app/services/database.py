import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import URL # URL 생성 도구 추가
import pymysql
from pathlib import Path

# 현재 파일 위치 기준 .env 경로 설정
env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=env_path)

def get_db_engine() -> Engine:
    try:
        user = os.getenv("DB_USER")
        password = os.getenv("DB_PASSWORD")
        host = os.getenv("DB_HOST")
        port_str = os.getenv("DB_PORT")
        dbname = os.getenv("DB_NAME")

        # 디버깅: 값 확인 (비밀번호는 보안상 길이만 출력)
        pwd_len = len(password) if password else 0
        print(f"DEBUG: User={user}, Host={host}, Port={port_str}, DB={dbname}, PwdLength={pwd_len}")

        if not all([user, password, host, port_str, dbname]):
             raise ValueError("⚠️ .env 파일에서 일부 환경변수를 불러오지 못했습니다.")
        
        # 포트 정수 변환
        port = int(str(port_str).strip())

        # [핵심 변경] f-string 대신 URL 객체 사용
        # 비밀번호의 특수문자를 자동으로 안전하게 처리(Encoding)해줍니다.
        connection_url = URL.create(
            drivername="mysql+pymysql",
            username=user,
            password=password,
            host=host,
            port=port,
            database=dbname
        )
        
        # 엔진 생성
        engine = create_engine(connection_url, pool_recycle=3600)
        return engine

    except Exception as e:
        print(f"❌ DB 연결 설정 중 오류 발생: {e}")
        raise e