"""
파이프라인 실행 이력 기록 유틸리티
"""
import json
import os
from datetime import datetime
from pathlib import Path
from sqlalchemy import text
import sys

# 프로젝트 루트 및 app 디렉토리 경로 추가
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.database import get_db_engine


def start_run(input_files: list[str]) -> int:
    """
    파이프라인 실행 시작 기록. run_id 반환.
    """
    engine = get_db_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                INSERT INTO pipeline_runs (started_at, status, input_files)
                VALUES (:started_at, 'running', :input_files)
            """),
            {
                "started_at": datetime.now(),
                "input_files": json.dumps(input_files, ensure_ascii=False),
            }
        )
        conn.commit()
        # SQLAlchemy result.lastrowid 또는 쿼리로 가져오기
        res = conn.execute(text("SELECT LAST_INSERT_ID()"))
        return res.scalar()


def finish_run(run_id: int, rows_processed: int, rows_rejected: int):
    """
    파이프라인 정상 완료 기록.
    """
    rejection_rate = (rows_rejected / rows_processed * 100) if rows_processed > 0 else 0.0
    engine = get_db_engine()
    with engine.connect() as conn:
        conn.execute(
            text("""
                UPDATE pipeline_runs
                SET finished_at     = :finished_at,
                    status          = 'completed',
                    rows_processed  = :rows_processed,
                    rows_rejected   = :rows_rejected,
                    rejection_rate  = :rejection_rate
                WHERE run_id = :run_id
            """),
            {
                "finished_at": datetime.now(),
                "rows_processed": rows_processed,
                "rows_rejected": rows_rejected,
                "rejection_rate": round(rejection_rate, 2),
                "run_id": run_id,
            }
        )
        conn.commit()


def fail_run(run_id: int, error_message: str):
    """
    파이프라인 오류 종료 기록.
    """
    engine = get_db_engine()
    with engine.connect() as conn:
        conn.execute(
            text("""
                UPDATE pipeline_runs
                SET finished_at   = :finished_at,
                    status        = 'failed',
                    error_message = :error_message
                WHERE run_id = :run_id
            """),
            {
                "finished_at": datetime.now(),
                "error_message": str(error_message)[:2000],
                "run_id": run_id,
            }
        )
        conn.commit()
