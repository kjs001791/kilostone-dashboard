"""
KiloStone Pipeline - 공유 설정 및 유틸리티
모든 step 모듈이 이 파일에서 상수/함수를 import합니다.
"""

import os
import re
import sys
import pandas as pd
import numpy as np
from pathlib import Path
from dotenv import load_dotenv

# =================================================================
# 경로 설정
# =================================================================
# scripts/pipeline/schema_config.py → parent.parent.parent = project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent.parent

# sys.path 등록 (cross-module import 지원)
for p in [str(PROJECT_ROOT), str(SCRIPTS_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
STAGING_DIR = DATA_DIR / "staging"
PROCESSED_DIR = DATA_DIR / "processed"
BACKUP_DIR = DATA_DIR / "backups"

# 디렉토리 자동 생성
for d in [RAW_DIR, STAGING_DIR, PROCESSED_DIR, BACKUP_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# =================================================================
# 컬럼 매핑
# =================================================================
COLUMN_MAPPING = {
    'date': ['날짜', '일자'],
    'fuel_efficiency': ['연비', '1일 평균연비', '1일평균연비', '평균연비', '연    비', 'km/l'],
    'speed': ['평균 운행속도', '평균운행속도', '평균 운행 속도', 'km/h'],
    'time': ['총 운행시간', '운행시간', '총 운행 시간', '구동시간_TOT', 'h(TOT)'],
    'distance': ['1일 주행거리', '1일주행거리', '총 운행거리', '운행거리', 'km(주행)', '트립미터_TOT', '트립미터 TOT'],
    'cumulative_distance': ['총 주행거리', '총주행거리', '누적주행거리', '누적 운행거리', 'km(누적)'],
    'consumed_fuel': ['1일 연료소모량', '연료소모량', '연비개요_TOT', 'l(TOT)'],
    'refuel': ['연료주입량', '주입량', '연료 주입량', '경유_TOT', 'l(경유)'],
    'reurea': ['요소수_TOT', '요소수주입', '요소수 주입량', 'l(요소수)'],
    # 스카니아 전용 컬럼 매핑
    'fuel_rate_per_hour': ['l/h'],
    'consumed_fuel_idle': ['연비개요_IDL', 'l(IDL)'],
    'consumed_fuel_pto': ['연비개요_PTO', 'l(PTO)'],
    'time_idle': ['구동시간_IDL', 'h(IDL)'],
    'time_pto': ['구동시간_PTO', 'h(PTO)']
}

FINAL_COLUMNS = [
    'date', 'vehicle_id', 'fuel_efficiency', 'speed', 'time',
    'distance', 'cumulative_distance', 'consumed_fuel', 'refuel', 'reurea',
    'fuel_rate_per_hour', 'consumed_fuel_idle', 'consumed_fuel_pto', 'time_idle', 'time_pto'
]


# =================================================================
# 물리적 한계값 (step3 + step5 통합)
# =================================================================
LIMITS = {
    # Step3: 의심 데이터 필터링용
    'PHYS_ERROR_TOLERANCE': 0.20,
    'FUEL_ERROR_TOLERANCE': 0.01,
    'MAX_HOURS_PER_DAY': 16,
    'MAX_SPEED': 110,
    'MAX_DISTANCE': 1000,
    # Step5: 최종 검증용
    'EFFICIENCY_MIN': 1.0, # 1.5 -> 1.0 (대형차 고려 하향)
    'EFFICIENCY_MAX': 6.0, # 5.5 -> 6.0
    'TIME_MAX_HOURS': 22,
    'DIST_CALC_TOLERANCE': 0.25,
}


# =================================================================
# 스키마 시점 정의
# =================================================================
SCHEMA_PERIODS = {
    "period_1": {
        "range": ("2016-01", "2017-05"),
        "vehicle": "MAN TGX",
        "has_fuel": False,
        "has_speed_time": True,
        "has_cumulative": False,
        "notes": "연료/요소수 컬럼 없음, 시간에 '.' 사용",
    },
    "period_2": {
        "range": ("2017-06", "2019-03"),
        "vehicle": "MAN TGX",
        "has_fuel": True,
        "has_speed_time": True,
        "has_cumulative": False,
        "notes": "연료/요소수 추가, 요소수 단위 혼재 (1~9 = 이벤트 카운트)",
    },
    "period_3": {
        "range": ("2019-04", "2023-11"),
        "vehicle": "Daewoo Prima",
        "has_fuel": True,
        "has_speed_time": False,
        "has_cumulative": True,
        "notes": "속도/시간 삭제, 누적거리 추가 (대우프리마 전 기간)",
    },
    "period_4": {
        "range": ("2023-12", "2099-12"),
        "vehicle": "Scania",
        "has_fuel": True,
        "has_speed_time": True,
        "has_cumulative": True,
        "has_scania_extra": True,
        "notes": "스카니아 전용 컬럼(IDL, PTO, l/h) 추가됨",
    },
}


# =================================================================
# API 설정
# =================================================================
API_KEY = os.getenv("GOOGLE_API_KEY")
API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEY}"
    if API_KEY else None
)
CONCURRENCY_LIMIT = 5


# =================================================================
# 공유 유틸리티 함수
# =================================================================
def extract_vehicle_id(df_head):
    """엑셀 상단(A1 주변)에서 차량 정보 추출"""
    try:
        val = str(df_head.columns[0]) + " " + str(df_head.iloc[0, 0])
        if '대우' in val or '프리마' in val: return 'Daewoo Prima'
        if '만' in val or 'MAN' in val: return 'MAN TGX'
        if '스카니아' in val: return 'Scania'
        return 'Unknown Vehicle'
    except:
        return 'Unknown Vehicle'


def fix_time_format(val):
    """시간 문자열 표준화 → HH:MM:SS. Dirty 값도 보존 (나중에 QA에서 탐지)."""
    if pd.isna(val) or str(val).strip() == '' or str(val).strip() == '0':
        return None
    val_str = str(val).strip()
    if ':' in val_str:
        return val_str
    hours, minutes = 0, 0
    match = re.search(r'(\d+)\D+(\d+)', val_str)
    if match:
        hours, minutes = int(match.group(1)), int(match.group(2))
    else:
        try:
            float_val = float(val_str)
            hours = int(float_val)
            decimal_part = round(float_val - hours, 2)
            if decimal_part > 0:
                minutes = int(decimal_part * 100)
        except:
            return None
    return f"{hours:02d}:{minutes:02d}:00"


def clean_numeric(val):
    """숫자 컬럼 정제 (쉼표 등 제거)"""
    if pd.isna(val):
        return None
    s = str(val).replace(',', '').strip()
    try:
        return float(s)
    except:
        return None


def convert_time_to_hours(x):
    """시간 문자열(HH:MM:SS) → 실수(시간) 변환"""
    if pd.isna(x):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    try:
        parts = str(x).strip().split(':')
        if len(parts) == 3:
            return int(parts[0]) + int(parts[1]) / 60 + int(parts[2]) / 3600
        elif len(parts) == 2:
            return int(parts[0]) + int(parts[1]) / 60
        return float(x)
    except:
        return None