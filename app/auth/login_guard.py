"""
로그인 시도 제한 및 차단 관리
"""
import json
import os
from datetime import datetime
import streamlit as st

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import MAX_LOGIN_ATTEMPTS, BLOCKED_USERS_FILE, LOGIN_ATTEMPTS_FILE


def get_client_ip():
    """클라이언트 IP 주소 가져오기"""
    try:
        if hasattr(st, 'context') and hasattr(st.context, 'headers'):
            headers = dict(st.context.headers)

            # 대소문자 무시하고 검색
            for key, value in headers.items():
                key_lower = key.lower()
                if key_lower == 'x-forwarded-for':
                    return value.split(',')[0].strip()
                if key_lower == 'x-real-ip':
                    return value.strip()
            
            # Host 헤더에서 IP 추출 시도 (최후의 수단)
            host = headers.get('Host', '')
            if host and not any(c.isalpha() for c in host.split(':')[0]):
                return host.split(':')[0]
                
    except Exception as e:
        st.sidebar.write(f"❌ Error: {e}")
    
    return "unknown"


def _load_json(filepath, default=None):
    """JSON 파일 로드"""
    if default is None:
        default = {}
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError):
        pass
    return default


def _save_json(filepath, data):
    """JSON 파일 저장"""
    try:
        # 디렉토리가 없으면 생성
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except IOError as e:
        st.error(f"파일 저장 오류: {e}")


def is_blocked(identifier):
    """차단 여부 확인"""
    blocked = _load_json(BLOCKED_USERS_FILE, {"blocked": []})
    for entry in blocked.get("blocked", []):
        if entry.get("ip") == identifier or entry.get("username") == identifier:
            return True
    return False


def get_login_attempts(identifier):
    """로그인 시도 횟수 조회"""
    attempts = _load_json(LOGIN_ATTEMPTS_FILE, {})
    return attempts.get(identifier, 0)


def increment_login_attempts(identifier, ip="unknown"):
    """로그인 시도 횟수 증가"""
    attempts = _load_json(LOGIN_ATTEMPTS_FILE, {})
    current = attempts.get(identifier, 0) + 1
    attempts[identifier] = current
    _save_json(LOGIN_ATTEMPTS_FILE, attempts)
    return current


def reset_login_attempts(identifier):
    """로그인 시도 횟수 초기화"""
    attempts = _load_json(LOGIN_ATTEMPTS_FILE, {})
    if identifier in attempts:
        del attempts[identifier]
        _save_json(LOGIN_ATTEMPTS_FILE, attempts)


def block_user(identifier, ip="unknown"):
    """사용자/IP 차단"""
    blocked = _load_json(BLOCKED_USERS_FILE, {"blocked": []})
    
    # 이미 차단되어 있는지 확인
    for entry in blocked["blocked"]:
        if entry.get("ip") == identifier:
            return
    
    blocked["blocked"].append({
        "ip": ip,
        "username": identifier,
        "blocked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "reason": f"로그인 {MAX_LOGIN_ATTEMPTS}회 실패"
    })
    _save_json(BLOCKED_USERS_FILE, blocked)


def get_remaining_attempts(identifier):
    """남은 시도 횟수 반환"""
    current = get_login_attempts(identifier)
    return max(0, MAX_LOGIN_ATTEMPTS - current)