"""
KPI 카드 컴포넌트
"""
import streamlit as st
from ..config import THEME


def render_kpi(container, title, value, delta_val=None, delta_suffix=""):
    """KPI 카드 렌더링"""
    with container:
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