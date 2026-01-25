"""
TAB 2: 차량별 비교 분석
"""
import streamlit as st
import plotly.express as px
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import THEME, LABEL_MAP
from components.charts import create_clean_chart

def render_vehicle_tab(filtered_df):
    """차량별 비교 분석 탭 렌더링"""
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    vehicle_group = filtered_df.groupby('vehicle_id').agg({
        'distance': 'sum',
        'fuel_efficiency': 'mean',
        'consumed_fuel': 'sum',
        'time': 'sum'
    }).reset_index()

    # 차트
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown('<div class="chart-header">차량별 총 주행 거리</div>', unsafe_allow_html=True)
        fig = px.bar(
            vehicle_group, x='vehicle_id', y='distance',
            color='vehicle_id', labels=LABEL_MAP, text_auto='.2s'
        )
        fig.update_traces(textfont_size=12, textangle=0, textposition="outside", cliponaxis=False)
        st.plotly_chart(create_clean_chart(fig), use_container_width=True)

    with col2:
        st.markdown('<div class="chart-header">차량별 평균 연비</div>', unsafe_allow_html=True)
        fig = px.bar(
            vehicle_group, x='vehicle_id', y='fuel_efficiency',
            color='vehicle_id', labels=LABEL_MAP, text_auto='.2f'
        )
        avg_all = vehicle_group['fuel_efficiency'].mean()
        fig.add_hline(y=avg_all, line_dash="dot", line_color=THEME['text_sub'], annotation_text="전체 평균")
        st.plotly_chart(create_clean_chart(fig), use_container_width=True)

    # 상세 테이블
    st.markdown('<div class="chart-header">차량별 상세 데이터</div>', unsafe_allow_html=True)
    st.dataframe(
        vehicle_group.rename(columns=LABEL_MAP).sort_values(by='주행 거리 (km)', ascending=False),
        use_container_width=True
    )