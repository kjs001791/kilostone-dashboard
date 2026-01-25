"""
TAB 1: 전체 운행 현황
"""
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import THEME, LABEL_MAP
from components.charts import create_clean_chart
from components.kpi_cards import render_kpi


def render_overview_tab(df, filtered_df, selected_days, resample_option):
    """전체 운행 현황 탭 렌더링"""
    
    # 데이터 리샘플링
    chart_df = filtered_df.copy()
    if "주별" in resample_option:
        chart_df = chart_df.resample('W-MON', on='date').mean(numeric_only=True).reset_index()
    elif "월별" in resample_option:
        chart_df = chart_df.resample('M', on='date').mean(numeric_only=True).reset_index()

    # --- KPI Section ---
    st.markdown("<br>", unsafe_allow_html=True)
    _render_kpi_section(df, filtered_df, selected_days)
    
    st.divider()
    
    # --- Charts Section ---
    _render_charts_section(chart_df, filtered_df)


def _render_kpi_section(df, filtered_df, selected_days):
    """KPI 카드 섹션"""
    kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)
    
    # 계산
    total_days = (df['date'].max() - df['date'].min()).days + 1
    
    avg_daily_dist_all = df['distance'].sum() / total_days
    curr_daily_dist = filtered_df['distance'].sum() / selected_days
    
    avg_daily_time_all = df['time'].sum() / total_days
    curr_daily_time = filtered_df['time'].sum() / selected_days
    
    avg_daily_fuel_all = df['consumed_fuel'].sum() / total_days
    curr_daily_fuel = filtered_df['consumed_fuel'].sum() / selected_days

    # KPI 1: 평균 연비
    current_eff = filtered_df['fuel_efficiency'].mean()
    delta_eff = current_eff - df['fuel_efficiency'].mean()
    render_kpi(kpi_col1, "평균 연비", f"{current_eff:.2f} km/L", delta_eff)

    # KPI 2: 총 주행 거리
    delta_dist = curr_daily_dist - avg_daily_dist_all
    render_kpi(kpi_col2, "총 주행 거리", f"{filtered_df['distance'].sum():,.0f} km", delta_dist)

    # KPI 3: 총 운행 시간
    total_minutes = filtered_df['time'].sum()
    time_str = f"{int(total_minutes // 60):,}시간" if total_minutes > 60 else f"{int(total_minutes)}분"
    delta_time = curr_daily_time - avg_daily_time_all
    render_kpi(kpi_col3, "총 운행 시간", time_str, delta_time)

    # KPI 4: 총 연료 소모량
    delta_fuel = curr_daily_fuel - avg_daily_fuel_all
    render_kpi(kpi_col4, "총 연료 소모량", f"{filtered_df['consumed_fuel'].sum():,.0f} L", delta_fuel)


def _render_charts_section(chart_df, filtered_df):
    """차트 섹션"""
    
    # Row 1
    col1, col2 = st.columns(2)
    
    with col1:
        _render_efficiency_chart(chart_df)
    
    with col2:
        _render_distance_chart(chart_df)
    
    # Row 2
    col3, col4 = st.columns(2)
    
    with col3:
        _render_fuel_chart(chart_df)
    
    with col4:
        _render_correlation_chart(filtered_df)


def _render_efficiency_chart(chart_df):
    """연비 추이 차트"""
    st.markdown('<div class="chart-header">연비 추이</div>', unsafe_allow_html=True)
    
    valid_df = chart_df[chart_df['fuel_efficiency'] > 0]
    
    if not valid_df.empty:
        fig = px.line(
            valid_df, x='date', y='fuel_efficiency', 
            labels=LABEL_MAP, 
            markers=len(valid_df) < 50
        )
        fig.update_traces(line_color=THEME['accent_green'], line_width=3)
        
        avg_eff = valid_df['fuel_efficiency'].mean()
        fig.add_hline(
            y=avg_eff, 
            line_dash="dash", 
            line_color=THEME['accent_red'],
            line_width=2,
            annotation_text=f"평균: {avg_eff:.2f} km/L",
            annotation_position="top left",
            annotation_font=dict(size=14, color=THEME['accent_red'])
        )
        st.plotly_chart(create_clean_chart(fig), use_container_width=True)
    else:
        st.info("표시할 연비 데이터가 없습니다.")


def _render_distance_chart(chart_df):
    """주행 거리 추이 차트"""
    st.markdown('<div class="chart-header">주행 거리 추이</div>', unsafe_allow_html=True)
    
    fig = px.bar(chart_df, x='date', y='distance', labels=LABEL_MAP)
    fig.update_traces(marker_color=THEME['accent_primary'], marker_line_width=0)
    
    if len(chart_df) >= 3:
        trend = chart_df['distance'].rolling(window=3, min_periods=1, center=True).mean()
        fig.add_trace(go.Scatter(
            x=chart_df['date'], y=trend, 
            mode='lines', name='추세(Trend)',
            line=dict(color='white', width=2, dash='dot')
        ))
    
    st.plotly_chart(create_clean_chart(fig), use_container_width=True)


def _render_fuel_chart(chart_df):
    """주유량 대비 연료 소모량 차트"""
    st.markdown('<div class="chart-header">주유량 대비 연료 소모량</div>', unsafe_allow_html=True)
    
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=chart_df['date'], y=chart_df['refuel'], 
        name='주유량', marker_color=THEME['accent_yellow'], opacity=0.8
    ))
    fig.add_trace(go.Scatter(
        x=chart_df['date'], y=chart_df['consumed_fuel'], 
        name='소모량', fill='tozeroy',
        line=dict(color=THEME['accent_red'], width=2),
        fillcolor="rgba(242, 139, 130, 0.2)"
    ))
    
    final_fig = create_clean_chart(fig)
    final_fig.update_layout(
        legend=dict(orientation="h", yanchor="top", y=1.1, xanchor="left", x=0)
    )
    st.plotly_chart(final_fig, use_container_width=True)


def _render_correlation_chart(filtered_df):
    """속도-연비 상관관계 차트"""
    st.markdown('<div class="chart-header">속도와 연비의 상관관계</div>', unsafe_allow_html=True)
    
    sample = filtered_df.sample(n=min(500, len(filtered_df))) if len(filtered_df) > 500 else filtered_df.copy()
    
    if not sample.empty:
        sample['distance'] = sample['distance'].fillna(0)
    
    valid = sample[(sample['speed'].notnull()) & (sample['speed'] > 0)]

    if not valid.empty:
        fig = px.scatter(
            valid, x='speed', y='fuel_efficiency',
            size='distance', labels=LABEL_MAP, opacity=0.7
        )
        fig.update_traces(marker=dict(
            color=THEME['accent_green'], 
            line=dict(width=1, color=THEME['bg_sidebar'])
        ))
        st.plotly_chart(create_clean_chart(fig), use_container_width=True)
    else:
        st.info("유효한 상관관계 데이터(속도 > 0)가 부족합니다.")