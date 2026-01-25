"""
전역 설정, 테마, 상수 정의
"""
import os

# 경로 설정
APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(APP_DIR)

# 파일 경로
ICON_PATH = os.path.join(PROJECT_ROOT, 'assets', 'logo.ico')
CONFIG_PATH = os.path.join(PROJECT_ROOT, 'config.yaml')
BLOCKED_USERS_FILE = os.path.join(PROJECT_ROOT, 'blocked_users.json')
LOGIN_ATTEMPTS_FILE = os.path.join(PROJECT_ROOT, 'login_attempts.json')

# 로그인 설정
MAX_LOGIN_ATTEMPTS = 5

# Google AI Studio 스타일 팔레트
THEME = {
    "bg_main": "#121212",       
    "bg_sidebar": "#1E1E1E",    
    "text_main": "#FFFFFF",     
    "text_sub": "#9aa0a6",
    "accent_primary": "#8AB4F8",
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