import pandas as pd
import numpy as np
import json
import os
import asyncio
import aiohttp
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# 1. 설정 로드
load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")

# API 설정 (REST API 직접 호출 방식이 비동기 처리에 유리함)
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEY}"

# 동시 실행 개수 제한 설정
CONCURRENCY_LIMIT = 5

def convert_time_to_hours(x):
    """
    문자열 시간('HH:MM:SS' or 'HH:MM')을 실수 시간(Hours)으로 변환
    오류 발생 시 NaN 반환
    """
    if pd.isna(x):
        return None
    
    # 이미 숫자인 경우 바로 반환
    if isinstance(x, (int, float)):
        return float(x)
        
    try:
        x = str(x).strip()
        parts = x.split(':')
        if len(parts) == 3: # HH:MM:SS
            return int(parts[0]) + int(parts[1])/60 + int(parts[2])/3600
        elif len(parts) == 2: # HH:MM
            return int(parts[0]) + int(parts[1])/60
        else:
            return float(x) # 그 외 숫자로 변환 시도
    except:
        return None # 변환 불가("11:64" 등 잘못된 포맷) -> NaN 처리


def add_full_reference_columns(df):
    """
    5개 변수 모두에 대해 '나머지 변수로 계산한 기대값'을 생성.
    (문자열 -> 숫자 강제 변환 및 소수점 2자리 반올림 적용)
    """
    # 0 나누기 방지
    df = df.replace([np.inf, -np.inf], np.nan)

    # [핵심 수정] 계산을 위해 숫자형으로 강제 변환 (임시 컬럼 생성)
    # errors='coerce': 숫자로 못 바꾸는 값(오타 등)은 NaN으로 처리하여 에러 방지
    df['speed_num'] = pd.to_numeric(df['speed'], errors='coerce')
    df['fuel_num'] = pd.to_numeric(df['consumed_fuel'], errors='coerce')
    df['eff_num'] = pd.to_numeric(df['fuel_efficiency'], errors='coerce')
    df['dist_num'] = pd.to_numeric(df['distance'], errors='coerce')
    
    # 시간 문자열을 실수(Hour)로 변환
    df['time_num'] = df['time'].apply(convert_time_to_hours)

    # 1. 거리 (Distance) 검증값 2개
    # speed_num과 time_num을 사용하여 계산해야 함 (원래 컬럼 X)
    df['ref_dist_phys'] = (df['speed_num'] * df['time_num']).round(2)
    df['ref_dist_fuel'] = (df['fuel_num'] * df['eff_num']).round(2)
    
    # 2. 소모량 (Fuel) 검증값
    df['ref_fuel'] = df.apply(lambda x: x['dist_num'] / x['eff_num'] if (pd.notnull(x['eff_num']) and x['eff_num'] > 0) else 0, axis=1).round(2)
    
    # 3. 연비 (Efficiency) 검증값
    df['ref_efficiency'] = df.apply(lambda x: x['dist_num'] / x['fuel_num'] if (pd.notnull(x['fuel_num']) and x['fuel_num'] > 0) else 0, axis=1).round(2)
    
    # 4. 속도 (Speed) 검증값
    df['ref_speed'] = df.apply(lambda x: x['dist_num'] / x['time_num'] if (pd.notnull(x['time_num']) and x['time_num'] > 0) else 0, axis=1).round(2)
    
    # 5. 시간 (Time) 검증값
    # 시간은 다시 HH:MM 형태로 바꿀 필요 없이, 비교를 위해 실수(Hour) 형태로 둠
    df['ref_time'] = df.apply(lambda x: x['dist_num'] / x['speed_num'] if (pd.notnull(x['speed_num']) and x['speed_num'] > 0) else 0, axis=1).round(2)

    return df


# 2. 비동기 API 호출 함수 (재시도 로직 포함)
async def call_gemini_async(session, prompt, semaphore, retries=3):
    headers = {'Content-Type': 'application/json'}
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json"
        }
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

                            if isinstance(parsed, dict):
                                return [parsed]
                            return parsed
                        except:
                            return [] # 파싱 실패 시 빈 리스트
                    elif response.status == 429: # Rate Limit
                        wait_time = (attempt + 1) * 5
                        print(f"⏳ Rate Limit. {wait_time}초 대기... (시도 {attempt+1}/{retries})")
                        await asyncio.sleep(wait_time)
                    else:
                        print(f"⚠️ API Error {response.status}: {await response.text()}")
                        return []
            except Exception as e:
                print(f"⚠️ Network Error ({attempt+1}/{retries}): {e}")
                await asyncio.sleep(3)
    
    return [] # 최종 실패

# 3. 배치 처리 함수
async def process_batch(session, month_str, stats, batch_df, semaphore):
    # 실제 데이터의 JSON 변환 (모델에 들어가는 실제 입력값)
    data_json = batch_df.to_json(orient='records', force_ascii=False)
    
    few_shot_examples = """
    [Case 1: Unit Error (Reurea - Force Fix)]
    - Input Context:
      - Original: {"reurea": 6}
      - References: {}
    - Reasoning: Single digit reurea (1~9) is a recording error. User input represents 'Event' not 'Volume'. Force replace with standard unit 20L. DO NOT MULTIPLY.
    - Output: [{"id": 10, "target": "reurea", "original": 6, "proposed": 20, "reference": null, "reason": "Unit error correction (Force 6 -> 20L). Standard refill volume."}]

    [Case 2: Copy-Paste Error (Variables are identical)]
    - Input Context:
      - Original: {"distance": 133.51, "consumed_fuel": 133.51, "fuel_efficiency": 2.77}
      - Stats: {"avg_dist": 450.0, "avg_fuel": 180.0}
      - References: {"ref_dist_fuel": 369.8}
    - Reasoning:
      1. Distance and Fuel are identical (133.51). Impossible physically.
      2. Fuel 133.51 is closer to avg_fuel(180) than avg_dist(450). Assume Fuel is correct.
      3. Recalculate Distance: Fuel(133.51) * Eff(2.77) = 369.8.
    - Output: [{"id": 55, "target": "distance", "original": 133.51, "proposed": 369.8, "reference": 369.8, "reason": "Copy error detected. Recalculated distance using fuel * efficiency."}]

    [Case 3: Digit Omission (Leading/Middle Digit)]
    - Input Context:
      - Original: {"distance": 36.9, "consumed_fuel": 208.01, "fuel_efficiency": 2.59}
      - References: {"ref_dist_fuel": 538.75}
    - Reasoning:
      1. Original Distance (36.9) is too small compared to Ref (538.75).
      2. Visual Check: '36.9' vs '538.75'. Missing leading digit '5' creates '536.9'.
      3. Validation: 536.9 / 208.01 = 2.58 (Matches efficiency 2.59 within tolerance).
    - Output: [{"id": 41, "target": "distance", "original": 36.9, "proposed": 536.9, "reference": 538.75, "reason": "Missing leading digit '5' detected (36.9 -> 536.9). Matches efficiency."}]

    [Case 4: Digit Omission (Fuel Example)]
    - Input Context:
      - Original: {"distance": 473.0, "consumed_fuel": 17.51, "fuel_efficiency": 2.64}
      - References: {"ref_fuel": 179.17}
    - Reasoning:
      1. Original Fuel (17.51) vs Ref (179.17).
      2. Visual Check: Missing '9' in the middle. 17.51 -> 179.51.
      3. Validation: 473.0 / 179.51 = 2.63 (Matches efficiency 2.64 within tolerance).
    - Output: [{"id": 42, "target": "consumed_fuel", "original": 17.51, "proposed": 179.51, "reference": 179.17, "reason": "Missing digit '9' detected (17.51 -> 179.51)."}]

    [Case 5: Fat Finger (Double Entry)]
    - Input Context:
      - Original: {"distance": 4718.1, "consumed_fuel": 188.51, "fuel_efficiency": 2.54}
      - References: {"ref_dist_fuel": 478.8, "ref_dist_phys": 473.1}
    - Reasoning:
      1. Original Distance (4718.1) is huge. Ref is ~478.
      2. Visual Check: '4718.1' vs '478.1'. User likely double-tapped '1' or '478' became '4718'.
      3. '478.1' is closest to Ref (478.8).
    - Output: [{"id": 22, "target": "distance", "original": 4718.1, "proposed": 478.1, "reference": 478.8, "reason": "Fat finger typo (4718.1 -> 478.1). Matches calculated distance."}]

    [Case 6: Keypad Neighbor Typo]
    - Input Context:
      - Original: {"distance": 638.1, "consumed_fuel": 184.01, "fuel_efficiency": 2.92}
      - References: {"ref_dist_fuel": 537.3}
    - Reasoning:
      1. Original (638.1) != Ref (537.3).
      2. Visual Check: '6' and '5' are neighbors on keypad. 638.1 -> 538.1.
      3. Validation: 538.1 / 184.01 = 2.92 (Exact match).
    - Output: [{"id": 35, "target": "distance", "original": 638.1, "proposed": 538.1, "reference": 537.3, "reason": "Keypad typo suspected (6->5). validated by calc."}]

    [Case 7: Ambiguous / Unsolvable (Manual Check)]
    - Input Context:
      - Original: {"time": "11:64", "distance": 500, "speed": 40}
      - References: {"ref_time_calc": "12:30"}
    - Reasoning:
      1. Time "11:64" is invalid format.
      2. Calc Time is 12:30.
      3. User might have meant 11:54 (typo) or really 12:30. Too ambiguous to auto-fix.
    - Output: [{"id": 99, "target": "manual_check", "original": "11:64", "proposed": null, "reference": null, "reason": "Invalid time format & ambiguous calculation. Requires manual review."}]
    """

    prompt = f"""
    You are a Data Cleaning Expert.
    Your goal is to detect and fix typos by comparing 'User Input' vs 'Calculated Reference'.

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

    return await call_gemini_async(session, prompt, semaphore)


# 4. 메인 실행 함수
async def main_async():
    current_dir = Path(__file__).resolve().parent
    project_root = current_dir.parent

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    input_path = project_root / 'data' / 'processed' / 'driving_log_2016_2020_cleaned.csv'

    output_filename = f'cleaning_proposal_ai_{timestamp}.csv'
    output_path = project_root / 'data' / output_filename

    print("🚀 초고속 AI 데이터 클리닝 시작 (Async Batch Processing)...")
    print(f"📄 결과 파일명: {output_filename}")

    # 결과 파일 초기화
    header_df = pd.DataFrame(columns=['id', 'target', 'original', 'proposed', 'reference', 'reason'])
    header_df.to_csv(output_path, index=False, encoding='utf-8-sig')
    

    # 1. 데이터 로드
    df = pd.read_csv(input_path)

    print("⚡ 모든 데이터에 대한 참조값(Reference) 계산 중...")
    df = add_full_reference_columns(df)

    # 2. 날짜 및 기타 설정
    df['id'] = df.index
    df['date_dt'] = pd.to_datetime(df['date'])
    df['month'] = df['date_dt'].dt.to_period('M')

    # 세마포어 생성 (동시 실행 개수 5개로 제한)
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    
    # TCPConnector 설정 (연결 끊김 방지, 강제 종료 허용)
    connector = aiohttp.TCPConnector(limit=10, force_close=True)

    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        
        # 월별 루프 -> Task 생성
        for month, group in df.groupby('month'):
            # 1. 해당 월의 통계 정보 추출 (프롬프트 컨텍스트용)
            stats = {
                'fuel_efficiency': group['fuel_efficiency'].mean(),
                'distance': group['distance'].mean()
            }
            
            # --- [필터링 로직 최적화: 벡터화 연산 사용] ---
            
            # 조건 1: 연비 시스템 검증 (엄격한 기준: 1% 오차)
            # (거리/소모량)과 (기록된 연비)가 1% 이상 차이나면 의심
            # 0으로 나누기 방지를 위해 분모가 0이 아닌 경우만 계산
            mask_fuel = (
                (group['consumed_fuel'] > 0) & 
                (group['fuel_efficiency'] > 0) &
                (abs((group['distance'] / group['consumed_fuel'] - group['fuel_efficiency']) / group['fuel_efficiency']) > 0.01)
            )

            # 조건 2: 물리 시스템 검증 (관대한 기준: 5% 오차)
            # (거리)와 (참조거리: 속도*시간)가 5% 이상 차이나면 의심
            # ref_dist_phys가 존재하고(NaN이 아니고), 거리가 0보다 클 때만 계산
            mask_phys = (
                (group['ref_dist_phys'].notna()) & 
                (group['distance'] > 0) &
                (abs(group['distance'] - group['ref_dist_phys']) / group['distance'] > 0.05)
            )

            # 조건 3: 시간 포맷 오류 검증
            # "25:00", "12:70" 같은 비정상적인 시간 형식 찾기
            def is_invalid_time(t):
                if pd.isna(t) or ':' not in str(t): return False
                try:
                    h, m, s = map(int, str(t).split(':'))
                    return h >= 24 or m >= 60 # 24시 이상이거나 60분 이상이면 오류
                except:
                    return True # 파싱 에러나면 오류로 간주

            mask_time = group['time'].apply(is_invalid_time)

            # 조건 4: 요소수 단위 오류 검증
            # 1, 2, 6 등 한 자리 수는 단위 오류(통 단위)일 확률 높음
            mask_reurea = (
                (group['reurea'].notna()) & 
                (group['reurea'].isin([1, 2, 6]))
            )

            # --- [최종 필터링 및 배치 처리] ---
            
            # 위 4가지 조건 중 하나라도 해당되면(OR 연산 |) 의심 데이터로 간주
            suspect_df = group[mask_fuel | mask_phys | mask_time | mask_reurea].copy()
            
            # 의심 데이터가 있다면 배치 작업 생성
            if not suspect_df.empty:
                # 필요한 컬럼만 선택하여 Dict 변환 (메모리 절약)
                target_cols = ['id', 'date', 'vehicle_id', 'distance', 'consumed_fuel', 
                            'fuel_efficiency', 'time', 'speed', 'reurea']
                
                # 15개씩 잘라서 처리 (Batch Processing)
                batch_size = 15
                for i in range(0, len(suspect_df), batch_size):
                    batch_slice = suspect_df.iloc[i:i+batch_size][target_cols]
                    
                    # Task 예약 (API 호출 함수에 전달)
                    tasks.append(process_batch(session, str(month), stats, batch_slice, semaphore))

        print(f"📦 총 {len(tasks)}개의 배치 작업이 예약되었습니다. 병렬 처리를 시작합니다...")
        
        # 병렬 실행 및 실시간 저장 (Streaming Save)
        total_corrections = 0
        
        # as_completed: 먼저 끝나는 작업부터 순서대로 처리
        for future in asyncio.as_completed(tasks):
            proposals = await future
            if proposals:
                res_df = pd.DataFrame(proposals)
                
                # [중요] 수정 제안이 없는 데이터(빈 리스트 등)나 잘못된 키가 있는 행 필터링
                if res_df.empty or 'target' not in res_df.columns:
                    continue
                
                # is_error 키가 혹시 남아있다면 제거 (프롬프트에서 제외했지만 안전장치)
                if 'is_error' in res_df.columns:
                    res_df = res_df[res_df['is_error'] != False]

                # 저장할 컬럼만 선택 (original 컬럼이 없으면 NaN 처리됨)
                cols_to_save = ['id', 'target', 'original', 'proposed', 'reference', 'reason']
                for col in cols_to_save:
                    if col not in res_df.columns:
                        res_df[col] = None 
                
                res_df = res_df[cols_to_save]
                
                # id가 없는 행(쓰레기 데이터) 제거
                res_df = res_df.dropna(subset=['id'])

                res_df.to_csv(output_path, mode='a', header=False, index=False, encoding='utf-8-sig', lineterminator='\n')
            
            count = len(res_df)
            total_corrections += count
            print(f"✅ 배치 완료: {count}건 저장됨 (누적 {total_corrections}건)")
        else:
            print(".", end="", flush=True)
    print("🧹 최종 결과 정렬 중...")
    try:
        final_df = pd.read_csv(output_path)
        if not final_df.empty:
            final_df = final_df.sort_values(by='id') # id 기준 오름차순 정렬
            final_df.to_csv(output_path, index=False, encoding='utf-8-sig')
            print("✨ 정렬 완료.")
    except Exception as e:
        print(f"⚠️ 정렬 중 오류 발생 (데이터는 보존됨): {e}")

    print(f"\n🎉 모든 작업 완료! 총 {total_corrections}건의 데이터가 수정 제안되었습니다.")
    print(f"📂 결과 파일: {output_path}")

if __name__ == "__main__":
    # 윈도우 환경에서 asyncio 에러 방지
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main_async())