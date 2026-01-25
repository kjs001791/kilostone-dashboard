"""
사이드바 컴포넌트
"""
import streamlit as st
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import THEME


def render_sidebar(df, authenticator, name):
    """사이드바 렌더링 및 필터 값 반환"""
    
    st.markdown('<p class="logo-text">KILOSTONE</p>', unsafe_allow_html=True)
    st.write(f"환영합니다, **{name}**님!")
    authenticator.logout('로그아웃', 'sidebar')
    st.divider()

    if df.empty:
        st.warning("데이터가 없습니다.")
        return None, None, None

    # 기간 설정
    st.markdown(
        f"<p style='color:{THEME['text_main']}; font-weight:500; margin-top:20px;'>기간 설정</p>", 
        unsafe_allow_html=True
    )
    min_date = df['date'].min().date()
    max_date = df['date'].max().date()
    date_range = st.date_input(
        "", 
        value=(min_date, max_date), 
        min_value=min_date, 
        max_value=max_date, 
        label_visibility="collapsed"
    )
    
    # 보기 방식
    st.markdown(
        f"<br><p style='color:{THEME['text_main']}; font-weight:500;'>보기 방식</p>", 
        unsafe_allow_html=True
    )
    resample_option = st.radio(
        "", 
        ["일별 (Daily)", "주별 (Weekly)", "월별 (Monthly)"], 
        index=1, 
        label_visibility="collapsed"
    )
    
    st.divider()
    st.markdown(
        f"<div style='text-align:center; color:{THEME['text_sub']}; font-size:12px;'>Connected to Server</div>", 
        unsafe_allow_html=True
    )

    # 필터링된 데이터 반환
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
        filtered_df = df[(df['date'].dt.date >= start) & (df['date'].dt.date <= end)]
        selected_days = (end - start).days + 1
    else:
        filtered_df = df
        selected_days = 1

    return filtered_df, selected_days, resample_option