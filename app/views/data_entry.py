"""
운행기록 관리 (추가 / 수정 / 삭제)
"""
import streamlit as st
import pandas as pd
import sys
import os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import THEME, LABEL_MAP
from services.data_writer import (
    insert_driving_log, update_driving_log, 
    delete_driving_log, get_log_by_id
)
from services.data_validator import validate_driving_log
from services.backup import create_backup, list_backups, restore_from_backup

def render_data_entry_tab(df):
    """운행기록 관리 탭"""
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    mode = st.radio(
        "작업 선택",
        ["➕ 새 운행기록 추가", "✏️ 운행기록 수정", "🗑️ 운행기록 삭제"],
        horizontal=True
    )
    
    st.divider()
    
    if "추가" in mode:
        _render_add_form()
    elif "수정" in mode:
        _render_edit_form(df)
    elif "삭제" in mode:
        _render_delete_form(df)


def _render_add_form():
    """새 운행기록 추가 폼"""
    
    st.subheader("➕ 새 운행기록 추가")
    
    with st.form("add_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            input_date = st.date_input("날짜", value=date.today())
            vehicle = st.selectbox("차량", ["MAN TGX", "Daewoo Prima"])
            distance = st.number_input("주행거리 (km)", min_value=0.0, step=0.1, format="%.1f")
            consumed_fuel = st.number_input("연료소모량 (L)", min_value=0.0, step=0.01, format="%.2f")
            fuel_eff = st.number_input("연비 (km/L)", min_value=0.0, step=0.01, format="%.2f")
        
        with col2:
            speed = st.number_input("평균속도 (km/h)", min_value=0.0, step=0.1, format="%.1f")
            time_input = st.text_input("운행시간 (HH:MM)", placeholder="예: 08:30")
            cumulative = st.number_input("누적거리 (km)", min_value=0.0, step=0.1, format="%.1f")
            refuel = st.number_input("주유량 (L)", min_value=0.0, step=0.1, format="%.1f")
            reurea = st.number_input("요소수 (L)", min_value=0.0, step=0.1, format="%.1f")
        
        submitted = st.form_submit_button("💾 저장", use_container_width=True)
    
    if submitted:
        data = {
            "date": input_date,
            "vehicle_id": vehicle,
            "distance": distance if distance > 0 else None,
            "consumed_fuel": consumed_fuel if consumed_fuel > 0 else None,
            "fuel_efficiency": fuel_eff if fuel_eff > 0 else None,
            "speed": speed if speed > 0 else None,
            "time": time_input if time_input else None,
            "cumulative_distance": cumulative if cumulative > 0 else None,
            "refuel": refuel if refuel > 0 else None,
            "reurea": reurea if reurea > 0 else None,
        }
        
        # 검증
        warnings = validate_driving_log(data)
        
        if warnings:
            for w in warnings:
                st.warning(w)
            st.info("⚠️ 경고가 있지만 저장하려면 다시 저장 버튼을 누르세요.")
        
        if insert_driving_log(data):
            st.success("✅ 저장 완료!")
            st.cache_data.clear()


def _render_edit_form(df):
    """운행기록 수정 폼"""
    
    st.subheader("✏️ 운행기록 수정")
    
    if df.empty:
        st.warning("데이터가 없습니다.")
        return
    
    # 기록 선택
    st.markdown("**수정할 기록 검색**")
    
    col_search1, col_search2 = st.columns(2)
    with col_search1:
        search_date = st.date_input(
            "날짜 선택", 
            value=df['date'].max().date(),
            key="edit_date"
        )
    with col_search2:
        search_vehicle = st.selectbox(
            "차량 선택", 
            df['vehicle_id'].unique(),
            key="edit_vehicle"
        )
    
    # 해당 날짜+차량의 기록 조회
    mask = (
        (df['date'].dt.date == search_date) & 
        (df['vehicle_id'] == search_vehicle)
    )
    matched = df[mask]
    
    if matched.empty:
        st.info("해당 날짜/차량의 기록이 없습니다.")
        return
    
    # id 컬럼이 있어야 수정 가능
    if 'id' not in matched.columns:
        st.error("ID 컬럼이 없습니다. data_loader.py에서 id를 포함해야 합니다.")
        return
    
    record_id = matched.iloc[0]['id']
    record = matched.iloc[0]
    
    st.markdown(f"**기록 ID: {int(record_id)}**")
    
    with st.form("edit_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            input_date = st.date_input("날짜", value=record['date'].date())
            vehicle = st.selectbox(
                "차량", ["MAN TGX", "Daewoo Prima"],
                index=0 if record['vehicle_id'] == "MAN TGX" else 1
            )
            distance = st.number_input(
                "주행거리 (km)", value=float(record.get('distance', 0) or 0),
                min_value=0.0, step=0.1, format="%.1f"
            )
            consumed_fuel = st.number_input(
                "연료소모량 (L)", value=float(record.get('consumed_fuel', 0) or 0),
                min_value=0.0, step=0.01, format="%.2f"
            )
            fuel_eff = st.number_input(
                "연비 (km/L)", value=float(record.get('fuel_efficiency', 0) or 0),
                min_value=0.0, step=0.01, format="%.2f"
            )
        
        with col2:
            speed = st.number_input(
                "평균속도 (km/h)", value=float(record.get('speed', 0) or 0),
                min_value=0.0, step=0.1, format="%.1f"
            )
            time_val = str(record.get('time', '') or '')
            time_input = st.text_input("운행시간 (HH:MM)", value=time_val)
            cumulative = st.number_input(
                "누적거리 (km)", value=float(record.get('cumulative_distance', 0) or 0),
                min_value=0.0, step=0.1, format="%.1f"
            )
            refuel = st.number_input(
                "주유량 (L)", value=float(record.get('refuel', 0) or 0),
                min_value=0.0, step=0.1, format="%.1f"
            )
            reurea = st.number_input(
                "요소수 (L)", value=float(record.get('reurea', 0) or 0),
                min_value=0.0, step=0.1, format="%.1f"
            )
        
        submitted = st.form_submit_button("💾 수정 저장", use_container_width=True)
    
    if submitted:
        data = {
            "date": input_date,
            "vehicle_id": vehicle,
            "distance": distance if distance > 0 else None,
            "consumed_fuel": consumed_fuel if consumed_fuel > 0 else None,
            "fuel_efficiency": fuel_eff if fuel_eff > 0 else None,
            "speed": speed if speed > 0 else None,
            "time": time_input if time_input else None,
            "cumulative_distance": cumulative if cumulative > 0 else None,
            "refuel": refuel if refuel > 0 else None,
            "reurea": reurea if reurea > 0 else None,
        }
        
        warnings = validate_driving_log(data)
        if warnings:
            for w in warnings:
                st.warning(w)
        
        if update_driving_log(int(record_id), data):
            st.success("✅ 수정 완료!")
            st.cache_data.clear()


def _render_delete_form(df):
    """운행기록 삭제"""
    
    st.subheader("🗑️ 운행기록 삭제")
    
    if df.empty:
        st.warning("데이터가 없습니다.")
        return
    
    col_search1, col_search2 = st.columns(2)
    with col_search1:
        search_date = st.date_input(
            "날짜 선택",
            value=df['date'].max().date(),
            key="del_date"
        )
    with col_search2:
        search_vehicle = st.selectbox(
            "차량 선택",
            df['vehicle_id'].unique(),
            key="del_vehicle"
        )
    
    mask = (
        (df['date'].dt.date == search_date) & 
        (df['vehicle_id'] == search_vehicle)
    )
    matched = df[mask]
    
    if matched.empty:
        st.info("해당 날짜/차량의 기록이 없습니다.")
        return
    
    if 'id' not in matched.columns:
        st.error("ID 컬럼이 없습니다.")
        return
    
    display_cols = ['id', 'date', 'vehicle_id', 'distance', 'fuel_efficiency', 'consumed_fuel']
    available_cols = [c for c in display_cols if c in matched.columns]
    st.dataframe(matched[available_cols], use_container_width=True)
    
    record_id = int(matched.iloc[0]['id'])
    
    st.error(f"⚠️ 기록 ID {record_id}을 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.")
    
    if st.button("🗑️ 삭제 확인", type="primary"):
        if delete_driving_log(record_id):
            st.success("✅ 삭제 완료!")
            st.cache_data.clear()

def render_data_entry_tab(df):
    """운행기록 관리 탭"""
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    mode = st.radio(
        "작업 선택",
        ["➕ 새 운행기록 추가", "✏️ 운행기록 수정", "🗑️ 운행기록 삭제", "💾 백업/복구"],
        horizontal=True
    )
    
    st.divider()
    
    if "추가" in mode:
        _render_add_form()
    elif "수정" in mode:
        _render_edit_form(df)
    elif "삭제" in mode:
        _render_delete_form(df)
    elif "백업" in mode:
        _render_backup_ui()


def _render_backup_ui():
    """백업/복구 UI"""
    
    st.subheader("💾 백업 / 복구")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 백업 생성")
        if st.button("📦 지금 백업하기", use_container_width=True):
            filepath = create_backup()
            st.success(f"✅ 백업 완료!\n{filepath}")
    
    with col2:
        st.markdown("### 백업 목록")
        backups = list_backups()
        
        if not backups:
            st.info("백업 파일이 없습니다.")
        else:
            for b in backups[:10]:  # 최근 10개만
                st.text(f"📄 {b['filename']} ({b['size_kb']}KB) - {b['created']}")
    
    # 복구
    st.divider()
    st.markdown("### ⚠️ 복구 (위험)")
    st.error("복구 시 현재 DB의 모든 데이터가 백업 시점으로 되돌아갑니다.")
    
    backups = list_backups()
    if backups:
        selected = st.selectbox(
            "복구할 백업 선택",
            options=[b['filename'] for b in backups]
        )
        
        confirm = st.text_input("복구하려면 'RESTORE'를 입력하세요")
        
        if st.button("🔄 복구 실행") and confirm == "RESTORE":
            filepath = next(b['filepath'] for b in backups if b['filename'] == selected)
            restore_from_backup(filepath)
            st.success("✅ 복구 완료!")
            st.cache_data.clear()