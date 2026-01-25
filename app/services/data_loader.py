"""
데이터베이스 데이터 로드
"""
import streamlit as st
import pandas as pd
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.database import get_db_engine


@st.cache_data(ttl=600)
def load_data():
    """운행 데이터 로드"""
    try:
        engine = get_db_engine()
        query = """
        SELECT date, vehicle_id, fuel_efficiency, speed, time, 
               distance, cumulative_distance, consumed_fuel, refuel, reurea 
        FROM driving_logs 
        ORDER BY date ASC
        """
        df = pd.read_sql(query, engine)
        df['date'] = pd.to_datetime(df['date'])
        
        # 시간 변환
        if 'time' in df.columns:
            time_td = pd.to_timedelta(df['time'].astype(str), errors='coerce')
            time_num = pd.to_numeric(df['time'], errors='coerce')
            df['time_minutes'] = time_td.dt.total_seconds() / 60
            df['time_minutes'] = df['time_minutes'].fillna(time_num).fillna(0)
            df['time'] = df['time_minutes']
        
        # 숫자 변환
        numeric_cols = ['fuel_efficiency', 'speed', 'distance', 'cumulative_distance', 'consumed_fuel', 'refuel']
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
        return df
    except Exception as e:
        st.error(f"데이터 로드 중 오류 발생: {e}")
        return pd.DataFrame()