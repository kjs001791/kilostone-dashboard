import pandas as pd
import numpy as np
from pathlib import Path

# ---------------------------------------------------------
# 설정: 임계값 (Thresholds)
# ---------------------------------------------------------
LIMITS = {
    'SPEED_MAX': 110,           # 트럭 최고 속도 제한 (km/h)
    'EFFICIENCY_MIN': 1.5,      # 최소 연비 (짐 가득 실었을 때)
    'EFFICIENCY_MAX': 5.5,      # 최대 연비 (내리막/공차)
    'TIME_MAX_HOURS': 20,       # 하루 최대 운전 시간 (물리적 한계)
    'DIST_CALC_TOLERANCE': 0.20 # 물리적 계산 오차 허용범위 (20%)
}

def convert_time_to_hours(x):
    """ 시간 문자열('HH:MM:SS')을 실수(Hour)로 변환 """
    try:
        if pd.isna(x): return None
        if isinstance(x, (int, float)): return float(x)
        parts = str(x).split(':')
        if len(parts) == 3:
            return int(parts[0]) + int(parts[1])/60 + int(parts[2])/3600
        elif len(parts) == 2:
            return int(parts[0]) + int(parts[1])/60
        return float(x)
    except:
        return None

def run_dirty_check():
    # 1. 파일 경로 설정
    current_dir = Path(__file__).resolve().parent
    project_root = current_dir.parent
    input_path = project_root / 'data' / 'processed' / 'driving_log_2016_2020_final.csv'
    output_report_path = project_root / 'data' / 'processed' / 'final_dirty_report.csv'

    if not input_path.exists():
        print(f"❌ 파일을 찾을 수 없습니다: {input_path}")
        return

    print("🔍 최종 데이터 건전성 점검(Dirty Check) 시작...")
    df = pd.read_csv(input_path)
    
    # 전처리: 날짜 정렬 및 시간 변환
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values(by=['vehicle_id', 'date']) # 누적 주행거리 체크를 위해 정렬
    
    df['time_h'] = df['time'].apply(convert_time_to_hours)
    
    issues = []

    # ---------------------------------------------------------
    # 2. 체크 로직
    # ---------------------------------------------------------
    
    # [Check 1] 누적 주행거리 역전 (Regression)
    # 어제 누적거리보다 오늘 누적거리가 작으면 말이 안 됨 (계기판 교체 등 특수 상황 제외)
    print("   - 누적 주행거리 논리 점검 중...")
    for vid, group in df.groupby('vehicle_id'):
        group = group.sort_values('date')
        prev_cum = None
        prev_date = None
        
        for idx, row in group.iterrows():
            curr_cum = row.get('cumulative_distance')
            
            if pd.notna(curr_cum) and pd.notna(prev_cum):
                if curr_cum < prev_cum:
                    issues.append({
                        'id': row.get('id', idx),
                        'date': row['date'],
                        'issue_type': 'Logic Error',
                        'column': 'cumulative_distance',
                        'value': curr_cum,
                        'message': f"누적거리 역전 발생 (이전: {prev_cum} > 현재: {curr_cum})"
                    })
            
            if pd.notna(curr_cum):
                prev_cum = curr_cum
                prev_date = row['date']

    # [Check 2] 물리적 한계 초과 (Outliers)
    print("   - 물리적 한계값(Outliers) 점검 중...")
    for idx, row in df.iterrows():
        row_id = row.get('id', idx)
        
        # 속도 체크
        if pd.notna(row['speed']) and row['speed'] > LIMITS['SPEED_MAX']:
             issues.append({
                'id': row_id, 'date': row['date'], 'issue_type': 'Outlier', 'column': 'speed',
                'value': row['speed'], 'message': f"속도 과다 ({row['speed']} > {LIMITS['SPEED_MAX']} km/h)"
            })
             
        # 연비 체크
        if pd.notna(row['fuel_efficiency']):
            if row['fuel_efficiency'] < LIMITS['EFFICIENCY_MIN']:
                issues.append({
                    'id': row_id, 'date': row['date'], 'issue_type': 'Outlier', 'column': 'fuel_efficiency',
                    'value': row['fuel_efficiency'], 'message': f"연비 과소 ({row['fuel_efficiency']} < {LIMITS['EFFICIENCY_MIN']})"
                })
            elif row['fuel_efficiency'] > LIMITS['EFFICIENCY_MAX']:
                 issues.append({
                    'id': row_id, 'date': row['date'], 'issue_type': 'Outlier', 'column': 'fuel_efficiency',
                    'value': row['fuel_efficiency'], 'message': f"연비 과다 ({row['fuel_efficiency']} > {LIMITS['EFFICIENCY_MAX']})"
                })

        # 운행 시간 체크
        if pd.notna(row['time_h']) and row['time_h'] > LIMITS['TIME_MAX_HOURS']:
             issues.append({
                'id': row_id, 'date': row['date'], 'issue_type': 'Outlier', 'column': 'time',
                'value': row['time'], 'message': f"운행 시간 과다 ({row['time_h']:.1f}h > {LIMITS['TIME_MAX_HOURS']}h)"
            })

    # [Check 3] 수학적 정합성 재확인 (AI가 놓친 부분)
    print("   - 수학적 정합성(Cross Check) 점검 중...")
    for idx, row in df.iterrows():
        # 거리 vs (속도*시간)
        if pd.notna(row['distance']) and pd.notna(row['speed']) and pd.notna(row['time_h']):
            if row['distance'] > 0:
                calc_dist = row['speed'] * row['time_h']
                error_ratio = abs(row['distance'] - calc_dist) / row['distance']
                
                if error_ratio > LIMITS['DIST_CALC_TOLERANCE']:
                    issues.append({
                        'id': row.get('id', idx), 'date': row['date'], 'issue_type': 'Math Mismatch', 'column': 'distance/speed/time',
                        'value': f"Dist:{row['distance']} vs Calc:{calc_dist:.1f}", 
                        'message': f"물리적 거리 불일치 ({error_ratio*100:.1f}%)"
                    })

    # ---------------------------------------------------------
    # 3. 결과 저장
    # ---------------------------------------------------------
    if issues:
        report_df = pd.DataFrame(issues)
        # 보기 좋게 정렬
        report_df = report_df[['id', 'date', 'issue_type', 'column', 'value', 'message']]
        report_df.to_csv(output_report_path, index=False, encoding='utf-8-sig')
        
        print("\n" + "="*50)
        print(f"⚠️ 총 {len(issues)}건의 이상 데이터가 발견되었습니다.")
        print("   - Logic Error: 누적 주행거리가 줄어드는 등 논리적 모순")
        print("   - Outlier: 속도 110km/h 초과, 연비 비정상 등")
        print("   - Math Mismatch: 거리 != 속도 * 시간 (20% 이상 차이)")
        print(f"📄 상세 리포트 저장됨: {output_report_path}")
        print("="*50)
    else:
        print("\n" + "="*50)
        print("✅ 이상 징후가 발견되지 않았습니다. 데이터가 아주 깨끗합니다!")
        print("="*50)

if __name__ == "__main__":
    run_dirty_check()