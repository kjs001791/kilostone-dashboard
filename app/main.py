"""
KiloStone Dashboard - Main Entry Point
"""
import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import sys
import os

# 경로 설정
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 내부 모듈
from config import ICON_PATH, CONFIG_PATH, THEME, LABEL_MAP, MAX_LOGIN_ATTEMPTS
from styles import get_css
from auth.login_guard import (
    get_client_ip, is_blocked, get_login_attempts,
    increment_login_attempts, reset_login_attempts, block_user
)
from components.sidebar import render_sidebar
from views.overview import render_overview_tab
from views.vehicle import render_vehicle_tab
from views.data_entry import render_data_entry_tab
from services.data_loader import load_data


# -----------------------------------------------------------------------------
# 페이지 설정
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="KiloStone",
    page_icon=ICON_PATH,
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS 적용
st.markdown(get_css(), unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# 헬퍼 함수
# -----------------------------------------------------------------------------
def _is_form_submitted():
    """로그인 폼이 실제로 제출되었는지 확인"""
    for key in st.session_state.keys():
        if 'FormSubmitter' in key and st.session_state.get(key, False):
            return True
    return False


def _show_blocked_message():
    """차단 메시지 표시"""
    st.markdown("""
        <div class="blocked-warning">
            <div class="blocked-icon">🚫</div>
            <div class="blocked-title">접근이 차단되었습니다</div>
            <div class="blocked-message">
                비정상적인 로그인 시도가 감지되어<br>
                해당 IP에서의 접근이 차단되었습니다.<br><br>
                문의: 관리자에게 연락하세요.
            </div>
        </div>
    """, unsafe_allow_html=True)


def _show_locked_message():
    """계정 잠김 메시지"""
    st.markdown("""
        <div class="blocked-warning">
            <div class="blocked-icon">🔒</div>
            <div class="blocked-title">접근이 잠겼습니다</div>
            <div class="blocked-message">
                로그인 시도 횟수를 모두 소진하였습니다.<br>
                관리자에게 문의하여 차단 해제를 요청하세요.
            </div>
        </div>
    """, unsafe_allow_html=True)


def _show_remaining_attempts(remaining):
    """남은 시도 횟수 표시"""
    if remaining <= 2:
        color = THEME['accent_red']
    else:
        color = THEME['accent_yellow']
    
    if remaining == 1:
        message = f"⚠️ 남은 시도 횟수: {remaining}회 (마지막 기회입니다!)"
    else:
        message = f"⚠️ 남은 시도 횟수: {remaining}회"
    
    st.markdown(
        f'<div class="attempts-warning" style="border-color: {color};">'
        f'<span class="attempts-text" style="color: {color};">{message}</span>'
        f'</div>',
        unsafe_allow_html=True
    )


# -----------------------------------------------------------------------------
# 메인 함수
# -----------------------------------------------------------------------------
def main():
    # 설정 로드
    try:
        with open(CONFIG_PATH, encoding='utf-8') as file:
            config = yaml.load(file, Loader=SafeLoader)
    except FileNotFoundError:
        st.error("config.yaml 파일을 찾을 수 없습니다.")
        return
    
    client_ip = get_client_ip()

    # ✅ 1차 방어: IP 차단 확인 (로그인 폼도 안 보여줌)
    if is_blocked(client_ip):
        _show_blocked_message()
        return

    # 인증
    authenticator = stauth.Authenticate(
        config['credentials'],
        config['cookie']['name'],
        config['cookie']['key'],
        config['cookie']['expiry_days']
    )
    
    authenticator.login('main')

    auth_status = st.session_state.get('authentication_status')
    name = st.session_state.get('name')
    username = st.session_state.get('username')
    
    form_submitted = _is_form_submitted()

    # =========================================================================
    # 로그인 실패 처리 (IP 기반으로 카운트)
    # =========================================================================
    if auth_status is False:
        # ✅ IP 기준으로 카운트 (어떤 아이디를 쓰든 IP로 추적)
        if form_submitted:
            current_attempts = increment_login_attempts(client_ip, client_ip)
        else:
            current_attempts = get_login_attempts(client_ip)
        
        remaining = MAX_LOGIN_ATTEMPTS - current_attempts
        
        # 횟수 소진 → 차단
        if remaining <= 0:
            block_user(client_ip, client_ip)
            _show_locked_message()
            return
        
        # 실패 메시지 + 남은 횟수
        st.error('❌ 아이디 또는 비밀번호가 틀렸습니다.')
        _show_remaining_attempts(remaining)
        return
    
    # =========================================================================
    # 대기 상태 (아직 입력 안 함)
    # =========================================================================
    if auth_status is None:
        st.warning('아이디와 비밀번호를 입력해주세요.')
        
        # 이전 실패 기록 있으면 표시
        ip_attempts = get_login_attempts(client_ip)
        if ip_attempts > 0:
            remaining = MAX_LOGIN_ATTEMPTS - ip_attempts
            st.info(f"ℹ️ 현재 IP에서 {ip_attempts}회 실패 / 남은 기회: {remaining}회")
        return

    # =========================================================================
    # ✅ 로그인 성공
    # =========================================================================
    # 성공 시 해당 IP 카운트 초기화
    reset_login_attempts(client_ip)
    
    # 데이터 로드
    df = load_data()
    
    # 사이드바
    with st.sidebar:
        filtered_df, selected_days, resample_option = render_sidebar(df, authenticator, name)
    
    if filtered_df is None:
        return

    # 메인 컨텐츠
    tab1, tab2, tab3 = st.tabs([
        "전체 운행 현황", 
        "차량별 비교 분석",
        "운행기록 관리"
    ])

    with tab1:
        render_overview_tab(df, filtered_df, selected_days, resample_option)

    with tab2:
        render_vehicle_tab(filtered_df)

    with tab3:
        render_data_entry_tab(df)

    # 하단 로그 데이터
    st.divider()
    with st.expander("📋 전체 로그 데이터 확인하기", expanded=True):
        display_df = filtered_df.rename(columns=LABEL_MAP).sort_values(by='날짜', ascending=False)
        st.dataframe(display_df, use_container_width=True, height=400)


if __name__ == "__main__":
    main()