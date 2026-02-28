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
        df_raw = pd.read_excel(file_path, sheet_name=sheet_name, header=None, nrows=20)
    except Exception:
        return None

    vehicle_id = extract_vehicle_id(df_raw)

    # 헤더 행 탐지 ('날짜' 키워드)
    header_idx = -1
    for i, row in df_raw.iterrows():
        row_str = " ".join([str(x) for x in row.values])
        if '날짜' in row_str:
            header_idx = i
            break
    if header_idx == -1:
        return None

    df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_idx)

    # 컬럼 매핑
    new_cols = {}
    for col in df.columns:
        col_clean = str(col).strip().replace('\n', '').replace(' ', '')
        for std_col, aliases in COLUMN_MAPPING.items():
            for alias in aliases:
                if alias.replace(' ', '') in col_clean:
                    if std_col not in new_cols.values():
                        new_cols[col] = std_col
                    break
    df = df.rename(columns=new_cols)

    # 누락 컬럼 보충
    for col in FINAL_COLUMNS:
        if col not in df.columns:
            df[col] = None
    df = df[FINAL_COLUMNS]

    # 행 정제
    df = df.dropna(subset=['date'])
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date'])
    df['vehicle_id'] = vehicle_id

    # 숫자/시간 정제
    num_cols = ['fuel_efficiency', 'speed', 'distance',
                'cumulative_distance', 'consumed_fuel', 'refuel', 'reurea']
    for col in num_cols:
        df[col] = df[col].apply(clean_numeric)
    df['time'] = df['time'].apply(fix_time_format)

    return df


# =================================================================
# Step 1 메인
# =================================================================
def step1_clean_messy(input_file, test_mode=False):
    """
    Excel → 표준 CSV 변환.
    Returns: 출력 파일 경로 (Path)
    """
    print("\n" + "=" * 60)
    print("📋 STEP 1: Messy Data 정제")
    print("=" * 60)

    input_path = Path(input_file)
    tag = "_TEST" if test_mode else ""
    output_path = STAGING_DIR / f"messy_cleaned{tag}.csv"

    xls = pd.ExcelFile(input_path)
    all_data = []

    for sheet in xls.sheet_names:
        print(f"  Processing: {sheet}...", end=" ")
        processed = process_sheet(input_path, sheet)
        if processed is not None and not processed.empty:
            all_data.append(processed)
            print(f"✅ ({len(processed)} rows)")
        else:
            print("⚠️ Skip")

    if not all_data:
        print("❌ 처리할 데이터가 없습니다.")
        sys.exit(1)

    final_df = pd.concat(all_data, ignore_index=True)

    # 유령 데이터 제거
    before = len(final_df)
    numeric_targets = [c for c in ['distance', 'refuel', 'reurea', 'consumed_fuel']
                       if c in final_df.columns]
    mask_no_numeric = (final_df[numeric_targets].fillna(0) == 0).all(axis=1)

    if 'time' in final_df.columns:
        mask_no_time = (final_df['time'].isna()
                        | (final_df['time'].astype(str).str.strip() == '0'))
    else:
        mask_no_time = True

    final_df = final_df[~(mask_no_numeric & mask_no_time)]
    removed = before - len(final_df)
    print(f"🧹 유령 데이터 제거: {before} → {len(final_df)} ({removed}건)")

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