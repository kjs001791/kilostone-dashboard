import pandas as pd
import os
import re
import warnings
from pathlib import Path

# 경고 메시지 숨기기
warnings.filterwarnings("ignore")

# =========================================================
# 1. 설정: 타겟 스키마와 엑셀 컬럼 매핑 (Schema Mapping)
# =========================================================
# DB에 저장할 '표준 컬럼명': [엑셀에서 발견되는 '다양한 이름들']
COLUMN_MAPPING = {
    'date': ['날짜', '일자'],
    'fuel_efficiency': ['연비', '1일 평균연비', '1일평균연비', '평균연비', '연    비'],
    'speed': ['평균 운행속도', '평균운행속도', '평균 운행 속도'],
    'time': ['총 운행시간', '운행시간', '총 운행 시간'],
    # [주의] 2019.05 이전 '총 운행거리'는 일일 거리임. 2019.05 이후 '총 주행거리'는 누적 거리임.
    'distance': ['1일 주행거리', '1일주행거리', '총 운행거리', '운행거리'], 
    'cumulative_distance': ['총 주행거리', '총주행거리', '누적주행거리', '누적 운행거리'],
    'consumed_fuel': ['연료 소모량', '1일 연료소모량', '소모량', '연료소모량'],
    'refuel': ['연료주입량', '주입량', '연료 주입량'],
    'reurea': ['요소수', '요소수주입', '요소수 주입량']
}

# 최종적으로 생성할 컬럼 순서
FINAL_COLUMNS = [
    'date', 'vehicle_id', 'fuel_efficiency', 'speed', 'time', 
    'distance', 'cumulative_distance', 'consumed_fuel', 'refuel', 'reurea'
]

# =========================================================
# 2. 유틸리티 함수: 데이터 정제 로직 (Cleaning Logic)
# =========================================================

def extract_vehicle_id(df_head):
    """엑셀 상단(A1 주변)에서 차량 번호나 차종 정보를 추출"""
    text = df_head.to_string()
    # 예: '만 트렉터', '대우프리마', 'Scania' 등을 식별
    # 실제로는 A1 셀 값을 가져오는 것이 가장 정확함
    try:
        # 첫 번째 컬럼의 이름이나 첫 번째 셀 값을 확인
        val = str(df_head.columns[0]) + " " + str(df_head.iloc[0,0])
        if '대우' in val or '프리마' in val: return 'Daewoo Prima'
        if '만' in val or 'MAN' in val: return 'MAN TGX'
        if '스카니아' in val: return 'Scania'
        return 'Unknown Vehicle' # 나중에 수동 보정 가능
    except:
        return 'Unknown Vehicle'

import re

def fix_time_format(val):
    """
    [수정 버전] 유효성 검사를 제거한 형태 변환 함수
    - 목표: Dirty Data도 그대로 보존한다.
    - 입력: "14. 90", "25:10"
    - 출력: "14:90:00", "25:10:00" (문자열로 반환)
    """
    if pd.isna(val) or str(val).strip() == '' or str(val).strip() == '0':
        return None
    
    val_str = str(val).strip()
    
    # 1. 이미 : 가 포함된 경우 (이미 문자열 포맷임)
    # 내용이 "25:00"이어도 그대로 둡니다. 나중에 QA에서 잡기 위해.
    if ':' in val_str:
        return val_str

    hours = 0
    minutes = 0

    # 2. 정규표현식으로 숫자 추출
    # "13. 30", "14,,20" 등 특수문자가 섞인 경우
    match = re.search(r'(\d+)\D+(\d+)', val_str)

    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
    else:
        # 3. 정규식 실패 -> 실수형(float) 또는 단순 숫자 문자열일 가능성 (예: 14.45)
        try:
            float_val = float(val_str)
            hours = int(float_val)
            
            # 소수점 아래를 분으로 변환 (0.45 -> 45)
            decimal_part = round(float_val - hours, 2)
            if decimal_part > 0:
                minutes = int(decimal_part * 100)
        except:
            # 도저히 해석 불가능한 값 (예: "휴무", "정비")
            return None

    # [핵심 변경] 유효성 검사(24시, 60분 제한) 삭제!
    # 25시나 90분이 나와도 그대로 문자열로 찍어냅니다.
    # CSV에는 "25:10:00", "14:90:00" 으로 저장됩니다. -> 이후 QA에서 적발 가능
    return f"{hours:02d}:{minutes:02d}:00"

def clean_numeric(val):
    """숫자 컬럼에 섞인 문자 제거 (쉼표 등)"""
    if pd.isna(val): return None
    s = str(val).replace(',', '').strip()
    try:
        return float(s)
    except:
        return None

def process_sheet(file_path, sheet_name):
    """시트 하나를 읽어서 표준 포맷으로 변환"""
    # 1. 헤더 위치 찾기 위해 앞부분만 읽기
    try:
        df_raw = pd.read_excel(file_path, sheet_name=sheet_name, header=None, nrows=20)
    except:
        return None

    # 차량 정보 추출 (A1 셀 가정)
    vehicle_id = extract_vehicle_id(df_raw)

    # '날짜'가 있는 행 찾기 (Header Detection)
    header_idx = -1
    for i, row in df_raw.iterrows():
        row_str = " ".join([str(x) for x in row.values])
        if '날짜' in row_str:
            header_idx = i
            break
    
    if header_idx == -1:
        print(f"  [Skip] 날짜 헤더 없음: {sheet_name}")
        return None

    # 2. 실제 데이터 읽기
    df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_idx)
    
    # 3. 컬럼 매핑 (Renaming)
    new_cols = {}
    for col in df.columns:
        col_clean = str(col).strip().replace('\n', '').replace(' ', '')
        for std_col, aliases in COLUMN_MAPPING.items():
            for alias in aliases:
                if alias.replace(' ', '') in col_clean:
                    # 중복 매핑 방지
                    if std_col not in new_cols.values():
                        new_cols[col] = std_col
                    break
    
    df = df.rename(columns=new_cols)
    
    # 4. 필요한 컬럼만 남기고, 없는 컬럼은 None으로 추가
    for col in FINAL_COLUMNS:
        if col not in df.columns:
            df[col] = None
            
    df = df[FINAL_COLUMNS] # 순서 정렬

    # 5. 데이터 정제 (Row-level Cleaning)
    # 5-1. 날짜 없는 행(빈 행, 합계 행) 제거
    df = df.dropna(subset=['date'])
    # 5-2. 날짜 형식이 아닌 것 제거 (예: '합계', '비고' 등 텍스트가 날짜 열에 있는 경우)
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date'])
    
    # 5-3. 차량 ID 할당
    df['vehicle_id'] = vehicle_id
    
    # 5-4. 숫자 데이터 정제
    num_cols = ['fuel_efficiency', 'speed', 'distance', 'cumulative_distance', 'consumed_fuel', 'refuel', 'reurea']
    for col in num_cols:
        df[col] = df[col].apply(clean_numeric)
        
    # 5-5. 시간 데이터 정제 (14.45 -> Time)
    df['time'] = df['time'].apply(fix_time_format)

    # 5-6. 요소수(reurea) 처리 (사용자 요청: 입력된 값 그대로 유지하되 숫자화)
    # 현재 로직에서는 clean_numeric으로 처리되므로 1은 1.0으로 저장됨.
    # 나중에 1 -> 20L 변환 로직이 필요하면 여기서 추가.

    return df

# =========================================================
# 3. 메인 실행 로직
# =========================================================
def main():
    current_dir = Path(__file__).resolve().parent

    project_root = current_dir.parent

    input_file = project_root / 'data' / 'raw' / 'driving_log_2016_2020.xlsx'

    output_dir = project_root / 'data' / 'processed'
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir /  'driving_log_2016_2020_cleaned.csv'
    
    
    print(f"전처리 시작")
    print(f"입력 경로: {input_file}")
    print(f"출력 경로: {output_file}")
    
    if not input_file.exists():
        print(f"오류: 원본 파일을 찾을 수 없습니다. ({input_file})")
        return

    try:
        # pathlib 객체도 pandas에서 바로 읽을 수 있음
        xls = pd.ExcelFile(input_file)
    except Exception as e:
        print(f"파일 열기 실패: {e}")
        return

    all_data = []
    
    for sheet in xls.sheet_names:
        print(f"  Processing Sheet: {sheet}...", end=" ")
        processed_df = process_sheet(input_file, sheet)
        
        if processed_df is not None and not processed_df.empty:
            all_data.append(processed_df)
            print(f"✅ OK ({len(processed_df)} rows)")
        else:
            print("⚠️ No Data")

    if all_data:
        final_df = pd.concat(all_data, ignore_index=True)

        # ---------------------------------------------------------
        # [최종 수정] Ghost Data(유령 데이터) 제거 로직
        # 목표: 운행(거리), 주유, 요소수, 시간 기록이 '단 하나라도' 있으면 살린다.
        # ---------------------------------------------------------
        before_count = len(final_df)
        
        # 1. 숫자형 활동 컬럼들 (거리, 주유량, 요소수량, 소모량)
        numeric_targets = ['distance', 'refuel', 'reurea', 'consumed_fuel']
        # 현재 데이터프레임에 실제로 존재하는 컬럼만 골라냄 (에러 방지)
        valid_numeric_cols = [c for c in numeric_targets if c in final_df.columns]
        
        # [판단 1] 숫자 데이터가 모두 없거나(NaN) 0인 행 찾기
        # fillna(0) -> 비어있는 값을 0으로 채움
        # (df == 0).all(axis=1) -> 가로로 한 줄씩 봤을 때 전부 0이면 True
        mask_no_numeric = (final_df[valid_numeric_cols].fillna(0) == 0).all(axis=1)
        
        # 2. 시간 활동 컬럼 (문자열일 수 있음)
        if 'time' in final_df.columns:
            # [판단 2] 시간 데이터가 비어있거나 0인 경우
            # 문자열 '0', 숫자 0, NaN 모두 체크
            mask_no_time = final_df['time'].isna() | (final_df['time'] == 0) | (final_df['time'].astype(str).str.strip() == '0')
        else:
            # 시간 컬럼 자체가 없으면(옛날 데이터), 시간 활동은 없는 것으로 간주
            mask_no_time = True

        # 3. 최종 삭제 결정 (AND 조건)
        # 숫자 활동도 없고(True) AND 시간 활동도 없으면(True) -> 삭제 대상(True)
        drop_mask = mask_no_numeric & mask_no_time
        
        # 삭제 대상이 아닌 것(~)만 남김
        final_df = final_df[~drop_mask]
        
        after_count = len(final_df)
        print(f"🧹 '활동 없는 유령 데이터' 제거: {before_count} -> {after_count} ({before_count - after_count}건 삭제됨)")

        # 날짜순 정렬
        final_df = final_df.sort_values(by='date')
        
        # CSV 저장
        final_df.to_csv(output_file, index=False, encoding='utf-8-sig')

        print("\n" + "="*50)
        print(f"전처리 완료: {output_file}")
        print(f"총 데이터 건수: {len(final_df)}행")
        print("="*50)
        print(final_df.head()) # 미리보기
    else:
        print("\n저장할 데이터가 없습니다.")

if __name__ == "__main__":
    main()