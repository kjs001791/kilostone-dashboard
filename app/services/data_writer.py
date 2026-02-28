"""
DB 쓰기 작업 (INSERT, UPDATE, DELETE)
"""
import streamlit as st
from sqlalchemy import text
from services.database import get_db_engine
from datetime import datetime


def insert_driving_log(data: dict) -> bool:
    """운행 기록 추가"""
    try:
        engine = get_db_engine()
        query = text("""
            INSERT INTO driving_logs 
            (date, vehicle_id, fuel_efficiency, speed, time,
             distance, cumulative_distance, consumed_fuel, refuel, reurea, source)
            VALUES 
            (:date, :vehicle_id, :fuel_efficiency, :speed, :time,
             :distance, :cumulative_distance, :consumed_fuel, :refuel, :reurea, 'manual')
        """)
        with engine.connect() as conn:
            conn.execute(query, data)
            conn.commit()
        return True
    except Exception as e:
        st.error(f"저장 실패: {e}")
        return False


def update_driving_log(record_id: int, data: dict) -> bool:
    """운행 기록 수정"""
    try:
        engine = get_db_engine()
        query = text("""
            UPDATE driving_logs 
            SET date=:date, vehicle_id=:vehicle_id, 
                fuel_efficiency=:fuel_efficiency, speed=:speed,
                time=:time, distance=:distance,
                cumulative_distance=:cumulative_distance,
                consumed_fuel=:consumed_fuel, 
                refuel=:refuel, reurea=:reurea
            WHERE id=:id
        """)
        data['id'] = record_id
        with engine.connect() as conn:
            result = conn.execute(query, data)
            conn.commit()
        return result.rowcount > 0
    except Exception as e:
        st.error(f"수정 실패: {e}")
        return False


def delete_driving_log(record_id: int) -> bool:
    """운행 기록 삭제"""
    try:
        engine = get_db_engine()
        query = text("DELETE FROM driving_logs WHERE id = :id")
        with engine.connect() as conn:
            result = conn.execute(query, {"id": record_id})
            conn.commit()
        return result.rowcount > 0
    except Exception as e:
        st.error(f"삭제 실패: {e}")
        return False


def get_log_by_id(record_id: int):
    """특정 기록 조회 (수정용)"""
    try:
        engine = get_db_engine()
        query = text("SELECT * FROM driving_logs WHERE id = :id")
        import pandas as pd
        df = pd.read_sql(query, engine, params={"id": record_id})
        if not df.empty:
            return df.iloc[0].to_dict()
        return None
    except Exception as e:
        st.error(f"조회 실패: {e}")
        return None