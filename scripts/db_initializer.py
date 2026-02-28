import pandas as pd
import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
import urllib.parse


# 1. 환경변수 로드 (.env 파일 읽기)
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
env_path = project_root / '.env'  # .env 파일의 절대 경로 지정

if load_dotenv(dotenv_path=env_path):
    print(f"✅ .env 파일을 로드했습니다: {env_path}")
else:
    print(f"❌ .env 파일을 찾을 수 없습니다: {env_path}")

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
DB_PORT = os.getenv("DB_PORT", "3306")

print(f"   - DB_HOST: {DB_HOST}")
print(f"   - DB_USER: {DB_USER}")
print(f"   - DB_NAME: {DB_NAME}")

def create_database_if_not_exists():
    """
    데이터베이스가 없을 경우 생성하는 함수
    DB 이름 없이 서버에 먼저 접속하여 CREATE DATABASE 명령을 수행함
    """
    encoded_password = urllib.parse.quote_plus(DB_PASSWORD) if DB_PASSWORD else ""
    
    # [중요] DB_NAME을 뺀 '서버 접속용' URL 생성
    server_url = f"mysql+pymysql://{DB_USER}:{encoded_password}@{DB_HOST}:{DB_PORT}"
    
    try:
        # 서버 엔진 생성 (DB 지정 없이)
        engine = create_engine(server_url)
        with engine.connect() as conn:
            # 데이터베이스 생성 쿼리 실행 (COMMIT 필요)
            conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
            print(f"🔨 데이터베이스 '{DB_NAME}' 확인 완료 (없으면 생성됨).")
    except Exception as e:
        print(f"❌ 데이터베이스 생성 실패: {e}")
        raise e


def init_db():
    final_csv_path = project_root / 'data' / 'processed' / 'driving_log_2016_2020_final.csv'

    if not final_csv_path.exists():
        print(f"❌ 데이터 파일이 없습니다. 먼저 apply_corrections.py를 실행하세요.")
        return

    # 3. 데이터 로드 및 전처리
    print("📂 최종 데이터(CSV) 로드 중...")
    df = pd.read_csv(final_csv_path)
    
    # 1. DB에 넣기로 약속한 '진짜 컬럼' 리스트 정의
    valid_columns = [
        'date', 'vehicle_id', 'fuel_efficiency', 'speed', 'time', 
        'distance', 'cumulative_distance', 'consumed_fuel', 'refuel', 'reurea'
    ]

    # 2. DataFrame에서 유효한 컬럼만 쏙 뽑아내기 (Unnamed 컬럼 자동 제거됨)
    # (CSV에 해당 컬럼이 실제로 존재할 때만 가져옵니다)
    df = df[[c for c in valid_columns if c in df.columns]]
    
    print(f"✨ 불필요한 컬럼 제거 완료. 적재 컬럼: {list(df.columns)}")
    
    # NaN(빈 값) 처리: DB에 넣을 때는 NaN을 None(NULL)으로 바꿔주는 게 좋습니다.
    df = df.where(pd.notnull(df), None)

    # 데이터베이스가 존재하는지 먼저 확인하고 생성
    create_database_if_not_exists()

    encoded_password = urllib.parse.quote_plus(DB_PASSWORD) if DB_PASSWORD else ""
    # 4. DB 연결 (SQLAlchemy 사용)
    # 포맷: mysql+pymysql://user:password@host:port/dbname
    db_url = f"mysql+pymysql://{DB_USER}:{encoded_password}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    
    try:
        engine = create_engine(db_url)
        conn = engine.connect()
        print("✅ MySQL 데이터베이스 연결 성공!")
    except Exception as e:
        print(f"❌ DB 연결 실패: {e}")
        return

    # 5. 테이블 생성 (기존 테이블 있으면 삭제 후 재생성)
    table_name = "driving_logs"
    
    # DDL 정의 (스키마에 맞춰서 수정 가능)
    create_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        id INT AUTO_INCREMENT PRIMARY KEY,
        date DATE,
        vehicle_id VARCHAR(50),
        fuel_efficiency FLOAT,
        speed FLOAT,
        time VARCHAR(20),  -- 시간은 '12:30:00' 문자열 또는 TIME 타입
        distance FLOAT,
        cumulative_distance FLOAT,
        consumed_fuel FLOAT,
        refuel FLOAT,
        reurea FLOAT,
        source VARCHAR(20) DEFAULT 'pipeline',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """

    try:
        # 기존 데이터 초기화 (선택 사항)
        conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
        print(f"🧹 기존 테이블 '{table_name}' 삭제 완료.")
        
        # 테이블 생성
        conn.execute(text(create_table_sql))
        print(f"🔨 테이블 '{table_name}' 생성 완료.")

        # 6. 데이터 적재 (Bulk Insert)
        print(f"🚀 데이터 적재 시작 ({len(df)}건)...")
             
        # DataFrame을 SQL로 저장 (if_exists='append'로 데이터 추가)
        df.to_sql(name=table_name, con=engine, if_exists='append', index=False)
        
        print("🎉 데이터 적재 완료!")
        
    except Exception as e:
        print(f"❌ 작업 중 오류 발생: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()