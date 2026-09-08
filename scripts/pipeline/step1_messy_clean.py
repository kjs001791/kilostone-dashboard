"""
Step 1: Messy Data 정제
Excel 시트를 읽어서 컬럼 매핑, 타입 변환, 유령 데이터 제거 후 표준 CSV 출력.
"""

import sys
import warnings
from pathlib import Path

import pandas as pd

# pipeline 패키지 import 보장
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.schema_config import (
    COLUMN_MAPPING, FINAL_COLUMNS, STAGING_DIR,
    extract_vehicle_id, fix_time_format, clean_numeric,
)

warnings.filterwarnings("ignore")


# =================================================================
# 시트 처리
# =================================================================
def process_sheet(file_path, sheet_name):
    """시트 하나를 읽어서 표준 포맷으로 변환"""
    try:
        # 상단 20줄을 읽어 양식 판별 및 헤더 위치 탐색
        df_scan = pd.read_excel(file_path, sheet_name=sheet_name, header=None, nrows=20)
    except Exception:
        return None

    vehicle_id = extract_vehicle_id(df_scan)
    is_scania = '스카니아' in str(df_scan.values)

    # 헤더 행 탐지 ('날짜' 키워드 위치)
    header_idx = -1
    for i, row in df_scan.iterrows():
        row_str = " ".join([str(x) for x in row.values])
        if '날짜' in row_str:
            header_idx = i
            break
    
    if header_idx == -1:
        return None

    # 스카니아 양식 (3중 헤더) 처리
    if is_scania:
        # 헤더 3줄 읽기
        headers_raw = pd.read_excel(file_path, sheet_name=sheet_name, header=None, 
                                   skiprows=header_idx, nrows=3)
        
        # [수정] 헤더 줄 수가 부족하면 처리 불가하므로 스킵
        if len(headers_raw) < 1:
            return None
            
        # 헤더 병합 (Level1_Level2_Level3)
        headers_raw = headers_raw.fillna('')
        combined_headers = []
        num_rows = len(headers_raw)
        
        for col in range(len(headers_raw.columns)):
            l1 = str(headers_raw.iloc[0, col]).strip() if num_rows >= 1 else ''
            l2 = str(headers_raw.iloc[1, col]).strip() if num_rows >= 2 else ''
            l3 = str(headers_raw.iloc[2, col]).strip() if num_rows >= 3 else ''
            
            # 상위 헤더 전방 채우기 (Merged Cell 대응)
            if l1 == '' and col > 0:
                curr_idx = col
                while curr_idx > 0 and l1 == '':
                    curr_idx -= 1
                    l1 = str(headers_raw.iloc[0, curr_idx]).strip()
            
            full_name = f"{l1}_{l2}_{l3}".strip('_')
            combined_headers.append(full_name)
        
        # 실제 데이터 로드
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=None, skiprows=header_idx + 3)
        
        if df.empty:
            return None

        # [핵심 수정] 열 개수 불일치 강제 조정 (Length mismatch 방지)
        if len(df.columns) > len(combined_headers):
            df = df.iloc[:, :len(combined_headers)]
        elif len(df.columns) < len(combined_headers):
            combined_headers = combined_headers[:len(df.columns)]
        
        df.columns = combined_headers
    else:
        # 기존 일반 양식
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_idx)

    # 컬럼 매핑 (고급 매핑 로직)
    new_cols = {}
    for col in df.columns:
        col_clean = str(col).strip().replace('\n', '').replace(' ', '')
        matched = False
        # 1. 정확히 일치하는 alias 검색
        for std_col, aliases in COLUMN_MAPPING.items():
            for alias in aliases:
                alias_clean = alias.replace(' ', '')
                # 스카니아 복합 헤더의 경우 alias가 포함되어 있는지 확인
                if alias_clean in col_clean:
                    # 'km'이 'km/h'나 'km/l'에 걸리는 것 방지 (우선순위 처리)
                    if alias_clean in ['km', 'l', 'h'] and ('km/h' in col_clean or 'km/l' in col_clean or 'l/h' in col_clean):
                        continue
                    
                    if std_col not in new_cols.values():
                        new_cols[col] = std_col
                        matched = True
                        break
            if matched: break
            
    df = df.rename(columns=new_cols)

    # 필요한 컬럼만 추출 및 누락 컬럼 보충
    for col in FINAL_COLUMNS:
        if col not in df.columns:
            df[col] = None
    df = df[FINAL_COLUMNS]

    # 행 정제
    df = df.dropna(subset=['date'])
    # 날짜 형식 처리 (엑셀 날짜 또는 문자열)
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date'])
    df['vehicle_id'] = vehicle_id

    # 숫자/시간 정제
    num_cols = [c for c in FINAL_COLUMNS if c not in ['date', 'vehicle_id', 'time', 'time_idle', 'time_pto', 'source', 'created_at']]
    for col in num_cols:
        df[col] = df[col].apply(clean_numeric)
    
    # 시간 형식 정제 (TOT, IDL, PTO 모두)
    for col in ['time', 'time_idle', 'time_pto']:
        if col in df.columns:
            df[col] = df[col].apply(fix_time_format)

    return df


# =================================================================
# Step 1 메인
# =================================================================
def step1_clean_messy(input_path_str, test_mode=False):
    """
    Excel(파일 또는 폴더) → 표준 CSV 변환.
    중복된 날짜/차량 데이터는 하나만 남기고 제거합니다.
    """
    print("\n" + "=" * 60)
    print("📋 STEP 1: Messy Data 정제")
    print("=" * 60)

    input_path = Path(input_path_str)
    tag = "_TEST" if test_mode else ""
    output_path = STAGING_DIR / f"messy_cleaned{tag}.csv"

    # 파일 목록 추출
    files = []
    if input_path.is_file():
        files.append(input_path)
    elif input_path.is_dir():
        # [수정] ~$ 로 시작하는 임시 파일 무시
        files = [f for f in input_path.glob("*.xls*") if not f.name.startswith("~$")]
        files.sort()
    
    if not files:
        print(f"❌ 읽을 수 있는 엑셀 파일이 없습니다: {input_path}")
        sys.exit(1)

    print(f"📂 총 {len(files)}개 파일 처리 시작...")
    
    all_data = []
    for file_path in files:
        print(f"  📄 파일: {file_path.name}")
        try:
            xls = pd.ExcelFile(file_path)
            for sheet in xls.sheet_names:
                processed = process_sheet(file_path, sheet)
                if processed is not None and not processed.empty:
                    all_data.append(processed)
                    print(f"    ✅ 시트: {sheet} ({len(processed)} rows)")
        except Exception as e:
            print(f"    ❌ 파일 읽기 실패: {e}")

    if not all_data:
        print("❌ 처리할 데이터가 없습니다.")
        sys.exit(1)

    final_df = pd.concat(all_data, ignore_index=True)

    # 1. 유령 데이터 제거
    before_clean = len(final_df)
    numeric_targets = [c for c in ['distance', 'refuel', 'reurea', 'consumed_fuel']
                       if c in final_df.columns]
    mask_no_numeric = (final_df[numeric_targets].fillna(0) == 0).all(axis=1)

    if 'time' in final_df.columns:
        mask_no_time = (final_df['time'].isna()
                        | (final_df['time'].astype(str).str.strip() == '0'))
    else:
        mask_no_time = True

    final_df = final_df[~(mask_no_numeric & mask_no_time)]
    
    # 2. 중복 데이터 제거 (날짜 + 차량ID 기준)
    # 여러 파일에 걸쳐 있는 동일 날짜 데이터 중 하나만 남김
    final_df = final_df.sort_values(by=['date', 'vehicle_id', 'distance'], ascending=[True, True, False])
    before_dup = len(final_df)
    final_df = final_df.drop_duplicates(subset=['date', 'vehicle_id'], keep='first')
    
    removed_phantom = before_clean - before_dup
    removed_dups = before_dup - len(final_df)
    
    print(f"🧹 정제 결과:")
    print(f"  - 초기 행수: {before_clean}")
    print(f"  - 유령 데이터 제거: -{removed_phantom}건")
    print(f"  - 날짜 중복 제거: -{removed_dups}건")
    print(f"  - 최종 행수: {len(final_df)}")

    final_df = final_df.sort_values(by='date')
    final_df.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"✅ STEP 1 완료: {output_path}")
    return output_path


# =================================================================
# 단독 테스트
# =================================================================
if __name__ == "__main__":
    from pipeline.schema_config import RAW_DIR

    test_input = RAW_DIR / "driving_log_2016_2020.xlsx"
    if test_input.exists():
        step1_clean_messy(test_input, test_mode=True)
    else:
        print(f"❌ 테스트 파일 없음: {test_input}")