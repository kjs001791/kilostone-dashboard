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
    increment_login_attempts, reset_login_attempts
)
from components.sidebar import render_sidebar
from views.overview import render_overview_tab
from views.vehicle import render_vehicle_tab
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

    # IP 차단 확인
    if is_blocked(client_ip) and client_ip != "unknown":
        _show_blocked_message()
        return

    # 인증
    authenticator = stauth.Authenticate(
        config['credentials'],
        config['cookie']['name'],
        config['cookie']['key'],
        config['cookie']['expiry_days']
    )
    
    prev_auth_status = st.session_state.get('authentication_status')
    authenticator.login('main')

    auth_status = st.session_state.get('authentication_status')
    name = st.session_state.get('name')
    username = st.session_state.get('username')

    # 로그인 실패
    if auth_status is False:
        _handle_login_failure(client_ip, prev_auth_status)
        return
    
    # 대기 상태
    if auth_status is None:
        st.warning('아이디와 비밀번호를 입력해주세요.')
        ip_attempts = get_login_attempts(client_ip)
        if ip_attempts > 0:
            remaining = MAX_LOGIN_ATTEMPTS - ip_attempts
            st.info(f"ℹ️ 현재 IP에서 {ip_attempts}회 실패 / 남은 기회: {remaining}회")
        return

    # ✅ 로그인 성공
    if username:
        reset_login_attempts(username)
    reset_login_attempts(client_ip)
    
    # 데이터 로드
    df = load_data()
    
    # 사이드바
    with st.sidebar:
        filtered_df, selected_days, resample_option = render_sidebar(df, authenticator, name)
    
    if filtered_df is None:
        return

    # 메인 컨텐츠
    tab1, tab2 = st.tabs(["전체 운행 현황", "차량별 비교 분석"])

    with tab1:
        render_overview_tab(df, filtered_df, selected_days, resample_option)

    with tab2:
        render_vehicle_tab(filtered_df)

    # 하단 로그 데이터
    st.divider()
    with st.expander("📋 전체 로그 데이터 확인하기", expanded=True):
        display_df = filtered_df.rename(columns=LABEL_MAP).sort_values(by='날짜', ascending=False)
        st.dataframe(display_df, use_container_width=True, height=400)


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


def _handle_login_failure(client_ip, prev_auth_status):
    """로그인 실패 처리"""
    attempted_username = st.session_state.get('username', client_ip)
    identifier = attempted_username if attempted_username else client_ip
    
    if is_blocked(identifier):
        st.markdown("""
            <div class="blocked-warning">
                <div class="blocked-icon">🚫</div>
                <div class="blocked-title">계정이 잠겼습니다</div>
                <div class="blocked-message">
                    로그인 시도 횟수를 초과하여 계정 접근이 차단되었습니다.<br>
                    관리자에게 문의하세요.
                </div>
            </div>
        """, unsafe_allow_html=True)
        return
    
    if prev_auth_status is None or prev_auth_status is True:
        current_attempts = increment_login_attempts(identifier, client_ip)
    else:
        current_attempts = get_login_attempts(identifier)
    
    remaining = MAX_LOGIN_ATTEMPTS - current_attempts
    
    if remaining <= 0:
        st.markdown("""
            <div class="blocked-warning">
                <div class="blocked-icon">🔒</div>
                <div class="blocked-title">계정이 잠겼습니다</div>
                <div class="blocked-message">
                    로그인 시도 횟수를 모두 소진하였습니다.<br>
                    관리자에게 문의하여 차단 해제를 요청하세요.
                </div>
            </div>
        """, unsafe_allow_html=True)
    else:
        st.error('❌ 아이디 또는 비밀번호가 틀렸습니다.')
        
        if remaining <= 3:
            color = THEME['accent_red'] if remaining <= 2 else THEME['accent_yellow']
            st.markdown(f"""
                <div class="attempts-warning" style="border-color: {color};">
                    <span class="attempts-text" style="color: {color};">
                        ⚠️ 남은 시도 횟수: {remaining}회 
                        {'(마지막 기회입니다!)' if remaining == 1 else ''}
                    </span>
                </div>
            """, unsafe_allow_html=True)
        else:
            st.info(f"ℹ️ 남은 시도 횟수: {remaining}회")


if __name__ == "__main__":
    main()