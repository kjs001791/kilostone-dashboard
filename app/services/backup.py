"""
DB 백업 및 복구
"""
import pandas as pd
import os
from datetime import datetime, timedelta
from pathlib import Path
from services.database import get_db_engine

# 백업 저장 경로
BACKUP_DIR = Path(__file__).resolve().parents[2] / "data" / "backups"


def create_backup() -> str:
    """
    현재 DB 상태를 CSV로 백업.
    반환: 백업 파일 경로
    """
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    
    engine = get_db_engine()
    df = pd.read_sql("SELECT * FROM driving_logs", engine)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"backup_{timestamp}.csv"
    filepath = BACKUP_DIR / filename
    
    df.to_csv(filepath, index=False, encoding="utf-8-sig")
    print(f"✅ 백업 완료: {filepath} ({len(df)}건)")
    
    return str(filepath)


def list_backups() -> list[dict]:
    """
    백업 파일 목록 반환.
    """
    if not BACKUP_DIR.exists():
        return []
    
    backups = []
    for f in sorted(BACKUP_DIR.glob("backup_*.csv"), reverse=True):
        stat = f.stat()
        backups.append({
            "filename": f.name,
            "filepath": str(f),
            "size_kb": round(stat.st_size / 1024, 1),
            "created": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
        })
    
    return backups


def restore_from_backup(filepath: str) -> bool:
    """
    백업 CSV로 DB 복구.
    ⚠️ 현재 데이터를 모두 삭제하고 백업 데이터로 교체.
    """
    from sqlalchemy import text
    
    df = pd.read_csv(filepath)
    
    # id, created_at 컬럼 제거 (자동 생성되므로)
    drop_cols = ['id', 'created_at']
    df = df.drop(columns=[c for c in drop_cols if c in df.columns])
    
    engine = get_db_engine()
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM driving_logs"))
        conn.commit()
    
    df.to_sql("driving_logs", engine, if_exists="append", index=False)
    
    print(f"✅ 복구 완료: {filepath} ({len(df)}건)")
    return True


def cleanup_old_backups(retention_days: int = 30):
    """
    오래된 백업 파일 삭제.
    """
    if not BACKUP_DIR.exists():
        return
    
    cutoff = datetime.now() - timedelta(days=retention_days)
    deleted = 0
    
    for f in BACKUP_DIR.glob("backup_*.csv"):
        file_time = datetime.fromtimestamp(f.stat().st_mtime)
        if file_time < cutoff:
            f.unlink()
            deleted += 1
    
    if deleted > 0:
        print(f"🧹 {deleted}개 오래된 백업 삭제됨 ({retention_days}일 초과)")