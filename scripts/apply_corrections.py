# Gemini의 제안을 반영하여 전처리가 완료된 최종 데이터 파일 생성
# messy_cleaned + cleaning_proposl_al -> final

import pandas as pd
import os
from pathlib import Path

def apply_corrections():
    # 1. 경로 설정
    current_dir = Path(__file__).resolve().parent
    project_root = current_dir.parent
    
    # 입력 1: 전처리된 원본
    input_csv_path = project_root / 'data' / 'processed' / 'driving_log_2016_2020_messy_cleaned.csv'
    
    # 입력 2: AI 제안 파일 (가장 최근에 생성된 파일명을 여기에 적어주세요)
    # 예: cleaning_proposal_ai_20260118_040233.csv
    proposal_filename = 'cleaning_proposal_ai_20260118_040233.csv' 
    proposal_csv_path = project_root / 'data' / proposal_filename
    
    # 출력: 최종 파일
    output_csv_path = project_root / 'data' / 'processed' / 'driving_log_2016_2020_final.csv'

    # 파일 확인
    if not input_csv_path.exists():
        print(f"❌ 원본 파일을 찾을 수 없습니다: {input_csv_path}")
        return
    if not proposal_csv_path.exists():
        print(f"❌ AI 제안 파일을 찾을 수 없습니다: {proposal_csv_path}")
        return

    # 2. 데이터 로드
    print("📂 데이터 로드 중...")
    df_orig = pd.read_csv(input_csv_path)
    df_prop = pd.read_csv(proposal_csv_path)

    # 3. Manual Check 및 빈 값 제외
    mask_valid = (df_prop['target'] != 'manual_check') & (df_prop['proposed'].notna())
    df_valid = df_prop[mask_valid].copy()
    
    print(f"   - 원본 데이터: {len(df_orig)}행")
    print(f"   - 반영할 수정 제안: {len(df_valid)}건 (Manual Check 제외됨)")

    # 4. 수정 반영 (인덱스 매핑)
    # 원본 데이터에 id 컬럼이 없으면 인덱스를 id로 간주하거나, 미리 id 컬럼을 만들어야 합니다.
    # 여기서는 df_orig의 인덱스가 id와 일치한다고 가정합니다.
    
    success_cnt = 0
    for _, row in df_valid.iterrows():
        try:
            target_id = int(row['id'])
            col_name = row['target']
            new_val = row['proposed']

            if target_id in df_orig.index:
                # 데이터 타입 맞추기 (숫자형인 경우)
                if pd.api.types.is_numeric_dtype(df_orig[col_name]):
                    new_val = float(new_val)
                    if pd.api.types.is_integer_dtype(df_orig[col_name]):
                        new_val = int(new_val)
                
                df_orig.at[target_id, col_name] = new_val
                success_cnt += 1
        except Exception as e:
            print(f"⚠️ ID {row['id']} 수정 중 오류: {e}")

    # 5. 최종 저장
    df_orig.to_csv(output_csv_path, index=False, encoding='utf-8-sig')
    print(f"🎉 수정 완료! {success_cnt}건 반영됨.")
    print(f"💾 저장 위치: {output_csv_path}")

if __name__ == "__main__":
    apply_corrections()