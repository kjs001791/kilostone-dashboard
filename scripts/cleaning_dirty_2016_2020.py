import pandas as pd
import numpy as np
import json
import os
import asyncio
import aiohttp
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv



# ---------------------------------------------------------
# 1. 설정 및 상수 정의
# ---------------------------------------------------------
load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEY}"
CONCURRENCY_LIMIT = 5

# 물리적 한계값 설정 (필터링 및 안전장치용)
LIMITS = {
    'PHYS_ERROR_TOLERANCE': 0.20, # 물리 오차 허용 범위 (20%)
    'FUEL_ERROR_TOLERANCE': 0.01, # 연비 오차 허용 범위 (1%)
    'MAX_HOURS_PER_DAY': 16,      # 하루 최대 운행 시간
    'MAX_SPEED': 110,             # 트럭 최고 속도
    'MAX_DISTANCE': 1000          # 하루 최대 주행 거리
}

# ---------------------------------------------------------
# 2. 헬퍼 함수 (데이터 처리)
# ---------------------------------------------------------
def convert_time_to_hours(x):
    """ 문자열 시간 -> 실수 시간(Hour) 변환 """
    if pd.isna(x): return None
    if isinstance(x, (int, float)): return float(x)
    try:
        x = str(x).strip()
        parts = x.split(':')
        if len(parts) == 3: return int(parts[0]) + int(parts[1])/60 + int(parts[2])/3600
        elif len(parts) == 2: return int(parts[0]) + int(parts[1])/60
        else: return float(x)
    except: return None

def add_full_reference_columns(df):
    """ 참조값(Reference) 계산 """
    df = df.replace([np.inf, -np.inf], np.nan)
    
    # 숫자형 강제 변환
    cols = {'speed': 'speed_num', 'consumed_fuel': 'fuel_num', 
            'fuel_efficiency': 'eff_num', 'distance': 'dist_num'}
    for col, new_col in cols.items():
        df[new_col] = pd.to_numeric(df[col], errors='coerce')
    
    df['time_num'] = df['time'].apply(convert_time_to_hours)

    # 참조값 계산
    df['ref_dist_phys'] = (df['speed_num'] * df['time_num']).round(2)
    df['ref_dist_fuel'] = (df['fuel_num'] * df['eff_num']).round(2)
    df['ref_fuel'] = df.apply(lambda x: x['dist_num'] / x['eff_num'] if (pd.notnull(x['eff_num']) and x['eff_num'] > 0) else 0, axis=1).round(2)
    df['ref_efficiency'] = df.apply(lambda x: x['dist_num'] / x['fuel_num'] if (pd.notnull(x['fuel_num']) and x['fuel_num'] > 0) else 0, axis=1).round(2)
    df['ref_speed'] = df.apply(lambda x: x['dist_num'] / x['time_num'] if (pd.notnull(x['time_num']) and x['time_num'] > 0) else 0, axis=1).round(2)
    df['ref_time'] = df.apply(lambda x: x['dist_num'] / x['speed_num'] if (pd.notnull(x['speed_num']) and x['speed_num'] > 0) else 0, axis=1).round(2)
    
    return df

def validate_proposal(row):
    """ 
    [안전장치]
    1. proposed가 비어있어도(NaN) 리포팅을 위해 통과시킴 (True)
    2. 값이 있을 때만 물리적 불가능 여부를 검사하여 기각함 
    """
    try:
        target = row['target']
        val = row['proposed']
        orig = row['original']

        if pd.isna(val): return True

        if target == 'reurea':
            # Case A: 원래 값이 없는데(NaN) 값을 채워넣으려 하면 기각
            if pd.isna(orig) or str(orig).strip() == '':
                return False
            
            # Case B: 원래 값이 정밀한 소수(33.491)인데 정수(20)로 바꾸려 하면 기각
            # (단, 1->10, 2->20 같은 10배수 보정은 허용해야 함)
            try:
                orig_float = float(orig)
                prop_float = float(val)
                # 원래 값이 10 이상이고, 제안값과 10% 이상 차이나면 '함부로 바꾸는 것'으로 간주하여 기각
                # (1, 2, 6 같은 한 자리 수 오타 수정은 통과됨)
                if orig_float >= 10 and abs(orig_float - prop_float) > 5:
                    return False
            except:
                pass
        
        if target == 'time':
            # 시간 포맷 체크 및 24시간 초과 확인
            parts = str(val).split(':')
            if len(parts) >= 1 and int(parts[0]) >= 24: return False
        elif target == 'distance':
            if float(val) > LIMITS['MAX_DISTANCE']: return False
        elif target == 'speed':
            if float(val) > LIMITS['MAX_SPEED']: return False
            
        return True
    except:
        return False

# ---------------------------------------------------------
# 3. 비동기 통신 및 프롬프트
# ---------------------------------------------------------
async def call_gemini_async(session, prompt, semaphore, retries=3):
    headers = {'Content-Type': 'application/json'}
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"}
    }
    
    async with semaphore:
        for attempt in range(retries):
            try:
                async with session.post(API_URL, headers=headers, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        try:
                            text = result['candidates'][0]['content']['parts'][0]['text']   
                            parsed = json.loads(text)
                            return [parsed] if isinstance(parsed, dict) else parsed
                        except: return []
                    elif response.status == 429:
                        await asyncio.sleep((attempt + 1) * 5)
                    else: return []
            except Exception: await asyncio.sleep(3)
    return []

async def process_batch(session, stats, batch_df, semaphore):
    data_json = batch_df.to_json(orient='records', force_ascii=False)

    # AI에게 줄 이번 달 평균 정보 (문맥 제공용)
    context_info = f"""
    - Monthly Avg Distance: {stats['avg_dist']:.1f} km
    - Monthly Avg Efficiency: {stats['avg_eff']:.2f} km/L
    - Monthly Avg Fuel: {stats['avg_fuel']:.1f} L
    """
    
    # =================================================================
    # 프롬프트 및 Few-Shot 예제
    # =================================================================
    few_shot_examples = """
    [Case 1: Unit Error (Reurea)]
    - Input: {"id": 10, "reurea": 6}
    - Reasoning: Single digit reurea (1~9) is a recording error (Event count). Force replace with standard unit 20L.
    - Output: [{"id": 10, "target": "reurea", "original": 6, "proposed": 20, "reference": null, "reason": "Unit error correction (Force 6 -> 20L). Standard refill volume."}]

    [Case 2: Copy-Paste Error (Distance == Fuel)]
    - Input: {"id": 55, "distance": 133.51, "consumed_fuel": 133.51, "fuel_efficiency": 2.77}
    - Context: Monthly Avg Distance = 450.0 km
    - Reasoning: 
      1. Distance and Fuel are identical (133.51). One is wrong.
      2. Compare with Avg Dist (450.0): 133.51 is suspiciously low.
      3. Assume Fuel (133.51) is correct. Recalculate Dist = Fuel * Eff.
    - Output: [{"id": 55, "target": "distance", "original": 133.51, "proposed": 369.8, "reference": 369.8, "reason": "Copy error (Dist=Fuel). Recalculated distance using fuel * efficiency."}]

    [Case 3: Digit Omission (Leading Digit)]
    - Input: {"id": 41, "distance": 36.9, "ref_dist_fuel": 538.75}
    - Reasoning: Original (36.9) is too small vs Reference (538.75). Missing leading '5'. 536.9 matches reference closely.
    - Output: [{"id": 41, "target": "distance", "original": 36.9, "proposed": 536.9, "reference": 538.75, "reason": "Missing leading digit '5' detected (36.9 -> 536.9)."}]

    [Case 4: Digit Omission (Middle Digit)]
    - Input: {"id": 42, "consumed_fuel": 17.51, "ref_fuel": 179.17}
    - Reasoning: Original (17.51) vs Ref (179.17). Missing '9' in middle makes 179.51.
    - Output: [{"id": 42, "target": "consumed_fuel", "original": 17.51, "proposed": 179.51, "reference": 179.17, "reason": "Missing digit '9' detected (17.51 -> 179.51)."}]

    [Case 5: Fat Finger (Double Entry)]
    - Input: {"id": 22, "distance": 4718.1, "ref_dist_fuel": 478.8}
    - Reasoning: 4718.1 is physically impossible (>1500km). Likely double-tapped '1'. 478.1 is close to Ref.
    - Output: [{"id": 22, "target": "distance", "original": 4718.1, "proposed": 478.1, "reference": 478.8, "reason": "Fat finger typo (4718.1 -> 478.1). Matches calculated distance."}]

    [Case 6: Keypad Neighbor Typo]
    - Input: {"id": 35, "distance": 638.1, "ref_dist_fuel": 537.3}
    - Reasoning: 638.1 vs 537.3. Keypad '6' is above '5'. 538.1 matches Ref.
    - Output: [{"id": 35, "target": "distance", "original": 638.1, "proposed": 538.1, "reference": 537.3, "reason": "Keypad typo suspected (6->5). Validated by calc."}]

    [Case 7: Cumulative Distance Regression (Logic Error)]
    - Input: {"id": 1254, "cumulative_distance": 131185.0, "prev_cum_dist": 131343.0}
    - Reasoning: Current < Previous. Impossible. Requires manual check.
    - Output: [{"id": 1254, "target": "cumulative_distance", "original": 131185.0, "proposed": null, "reference": 131343.0, "reason": "Logic Error: Cumulative distance regression. Manual Check Required."}]

    [Case 8: Time Outlier (> 20h)]
    - Input: {"id": 720, "time": "35:27:00", "ref_time": "3:30"}
    - Reasoning: Time 35h is physically impossible (> 20h). Likely typo 35 -> 03.
    - Output: [{"id": 720, "target": "time", "original": "35:27:00", "proposed": "03:27:00", "reference": "03:30", "reason": "Time outlier (>20h). Corrected to 03:xx based on reference."}]

    [Case 9: Impossible Distance (Decimal Error)]
    - Input: {"id": 501, "distance": 5305, "time": "12:12:00", "speed": 43.1}
    - Reasoning: 5305km is impossible (>1500km). Do NOT adjust time to 123h. Fix distance decimal: 5305 -> 530.5.
    - Output: [{"id": 501, "target": "distance", "original": 5305, "proposed": 530.5, "reference": 525.8, "reason": "Impossible distance outlier. Corrected typo (5305 -> 530.5)."}]

    [Case 10: Ambiguous / Unsolvable]
    - Input: {"id": 99, "time": "11:64"}
    - Reasoning: Invalid format, ambiguous fix.
    - Output: [{"id": 99, "target": "manual_check", "original": "11:64", "proposed": null, "reference": null, "reason": "Invalid time format & ambiguous. Manual review."}]
    """

    prompt = f"""
    You are a Data Cleaning Expert.
    Your goal is to detect and fix typos by comparing 'User Input' vs 'Calculated Reference'.

    [Context Info (Averages)]
    {context_info}

    [Logic: Visual Pattern Matching]
    For each row, I provide the 'Original Input' and the 'Calculated Reference' (derived from other variables).
    1. Compare the **Original** value with its corresponding **Reference** value.
    2. If they differ significantly, check if the **Reference** value looks like a corrected version of the **Original** (e.g., typo, missing digit, wrong decimal).
    3. **Priority:** Trust the value that resolves the conflict with minimum edits to the original digits.

    [Columns Provided]
    - original: distance, consumed_fuel, fuel_efficiency, speed, time
    - reference: 
    - ref_dist_phys (from Speed*Time)
    - ref_dist_fuel (from Fuel*Eff)
    - ref_fuel (from Dist/Eff)
    - ref_efficiency (from Dist/Fuel)
    - ref_speed (from Dist/Time)
    - ref_time (from Dist/Speed)

    [Few-Shot Example]
    {few_shot_examples}

    [Output Schema]
    Return a JSON list. If valid, return [].
    {{
        "id": (int),
        "target": (str),
        "original": (value),
        "proposed": (value),
        "reference": (value),
        "reason": (str)
    }}

    [Data to Analyze]
    {data_json}
    """
    # =================================================================

    return await call_gemini_async(session, prompt, semaphore)

# ---------------------------------------------------------
# 4. 메인 실행 함수
# ---------------------------------------------------------
async def main_async():
    current_dir = Path(__file__).resolve().parent
    project_root = current_dir.parent
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    input_path = project_root / 'data' / 'processed' / 'driving_log_2016_2020_messy_cleaned.csv'
    output_path = project_root / 'data' / f'cleaning_proposal_ai_{timestamp}.csv'

    # 결과 파일 초기화
    header_df = pd.DataFrame(columns=['id', 'date', 'vehicle_id', 'target', 'original', 'proposed', 'reference', 'reason'])
    header_df.to_csv(output_path, index=False, encoding='utf-8-sig')

    print("🚀 데이터 로드 및 전처리...")
    df = pd.read_csv(input_path)
    df = add_full_reference_columns(df)
    
    df['id'] = df.index
    df['date_dt'] = pd.to_datetime(df['date'])
    df['month'] = df['date_dt'].dt.to_period('M')

    # [최적화 1] 누적 주행거리 역전 검사를 위한 전역 정렬 및 Shift
    print("⚡ 누적 주행거리 논리 검사 준비 중...")
    df = df.sort_values(by=['vehicle_id', 'date_dt'])
    df['prev_cum_dist'] = df.groupby('vehicle_id')['cumulative_distance'].shift(1)
    
    # 누적 주행거리 에러 마스크 (전역 계산)
    mask_cum_error = (
        (df['cumulative_distance'].notna()) & 
        (df['prev_cum_dist'].notna()) & 
        (df['cumulative_distance'] < df['prev_cum_dist'])
    )

    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    connector = aiohttp.TCPConnector(limit=10, force_close=True)

    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        
        # 월별 처리 루프
        for month, group in df.groupby('month'):
            print(f"📅 {month} 데이터 분석 중... (대상: {len(group)}건)")
            stats = {
                'avg_dist': group['distance'].mean(),
                'avg_eff': group['fuel_efficiency'].mean(),
                'avg_fuel': group['consumed_fuel'].mean()
            }
            # [최적화 2] 벡터화된 필터링 (iterrows 제거)
            
            # 조건 1: 연비 시스템 검증
            mask_fuel = (
                (group['consumed_fuel'] > 0) & (group['fuel_efficiency'] > 0) &
                (abs((group['distance'] / group['consumed_fuel'] - group['fuel_efficiency']) / group['fuel_efficiency']) > LIMITS['FUEL_ERROR_TOLERANCE'])
            )

            # 조건 2: 물리 시스템 검증
            mask_phys = (
                (group['ref_dist_phys'].notna()) & (group['distance'] > 0) &
                (abs(group['distance'] - group['ref_dist_phys']) / group['distance'] > LIMITS['PHYS_ERROR_TOLERANCE'])
            )

            # 조건 3: 시간 포맷 및 범위 검증
            def is_invalid_time(t):
                if pd.isna(t) or ':' not in str(t): return False
                try:
                    h, m, s = map(int, str(t).split(':'))
                    return h >= LIMITS['MAX_HOURS_PER_DAY'] or m >= 60 
                except: return True
            mask_time = group['time'].apply(is_invalid_time)

            # 조건 4: 요소수 단위 검증
            mask_reurea = (group['reurea'].notna()) & (group['reurea'].isin([1, 2, 6]))
            
            # 조건 5: 누적 주행거리 에러 (전역 마스크 매핑)
            mask_cum = mask_cum_error.loc[group.index]

            # 최종 의심 데이터 추출
            suspect_df = group[mask_fuel | mask_phys | mask_time | mask_reurea | mask_cum].copy()

            if not suspect_df.empty:
                # AI에게 보낼 컬럼 선택 (Hints 포함)
                target_cols = ['id', 'date', 'vehicle_id', 'distance', 'consumed_fuel', 
                               'fuel_efficiency', 'time', 'speed', 'reurea', 
                               'cumulative_distance', 'prev_cum_dist', 'ref_time']
                
                for col in target_cols:
                    if col not in suspect_df.columns: suspect_df[col] = None

                # 배치 분할 및 Task 예약
                batch_size = 15
                for i in range(0, len(suspect_df), batch_size):
                    batch_slice = suspect_df.iloc[i:i+batch_size][target_cols]
                    tasks.append(process_batch(session, stats, batch_slice, semaphore))

        print(f"📦 총 {len(tasks)}개의 배치 작업이 예약되었습니다. 실행 중...")
        
        total_corrections = 0
        for future in asyncio.as_completed(tasks):
            proposals = await future
            if proposals:
                res_df = pd.DataFrame(proposals)
                
                # 유효성 검사 및 정제
                if res_df.empty or 'target' not in res_df.columns: continue
                
                # [최적화 3] 안전장치 가동: 말도 안 되는 제안값 자동 기각
                valid_mask = res_df.apply(validate_proposal, axis=1)
                res_df = res_df[valid_mask]
                
                if res_df.empty: continue

                # [수정] 결과 파일 저장 시 date, vehicle_id를 원본에서 찾아 병합 (Merge)
                # AI가 반환한 JSON에는 id만 있을 수 있으므로, 원본 df에서 날짜 정보를 가져옴
                res_df['id'] = res_df['id'].astype(int)
                
                # 원본 데이터(df)에서 해당 id의 날짜와 차량번호 매핑
                merged_df = res_df.merge(df[['id', 'date', 'vehicle_id']], on='id', how='left')
                
                # 저장할 컬럼 순서 지정
                cols_to_save = ['id', 'date', 'vehicle_id', 'target', 'original', 'proposed', 'reference', 'reason']
                for col in cols_to_save:
                    if col not in merged_df.columns: merged_df[col] = None
                
                merged_df = merged_df[cols_to_save].dropna(subset=['id'])
                merged_df.to_csv(output_path, mode='a', header=False, index=False, encoding='utf-8-sig', lineterminator='\n')
                
                count = len(merged_df)
                total_corrections += count
                print(f"✅ 배치 완료: {count}건 저장 (누적 {total_corrections})")
            else:
                print(".", end="", flush=True)

    # 최종 정렬
    print("\n🧹 최종 결과 정렬 중...")
    try:
        final_df = pd.read_csv(output_path)
        if not final_df.empty:
            final_df = final_df.sort_values(by='id')
            final_df.to_csv(output_path, index=False, encoding='utf-8-sig')
            print("✨ 정렬 완료.")
    except Exception as e:
        print(f"⚠️ 정렬 중 오류 (데이터 보존됨): {e}")

    print(f"🎉 작업 완료! 결과 파일: {output_path}")

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main_async())