import pandas as pd
from pathlib import Path
import os

def categorize_action(action_str):
    """
    로그 메시지(action)를 분석하여 유형(Category)을 분류하는 함수
    """
    if pd.isna(action_str):
        return "기타"
    
    if "[수동확인]" in action_str:
        return "1_수동확인(심각한_오류)"
    elif "자릿수" in action_str:
        return "2_자릿수_변경(Decimal)"
    elif "시간" in action_str:
        return "3_시간_오류(Time)"
    elif "요소수" in action_str:
        return "4_요소수_정규화(Urea)"
    elif "연비 재계산" in action_str:
        return "5_단순_연비_재계산"
    else:
        return "6_기타_수정"

def main():
    # =========================================================
    # 1. 파일 경로 설정
    # =========================================================
    current_dir = Path(__file__).resolve().parent
    project_root = current_dir.parent
    data_dir = project_root / 'data'
    
    # 입력 파일 경로
    report_file_path = data_dir / 'cleaning_report.csv'
    # Messy만 처리된(Dirty 처리 전) 상태의 파일 경로
    # (사용자가 명시한 파일명: cleaning_messy_2016_2020.csv가 없다면 driving_log_2016_2020_cleaned.csv 확인 필요)
    cleaned_file_path = data_dir / 'processed' / 'driving_log_2016_2020_cleaned.csv' 
    
    # 출력 파일 경로
    output_file_path = data_dir / 'analysis_report.csv'

    print("🚀 분석 리포트 생성 시작...")
    
    # 파일 존재 여부 확인
    if not report_file_path.exists():
        print(f"❌ Report 파일이 없습니다: {report_file_path}")
        return
    if not cleaned_file_path.exists():
        print(f"❌ Data 파일이 없습니다: {cleaned_file_path}")
        return

    # =========================================================
    # 2. 데이터 로드 및 전처리
    # =========================================================
    df_report = pd.read_csv(report_file_path)
    df_data = pd.read_csv(cleaned_file_path)

    # 날짜 형식 통일 (String 매칭을 위해)
    df_report['date'] = df_report['date'].astype(str)
    df_data['date'] = df_data['date'].astype(str)

    # =========================================================
    # 3. 유형 분류 (Categorization)
    # =========================================================
    # action 컬럼을 보고 category 컬럼 생성
    df_report['category'] = df_report['action'].apply(categorize_action)

    # =========================================================
    # 4. 데이터 병합 (Merge)
    # =========================================================
    # report에 있는 날짜와 차량ID를 기준으로 원본 데이터(df_data)를 붙임
    # inner join을 사용하여 리포트에 있는 행만 남김
    merged_df = pd.merge(
        df_report, 
        df_data, 
        on=['date', 'vehicle_id'], 
        how='left' # 리포트 기준으로 데이터 조회
    )

    # =========================================================
    # 5. 컬럼 정리 및 정렬
    # =========================================================
    # 분석에 필요한 컬럼만, 보기 좋은 순서로 배치
    target_columns = [
        'category',         # 분류 (가장 중요)
        'date',             # 날짜
        'vehicle_id',       # 차량
        'action',           # 수정 내역 (무엇을 어떻게 바꿨나)
        'status',           # 상태
        'distance',         # [원본] 거리
        'consumed_fuel',    # [원본] 연료
        'fuel_efficiency',  # [원본] 연비
        'time',             # [원본] 시간
        'speed',            # [원본] 속도
        'reurea'            # [원본] 요소수
    ]
    
    # 데이터에 없는 컬럼이 있을 경우를 대비해 교집합만 선택
    final_cols = [c for c in target_columns if c in merged_df.columns]
    final_df = merged_df[final_cols]

    # 정렬: 카테고리별 -> 날짜별
    final_df = final_df.sort_values(by=['category', 'date'])

    # =========================================================
    # 6. 저장
    # =========================================================
    final_df.to_csv(output_file_path, index=False, encoding='utf-8-sig')
    
    print("\n" + "="*50)
    print(f"📊 분석용 파일 생성 완료: {output_file_path}")
    print(f"   총 {len(final_df)}건의 오류 케이스가 정리되었습니다.")
    print("="*50)
    
    # 미리보기 출력 (카테고리별 개수)
    print("\n[유형별 발생 건수]")
    print(final_df['category'].value_counts())

if __name__ == "__main__":
    main()