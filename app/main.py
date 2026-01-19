import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sys
import os

# 모듈 경로 설정
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from services.database import get_db_engine

# -----------------------------------------------------------------------------
# 1. 전역 설정 및 상수 정의
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="KILOSTONE",
    page_icon="🚛",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 한글 라벨 매핑 (전역 사용)
LABEL_MAP = {
    "date": "날짜",
    "vehicle_id": "차량 ID",
    "fuel_efficiency": "연비 (km/L)",
    "speed": "평균 속도 (km/h)",
    "time": "운행 시간",
    "distance": "주행 거리 (km)",
    "cumulative_distance": "누적 주행 거리 (km)",
    "consumed_fuel": "연료 소모량 (L)",
    "refuel": "주유량 (L)",
    "reurea": "요소수 (L)"
}

# 다크 테마용 컬러 팔레트 (가시성 확보)
COLORS = {
    "primary": "#00CC96",    # 녹색 (긍정, 연비)
    "danger": "#EF553B",     # 적색 (경고, 소모)
    "info": "#AB63FA",       # 보라 (거리, 속도)
    "warning": "#FFA15A",    # 주황 (주유)
    "bg_mix": "#1F2630"      # 차트 배경색
}

# CSS: 로고 확대 및 스타일링
# CSS: KILOSTONE 로고를 사이드바에 꽉 채우기 위한 강제 스타일링
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Teko:wght@700&display=swap');
    
    /* 1. Streamlit 사이드바의 기본 여백을 강제로 줄임 (핵심) */
    section[data-testid="stSidebar"] div[class*="css"] {
        padding-top: 2rem;
        padding-bottom: 0rem;
        /* 좌우 여백을 줄여서 글자가 들어갈 공간 확보 */
        padding-left: 1rem; 
        padding-right: 1rem;
    }

    /* 2. 로고 텍스트 스타일 */
    .logo-text {
        font-family: 'Teko', sans-serif;
        /* 화면 크기에 반응하지 않고 무조건 거대하게 설정 (Teko는 좁아서 110px은 줘야 꽉 참) */
        font-size: 50px !important;  
        font-weight: 700;
        font-style: italic;
        color: #e0e0e0;
        
        /* 텍스트 정렬 및 배치 */
        text-align: center;
        line-height: 0.8;      /* 줄 간격을 좁혀서 위아래 공백 제거 */
        margin-top: -20px;     /* 위쪽으로 더 바짝 붙이기 */
        margin-bottom: 20px;
        
        /* 텍스트 효과 */
        text-shadow: 5px 5px 0px #000;
        letter-spacing: -1px;  /* 자간을 살짝 좁혀서 단단한 느낌 */
        
        /* 줄바꿈 방지 (글자가 너무 커도 한 줄에 나오게 강제) */
        white-space: nowrap;
    }
    
    /* 기존 메트릭 스타일 유지 */
    div[data-testid="stMetricValue"] {
        font-size: 26px;
        color: #ffffff;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 14px;
        color: #aaaaaa;
    }
    </style>
    """, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. 데이터 로드 함수
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
        
        # 전처리
        df['date'] = pd.to_datetime(df['date'])
        numeric_cols = ['fuel_efficiency', 'speed', 'distance', 'cumulative_distance', 'consumed_fuel', 'refuel']
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        return df
    except Exception as e:
        st.error(f"데이터 로드 중 오류 발생: {e}")
        return pd.DataFrame()

# -----------------------------------------------------------------------------
# 3. 메인 로직
# -----------------------------------------------------------------------------
def main():
    # --- Sidebar ---
    with st.sidebar:
        st.markdown('<p class="logo-text">KILOSTONE</p>', unsafe_allow_html=True)
        st.divider()
        
        df = load_data()
        
        df = load_data()
        if df.empty:
            st.warning("데이터가 없습니다.")
            return

        # 날짜 필터
        min_date, max_date = df['date'].min().date(), df['date'].max().date()
        date_range = st.date_input("📅 분석 기간 설정", value=(min_date, max_date), min_value=min_date, max_value=max_date)
        
        # 성능 최적화를 위한 리샘플링 옵션 (버벅임 해결의 핵심)
        resample_option = st.radio("📊 그래프 상세도 (성능 최적화)", ["일별(Daily)", "주별(Weekly)", "월별(Monthly)"], index=1)
        
        # 데이터 필터링
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start, end = date_range
            filtered_df = df[(df['date'].dt.date >= start) & (df['date'].dt.date <= end)]
        else:
            filtered_df = df

    # --- 데이터 리샘플링 (차트 렌더링 속도 향상용) ---
    chart_df = filtered_df.copy()
    if resample_option == "주별(Weekly)":
        chart_df = chart_df.resample('W-MON', on='date').mean(numeric_only=True).reset_index()
    elif resample_option == "월별(Monthly)":
        chart_df = chart_df.resample('M', on='date').mean(numeric_only=True).reset_index()
    # 일별일 경우 원본 그대로 사용

    # --- KPI Section ---
    st.markdown("### 🚦 핵심 운행 지표")
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    
    with kpi1:
        st.metric(label="총 주행 거리", value=f"{filtered_df['distance'].sum():,.1f} km")
    with kpi2:
        current_eff = filtered_df['fuel_efficiency'].mean()
        st.metric(label="평균 연비", value=f"{current_eff:.2f} km/L")
    with kpi3:
        st.metric(label="총 연료 소모", value=f"{filtered_df['consumed_fuel'].sum():,.0f} L")
    with kpi4:
        last_cum = filtered_df['cumulative_distance'].iloc[-1] if not filtered_df.empty else 0
        st.metric(label="차량 총 누적 거리", value=f"{last_cum:,.0f} km")

    st.markdown("---")

    # --- Charts Section (2x2 Grid) ---
    
    # 공통 차트 설정 함수 (스타일 통일)
    def update_chart_layout(fig, title):
        fig.update_layout(
            title=dict(text=title, font=dict(size=20, color="white")),
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            hovermode="x unified",
            margin=dict(l=20, r=20, t=50, b=20)
        )
        return fig

    c1, c2 = st.columns(2)

    # 1. 연비 추이 (Line)
    with c1:
        fig_eff = px.line(
            chart_df, x='date', y='fuel_efficiency',
            labels=LABEL_MAP, # 한글 라벨 적용
            markers=True if len(chart_df) < 100 else False, # 점이 너무 많으면 선만 표시
        )
        fig_eff.update_traces(line_color=COLORS['primary'], line_width=3)
        # 평균선
        avg_eff = filtered_df['fuel_efficiency'].mean()
        fig_eff.add_hline(y=avg_eff, line_dash="dot", line_color="gray", annotation_text="기간 평균")
        st.plotly_chart(update_chart_layout(fig_eff, "📈 연비 추이 분석"), use_container_width=True)

    # 2. 주행 거리 (Bar) - 가시성 개선
    with c2:
        fig_dist = px.bar(
            chart_df, x='date', y='distance',
            labels=LABEL_MAP,
            color='distance',
            # 기존 Bluered 대신 가시성 좋은 커스텀 컬러 적용
            color_continuous_scale=[[0, COLORS['bg_mix']], [1, COLORS['info']]] 
        )
        st.plotly_chart(update_chart_layout(fig_dist, "🚛 운행 강도 (주행 거리)"), use_container_width=True)

    c3, c4 = st.columns(2)

    # 3. 연료 밸런스 (Area)
    with c3:
        fig_fuel = go.Figure()
        # 주유량 (Bar로 변경하여 더 잘 보이게 함)
        fig_fuel.add_trace(go.Bar(
            x=chart_df['date'], y=chart_df['refuel'],
            name='주유량', marker_color=COLORS['warning'], opacity=0.8
        ))
        # 소모량 (Line + Area)
        fig_fuel.add_trace(go.Scatter(
            x=chart_df['date'], y=chart_df['consumed_fuel'],
            name='소모량', fill='tozeroy', line=dict(color=COLORS['danger'], width=2)
        ))
        fig_fuel.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(update_chart_layout(fig_fuel, "⛽ 연료 소모 vs 주유 패턴"), use_container_width=True)

    # 4. 속도 vs 연비 (Scatter) - 샘플링 필요 (데이터가 너무 많으면 버벅임)
    with c4:
        # 산점도는 원본 데이터를 쓰되, 너무 많으면 최근 500개만 보여주거나 샘플링
        scatter_sample = filtered_df.sample(n=min(500, len(filtered_df))) if len(filtered_df) > 500 else filtered_df
        if not scatter_sample.empty and scatter_sample['speed'].notnull().any():
            fig_corr = px.scatter(
                scatter_sample, x='speed', y='fuel_efficiency',
                size='distance', color='fuel_efficiency',
                labels=LABEL_MAP,
                color_continuous_scale='Viridis', # 밝은 색상 척도
                opacity=0.8
            )
            st.plotly_chart(update_chart_layout(fig_corr, "⚙️ 속도와 연비의 상관관계 (Sampled)"), use_container_width=True)
        else:
            st.info("속도 데이터가 충분하지 않습니다.")

    # --- Raw Data Section ---
    st.subheader("📋 상세 로그 데이터")
    # 컬럼명 한글로 변경하여 표시
    display_df = filtered_df.rename(columns=LABEL_MAP).sort_values(by='날짜', ascending=False)
    st.dataframe(display_df, use_container_width=True, height=300)

if __name__ == "__main__":
    main()