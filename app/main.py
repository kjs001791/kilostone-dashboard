import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sys
import os

# 모듈 경로 설정
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from services.database import get_db_engine

# 1. 현재 파일(main.py)이 있는 폴더 경로 구하기
current_dir = os.path.dirname(os.path.abspath(__file__))

# 2. 한 단계 상위 폴더(프로젝트 루트)로 이동
project_root = os.path.dirname(current_dir)

# 3. assets 폴더와 파일명 합치기
icon_path = os.path.join(project_root, 'assets', 'logo.ico')

# -----------------------------------------------------------------------------
# 1. 전역 설정 및 상수 정의
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="KiloStone",
    page_icon=icon_path,
    layout="wide",
    initial_sidebar_state="expanded"
)

# Google AI Studio 스타일 팔레트
THEME = {
    "bg_main": "#121212",       
    "bg_sidebar": "#1E1E1E",    
    "text_main": "#FFFFFF",     
    "text_sub": "#9aa0a6",      # 구글 특유의 회색 텍스트
    "accent_primary": "#8AB4F8", # 구글 블루
    "accent_green": "#81C995",  
    "accent_red": "#F28B82",    
    "accent_yellow": "#FDD663", 
    "border": "#3C4043"         
}

# 한글 라벨 매핑
LABEL_MAP = {
    "date": "날짜",
    "vehicle_id": "차량 ID",
    "fuel_efficiency": "연비 (km/L)",
    "speed": "평균 속도 (km/h)",
    "time": "운행 시간 (분)",
    "distance": "주행 거리 (km)",
    "cumulative_distance": "누적 주행 거리 (km)",
    "consumed_fuel": "연료 소모량 (L)",
    "refuel": "주유량 (L)",
    "reurea": "요소수 (L)"
}

# -----------------------------------------------------------------------------
# 2. CSS 스타일링 (Flat & Clean Design)
# -----------------------------------------------------------------------------
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Teko:wght@700&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap');

    /* [기본] 전체 폰트 및 배경 설정 */
    .stApp {{
        background-color: {THEME['bg_main']};
        font-family: 'Roboto', sans-serif;
    }}
    
    /* [사이드바] */
    [data-testid="stSidebar"] {{
        background-color: {THEME['bg_sidebar']};
        border-right: 1px solid {THEME['border']};
        width: 235px !important;
    }}
    div[data-testid="stSidebar"] > div:nth-child(2) {{ display: none; }}
    
    .logo-text {{
        font-family: 'Teko', sans-serif; 
        font-size: 40px !important; 
        font-weight: 700;
        font-style: italic; color: #e0e0e0; text-align: center; line-height: 0.8;
        margin-top: -10px; margin-bottom: 20px;
        letter-spacing: -1px; white-space: nowrap;
    }}

    /* [탭 디자인] 구글 스타일 (심플한 밑줄) */
    .stTabs [data-baseweb="tab-list"] {{
        background-color: transparent;
        border-bottom: 1px solid {THEME['border']};
        gap: 24px;
        padding-bottom: 0px;
    }}
    
    .stTabs [data-baseweb="tab"] {{
        height: 40px;
        background-color: transparent;
        border: none;
        color: {THEME['text_sub']};
        font-size: 14px;
        font-weight: 500;
        padding: 0 0 10px 0;
    }}

    /* 선택된 탭 텍스트 색상만 변경 (밑줄은 아래 highlight가 담당) */
    .stTabs [aria-selected="true"] {{
        color: #8AB4F8 !important; 
        /* border-bottom 삭제함: 고정된 줄이 아니라 움직이는 줄을 쓸 것이므로 */
    }}
    
    /* [핵심] Streamlit의 움직이는 애니메이션 바(Highlight) 색상 변경 */
    div[data-baseweb="tab-highlight"] {{
        background-color: #8AB4F8 !important; /* 기본 빨간색 -> 파란색 변경 */
    }}
    
    .stTabs [data-baseweb="tab"]:hover {{
        color: {THEME['text_main']};
    }}

    /* [KPI 컨테이너] Streamlit Native Container 스타일링 */
    /* st.container(border=True)의 테두리와 배경색을 변경 */
    [data-testid="stVerticalBlockBorderWrapper"] {{
        background-color: #1E1E1E; /* 카드 배경색 */
        border: 1px solid #3C4043;
        border-radius: 12px;
        padding: 20px;
    }}

    /* KPI 텍스트 스타일 */
    .kpi-title {{
        color: {THEME['text_sub']};
        font-size: 14px;
        margin-bottom: 4px;
        text-align: center;
    }}
    
    .kpi-value {{
        color: {THEME['text_main']};
        font-size: 32px;
        font-weight: 700;
        text-align: center;
        white-space: nowrap;
    }}
    
    .kpi-delta {{
        font-size: 13px;
        margin-top: 4px;
        text-align: center;
        display: flex;
        justify-content: center;
        gap: 5px;
    }}

    /* 차트 제목 스타일 (박스 밖) */
    .chart-header {{
        color: {THEME['text_sub']};
        font-size: 16px;
        font-weight: 500;
        margin-bottom: 10px;
        margin-top: 20px;
        padding-left: 5px;
        border-left: 3px solid {THEME['accent_primary']};
        line-height: 1;
    }}

    /* 데이터프레임 */
    [data-testid="stDataFrame"] {{
        background-color: transparent;
    }}
    
    /* 구분선 */
    hr {{
        border-color: {THEME['border']};
    }}
    </style>
    """, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 3. 데이터 로드 함수
# -----------------------------------------------------------------------------
@st.cache_data(ttl=600)
def load_data():
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
        
        if 'time' in df.columns:
            time_td = pd.to_timedelta(df['time'].astype(str), errors='coerce')
            time_num = pd.to_numeric(df['time'], errors='coerce')
            df['time_minutes'] = time_td.dt.total_seconds() / 60
            df['time_minutes'] = df['time_minutes'].fillna(time_num).fillna(0)
            df['time'] = df['time_minutes']
        
        numeric_cols = ['fuel_efficiency', 'speed', 'distance', 'cumulative_distance', 'consumed_fuel', 'refuel']
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
        return df
    except Exception as e:
        st.error(f"데이터 로드 중 오류 발생: {e}")
        return pd.DataFrame()

# -----------------------------------------------------------------------------
# 4. 차트 헬퍼 함수 (박스 제거, 깔끔한 배경)
# -----------------------------------------------------------------------------
def create_clean_chart(fig, height=300):
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", # 투명 배경
        plot_bgcolor="rgba(0,0,0,0)",  # 투명 배경
        height=height,
        margin=dict(l=0, r=0, t=20, b=20), # 여백 최소화
        xaxis=dict(showgrid=False, color=THEME['text_sub'], gridcolor=THEME['border']),
        yaxis=dict(showgrid=True, gridcolor=THEME['border'], color=THEME['text_sub'], zeroline=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color=THEME['text_sub'])),
        hovermode="x unified"
    )
    return fig

# -----------------------------------------------------------------------------
# 5. 메인 로직
# -----------------------------------------------------------------------------
def main():
    with st.sidebar:
        st.markdown('<p class="logo-text">KILOSTONE</p>', unsafe_allow_html=True)
        
        df = load_data()
        
        if df.empty:
            st.warning("데이터가 없습니다.")
            return

        st.markdown(f"<p style='color:{THEME['text_main']}; font-weight:500; margin-top:20px;'>기간 설정</p>", unsafe_allow_html=True)
        min_date, max_date = df['date'].min().date(), df['date'].max().date()
        date_range = st.date_input("", value=(min_date, max_date), min_value=min_date, max_value=max_date, label_visibility="collapsed")
        
        st.markdown(f"<br><p style='color:{THEME['text_main']}; font-weight:500;'>보기 방식</p>", unsafe_allow_html=True)
        resample_option = st.radio("", ["일별 (Daily)", "주별 (Weekly)", "월별 (Monthly)"], index=1, label_visibility="collapsed")
        
        st.divider()
        st.markdown(f"<div style='text-align:center; color:{THEME['text_sub']}; font-size:12px;'>Connected to Server</div>", unsafe_allow_html=True)

        if isinstance(date_range, tuple) and len(date_range) == 2:
            start, end = date_range
            filtered_df = df[(df['date'].dt.date >= start) & (df['date'].dt.date <= end)]
            selected_days = (end - start).days + 1
        else:
            filtered_df = df
            selected_days = 1

    # --- Main Content ---
    # 헤더 제거하고 바로 탭으로 시작하여 공간 효율 극대화
    
    # 탭 메뉴
    tab1, tab2 = st.tabs(["전체 운행 현황", "차량별 비교 분석"])

    # -------------------------------------------------------------------------
    # TAB 1: 전체 운행 현황
    # -------------------------------------------------------------------------
    with tab1:
        # 데이터 리샘플링
        chart_df = filtered_df.copy()
        if "주별" in resample_option:
            chart_df = chart_df.resample('W-MON', on='date').mean(numeric_only=True).reset_index()
        elif "월별" in resample_option:
            chart_df = chart_df.resample('M', on='date').mean(numeric_only=True).reset_index()

        # --- KPI Section (Streamlit Native Container 사용 - 반응형 완벽 지원) ---
        # 억지로 높이를 맞추지 않고 내용물에 따라 늘어나게 함
        st.markdown("<br>", unsafe_allow_html=True) # 상단 여백
        
        kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)
        
        # KPI 렌더링 함수 (Native Container 안에 HTML 주입)
        def render_kpi(container, title, value, delta_val=None, delta_suffix=""):
            with container:
                # [중요] border=True 옵션 사용: Streamlit이 알아서 크기 조절해주는 박스 생성
                with st.container(border=True):
                    delta_html = ""
                    if delta_val is not None:
                        color = THEME['accent_green'] if delta_val >= 0 else THEME['accent_red']
                        sign = "▲" if delta_val >= 0 else "▼"
                        delta_html = f"<span style='color:{color}'>{sign} {abs(delta_val):.2f}{delta_suffix}</span>"
                    
                    st.markdown(f"""
                        <div class="kpi-title">{title}</div>
                        <div class="kpi-value">{value}</div>
                        <div class="kpi-delta">{delta_html}</div>
                    """, unsafe_allow_html=True)

        # KPI 계산
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
        if total_minutes > 60:
            time_str = f"{int(total_minutes // 60):,}시간" # 예: 11,432시간
        else:
            time_str = f"{int(total_minutes)}분"
        delta_time = curr_daily_time - avg_daily_time_all
        render_kpi(kpi_col3, "총 운행 시간", time_str, delta_time)

        # KPI 4: 총 연료 소모량
        delta_fuel = curr_daily_fuel - avg_daily_fuel_all
        render_kpi(kpi_col4, "총 연료 소모량", f"{filtered_df['consumed_fuel'].sum():,.0f} L", delta_fuel)

        st.divider() # 구분선

        # --- Charts Section (박스 없이 깔끔하게 배치) ---
        
        col_row1_1, col_row1_2 = st.columns(2)

        with col_row1_1:
            st.markdown('<div class="chart-header">연비 추이</div>', unsafe_allow_html=True)
            fig_eff = px.line(chart_df, x='date', y='fuel_efficiency', labels=LABEL_MAP, markers=True if len(chart_df) < 50 else False)
            fig_eff.update_traces(line_color=THEME['accent_green'], line_width=3)
            avg_eff = filtered_df['fuel_efficiency'].mean()
            fig_eff.add_hline(y=avg_eff, line_dash="dot", line_color=THEME['text_sub'], annotation_text="평균")
            st.plotly_chart(create_clean_chart(fig_eff), use_container_width=True)

        with col_row1_1:
            st.markdown('<div class="chart-header">연비 추이</div>', unsafe_allow_html=True)
            
            # 연비가 0보다 큰 데이터만 필터링하여 저장
            valid_eff_df = chart_df[chart_df['fuel_efficiency'] > 0]
            
            # 데이터가 존재하는 경우에만 시각화
            if not valid_eff_df.empty:
                fig_eff = px.line(valid_eff_df, x='date', y='fuel_efficiency', labels=LABEL_MAP, markers=True if len(valid_eff_df) < 50 else False)
                fig_eff.update_traces(line_color=THEME['accent_green'], line_width=3)
                
                # 평균선 강조 및 수치 표시
                avg_eff = valid_eff_df['fuel_efficiency'].mean()
                fig_eff.add_hline(
                    y=avg_eff, 
                    line_dash="dash", 
                    line_color=THEME['accent_red'], # 눈에 띄는 색(빨강)으로 변경
                    line_width=2,
                    annotation_text=f"평균: {avg_eff:.2f} km/L", # 값 직접 표시
                    annotation_position="top left",
                    annotation_font=dict(size=14, color=THEME['accent_red']) # 폰트 키움
                )
                st.plotly_chart(create_clean_chart(fig_eff), use_container_width=True)
            else:
                st.info("표시할 연비 데이터가 없습니다.")

        with col_row1_2:
            st.markdown('<div class="chart-header">주행 거리 추이</div>', unsafe_allow_html=True)
            
            fig_dist = px.bar(chart_df, x='date', y='distance', labels=LABEL_MAP)
            fig_dist.update_traces(marker_color=THEME['accent_primary'], marker_line_width=0)
            
            # 추세선(이동 평균선) 추가 (데이터가 3개 이상일 때만)
            if len(chart_df) >= 3:
                # 3구간 이동 평균 계산
                trend_data = chart_df['distance'].rolling(window=3, min_periods=1, center=True).mean()
                fig_dist.add_trace(go.Scatter(
                    x=chart_df['date'], 
                    y=trend_data, 
                    mode='lines', 
                    name='추세(Trend)', 
                    line=dict(color='white', width=2, dash='dot') # 흰색 점선으로 추세 표시
                ))
            
            st.plotly_chart(create_clean_chart(fig_dist), use_container_width=True)

        col_row2_1, col_row2_2 = st.columns(2)

        with col_row2_1:
            st.markdown('<div class="chart-header">주유량 대비 연료 소모량</div>', unsafe_allow_html=True)
            fig_fuel = go.Figure()
            fig_fuel.add_trace(go.Bar(x=chart_df['date'], y=chart_df['refuel'], name='주유량', marker_color=THEME['accent_yellow'], opacity=0.8))
            fig_fuel.add_trace(go.Scatter(
                x=chart_df['date'], y=chart_df['consumed_fuel'], name='소모량', fill='tozeroy', 
                line=dict(color=THEME['accent_red'], width=2), fillcolor=f"rgba(242, 139, 130, 0.2)"
            ))
            
            # 기본 차트 생성 후 레이아웃 업데이트
            final_fig_fuel = create_clean_chart(fig_fuel)
            
            # 범례 위치를 우상단(기본)에서 좌상단으로 강제 이동
            final_fig_fuel.update_layout(
                legend=dict(
                    orientation="h", 
                    yanchor="top", y=1.1, # 차트 위쪽
                    xanchor="left", x=0   # 왼쪽 정렬
                )
            )
            st.plotly_chart(final_fig_fuel, use_container_width=True)

        with col_row2_2:
            st.markdown('<div class="chart-header">속도와 연비의 상관관계</div>', unsafe_allow_html=True)
            scatter_sample = filtered_df.sample(n=min(500, len(filtered_df))) if len(filtered_df) > 500 else filtered_df.copy()
            
            if not scatter_sample.empty:
                scatter_sample['distance'] = scatter_sample['distance'].fillna(0)
            
            # 속도가 0보다 큰 데이터만 유효 데이터로 인정 (0인 데이터 제외)
            valid_scatter = scatter_sample[
                (scatter_sample['speed'].notnull()) & 
                (scatter_sample['speed'] > 0)
            ]

            if not valid_scatter.empty:
                fig_corr = px.scatter(
                    valid_scatter, x='speed', y='fuel_efficiency',
                    size='distance', 
                    labels=LABEL_MAP,
                    opacity=0.7
                )
                fig_corr.update_traces(marker=dict(color=THEME['accent_green'], line=dict(width=1, color=THEME['bg_sidebar'])))
                st.plotly_chart(create_clean_chart(fig_corr), use_container_width=True)
            else:
                st.info("유효한 상관관계 데이터(속도 > 0)가 부족합니다.")

    # -------------------------------------------------------------------------
    # TAB 2: 차량별 비교 분석
    # -------------------------------------------------------------------------
    with tab2:
        st.markdown("<br>", unsafe_allow_html=True)
        vehicle_group = filtered_df.groupby('vehicle_id').agg({
            'distance': 'sum',
            'fuel_efficiency': 'mean',
            'consumed_fuel': 'sum',
            'time': 'sum'
        }).reset_index()

        c_v1, c_v2 = st.columns(2)
        with c_v1:
            st.markdown('<div class="chart-header">차량별 총 주행 거리</div>', unsafe_allow_html=True)
            fig_v_dist = px.bar(
                vehicle_group, x='vehicle_id', y='distance',
                color='vehicle_id',
                labels=LABEL_MAP,
                text_auto='.2s'
            )
            fig_v_dist.update_traces(textfont_size=12, textangle=0, textposition="outside", cliponaxis=False)
            st.plotly_chart(create_clean_chart(fig_v_dist), use_container_width=True)

        with c_v2:
            st.markdown('<div class="chart-header">차량별 평균 연비</div>', unsafe_allow_html=True)
            fig_v_eff = px.bar(
                vehicle_group, x='vehicle_id', y='fuel_efficiency',
                color='vehicle_id',
                labels=LABEL_MAP,
                text_auto='.2f'
            )
            avg_all_eff = vehicle_group['fuel_efficiency'].mean()
            fig_v_eff.add_hline(y=avg_all_eff, line_dash="dot", line_color=THEME['text_sub'], annotation_text="전체 평균")
            st.plotly_chart(create_clean_chart(fig_v_eff), use_container_width=True)

        # 차량별 상세 데이터 (박스 없음)
        st.markdown('<div class="chart-header">차량별 상세 데이터</div>', unsafe_allow_html=True)
        st.dataframe(
            vehicle_group.rename(columns=LABEL_MAP).sort_values(by='주행 거리 (km)', ascending=False),
            use_container_width=True
        )

    # 공통: 하단 원본 데이터 로그
    st.divider()
    with st.expander("📋 전체 로그 데이터 확인하기", expanded=True):
        display_df = filtered_df.rename(columns=LABEL_MAP).sort_values(by='날짜', ascending=False)
        st.dataframe(display_df, use_container_width=True, height=400)

if __name__ == "__main__":
    main()