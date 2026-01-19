import pandas as pd
from pathlib import Path
import numpy as np

def main():
    # 1. 파일 로드
    current_dir = Path(__file__).resolve().parent
    file_path = current_dir.parent / 'data' / 'processed' / 'driving_log_2016_2020_cleaned.csv'
    
    if not file_path.exists():
        print("❌ 파일이 없습니다. ETL 스크립트를 먼저 실행하세요.")
        return

    print("🚀 Messy Data QA (구조적 무결성 검사) 시작")
    print("="*60)
    
    df = pd.read_csv(file_path)
    df['date'] = pd.to_datetime(df['date']) # 날짜 타입 변환

    # ---------------------------------------------------------
    # CHECK 1: 데이터 타입 및 결측치 현황 (Data Types & Nulls)
    # ---------------------------------------------------------
    print("\n[Check 1] 컬럼별 데이터 타입 및 비어있는 값(Null) 개수")
    print(df.info())
    print("-" * 30)
    # 해석 가이드: 
    # vehicle_id, date, distance는 Non-Null Count가 전체 데이터 수와 같아야 함 (필수값)
    # speed, time은 2019년 5월 이후 데이터 때문에 Null이 꽤 있어야 정상임.

    # ---------------------------------------------------------
    # CHECK 2: 스키마 변화 시점 검증 (Schema Shift)
    # ---------------------------------------------------------
    print("\n[Check 2] 2019년 5월 전후 스키마 변화 확인")
    
    # 기준일: 2019-05-01
    split_date = pd.to_datetime("2019-05-01")
    
    df_old = df[df['date'] < split_date]
    df_new = df[df['date'] >= split_date]

    print(f"📉 [과거 데이터] (~2019.04) : {len(df_old)}행")
    # 과거 데이터는 '누적 주행거리(cumulative_distance)'가 거의 없어야 정상 (대부분 NaN)
    old_cum_na = df_old['cumulative_distance'].isna().sum()
    print(f"   -> 누적거리(cumulative)가 비어있는 비율: {old_cum_na / len(df_old) * 100:.1f}% (높아야 정상)")
    
    print(f"📈 [최신 데이터] (2019.05~) : {len(df_new)}행")
    # 최신 데이터는 '속도(speed)', '시간(time)'이 없어야 정상 (NaN)
    new_speed_na = df_new['speed'].isna().sum()
    print(f"   -> 속도(speed)가 비어있는 비율: {new_speed_na / len(df_new) * 100:.1f}% (100%에 가까워야 정상)")
    
    # ---------------------------------------------------------
    # CHECK 3: 컬럼 밀림 현상 탐지 (Column Shift Detection)
    # 값이 들어갔는데, 엉뚱한 컬럼에 들어갔는지 범위(Range)로 체크
    # ---------------------------------------------------------
    print("\n[Check 3] 컬럼 데이터 범위 적합성 (컬럼 밀림 확인)")
    
    # Rule 1: 연비(fuel_efficiency)는 보통 1.0 ~ 5.0 사이여야 함.
    # 만약 100이 넘는 숫자가 있다면 거리가 연비 칸에 잘못 들어간 것.
    suspicious_fuel = df[df['fuel_efficiency'] > 10]
    if not suspicious_fuel.empty:
        print(f"🚨 [경고] 연비 컬럼에 10 이상의 값이 {len(suspicious_fuel)}건 있습니다. (컬럼 밀림 의심)")
        print(suspicious_fuel[['date', 'fuel_efficiency', 'distance']].head(3))
    else:
        print("✅ 연비 컬럼 범위 정상 (10 초과 값 없음)")

    # Rule 2: 일일 거리(distance)는 0일 수 없음 (위에서 제거했으므로).
    # 너무 작은 값(예: 5km 미만)이 있는지? (혹시 연비가 거리로 들어갔나?)
    suspicious_dist = df[df['distance'] < 5]
    if not suspicious_dist.empty:
        print(f"🚨 [경고] 거리가 5km 미만인 데이터가 {len(suspicious_dist)}건 있습니다. (연비가 거리로? 확인 필요)")
        print(suspicious_dist[['date', 'distance', 'fuel_efficiency']].head(3))
    else:
        print("✅ 거리 컬럼 범위 정상 (5km 미만 값 없음)")

    # Rule 3: 시간(time) 포맷 체크
    # time 컬럼은 문자열(HH:MM:SS)이어야 함.
    # 만약 숫자가 들어가 있다면 전처리 함수(fix_time_format)가 실패한 것.
    non_string_times = df[df['time'].apply(lambda x: not isinstance(x, str) and not pd.isna(x))]
    if not non_string_times.empty:
        print(f"🚨 [경고] 시간(time) 컬럼에 문자열이 아닌 데이터 발견: {len(non_string_times)}건")
        print(non_string_times[['date', 'time']].head())
    else:
        print("✅ 시간 컬럼 형식 정상 (String or NaN)")

    print("="*60)
    print("검사 종료. 위 결과에서 '🚨' 표시가 없다면 Messy Data 처리는 완료된 것입니다.")

if __name__ == "__main__":
    main()