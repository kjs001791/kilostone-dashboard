"""
Step 3: Dirty Data 정제 (Gemini API)
의심 데이터를 필터링하고, Gemini API에 비동기 배치 요청하여 수정 제안서(proposal) 생성.
"""

import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np
import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.schema_config import (
    LIMITS, STAGING_DIR, API_KEY, API_URL, CONCURRENCY_LIMIT,
    convert_time_to_hours,
)


# =================================================================
# 참조값 계산
# =================================================================
def add_reference_columns(df):
    """원본 값으로부터 교차검증용 참조값(Reference) 계산"""
    df = df.replace([np.inf, -np.inf], np.nan)

    for col, new in {
        'speed': 'speed_num',
        'consumed_fuel': 'fuel_num',
        'fuel_efficiency': 'eff_num',
        'distance': 'dist_num',
    }.items():
        df[new] = pd.to_numeric(df[col], errors='coerce')

    df['time_num'] = df['time'].apply(convert_time_to_hours)

    # 물리 시스템: distance = speed × time
    df['ref_dist_phys'] = (df['speed_num'] * df['time_num']).round(2)

    # 연비 시스템: distance = fuel × efficiency
    df['ref_dist_fuel'] = (df['fuel_num'] * df['eff_num']).round(2)

    # 역산 참조값
    df['ref_fuel'] = df.apply(
        lambda x: round(x['dist_num'] / x['eff_num'], 2)
        if pd.notnull(x['eff_num']) and x['eff_num'] > 0 else 0,
        axis=1
    )
    df['ref_efficiency'] = df.apply(
        lambda x: round(x['dist_num'] / x['fuel_num'], 2)
        if pd.notnull(x['fuel_num']) and x['fuel_num'] > 0 else 0,
        axis=1
    )
    df['ref_speed'] = df.apply(
        lambda x: round(x['dist_num'] / x['time_num'], 2)
        if pd.notnull(x['time_num']) and x['time_num'] > 0 else 0,
        axis=1
    )
    df['ref_time'] = df.apply(
        lambda x: round(x['dist_num'] / x['speed_num'], 2)
        if pd.notnull(x['speed_num']) and x['speed_num'] > 0 else 0,
        axis=1
    )
    return df


# =================================================================
# 안전장치: 제안값 검증
# =================================================================
def validate_proposal(row):
    """AI 제안값이 물리적으로 가능한지 필터링"""
    try:
        target = row['target']
        val = row['proposed']
        orig = row['original']

        if pd.isna(val):
            return True  # proposed=null (manual_check) → 리포팅용으로 통과

        if target == 'reurea':
            if pd.isna(orig) or str(orig).strip() == '':
                return False  # 원래 없는 값을 채워넣으려 하면 기각
            try:
                orig_float = float(orig)
                prop_float = float(val)
                if orig_float >= 10 and abs(orig_float - prop_float) > 5:
                    return False  # 정밀한 값을 함부로 바꾸면 기각
            except:
                pass

        if target == 'time':
            parts = str(val).split(':')
            if len(parts) >= 1 and int(parts[0]) >= 24:
                return False
        elif target == 'distance':
            if float(val) > LIMITS['MAX_DISTANCE']:
                return False
        elif target == 'speed':
            if float(val) > LIMITS['MAX_SPEED']:
                return False

        return True
    except:
        return False


# =================================================================
# Gemini API 비동기 호출
# =================================================================
async def call_gemini(session, prompt, semaphore, retries=3):
    """Gemini API 단일 호출 (재시도 포함)"""
    headers = {'Content-Type': 'application/json'}
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
        },
    }
    async with semaphore:
        for attempt in range(retries):
            try:
                async with session.post(API_URL, headers=headers, json=data) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        text = result['candidates'][0]['content']['parts'][0]['text']
                        parsed = json.loads(text)
                        return [parsed] if isinstance(parsed, dict) else parsed
                    elif resp.status == 429:
                        await asyncio.sleep((attempt + 1) * 5)
                    else:
                        return []
            except Exception:
                await asyncio.sleep(3)
    return []


# =================================================================
# 프롬프트 생성
# =================================================================
def get_prompt(stats, data_json):

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

    return prompt


# =================================================================
# Step 3 메인
# =================================================================
async def step3_clean_dirty(csv_path, test_mode=False):
    """
    의심 데이터 필터링 → Gemini API 배치 호출 → 제안서 CSV 생성.
    Returns: 제안서 파일 경로 (Path)
    """
    print("\n" + "=" * 60)
    print("🤖 STEP 3: Dirty Data 정제 (Gemini API)")
    print("=" * 60)

    if not API_KEY:
        print("❌ GOOGLE_API_KEY가 .env에 없습니다.")
        sys.exit(1)

    tag = "_TEST" if test_mode else ""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = STAGING_DIR / f"cleaning_proposal{tag}_{timestamp}.csv"

    # 결과 파일 초기화
    header_df = pd.DataFrame(columns=[
        'id', 'date', 'vehicle_id', 'target',
        'original', 'proposed', 'reference', 'reason',
    ])
    header_df.to_csv(output_path, index=False, encoding='utf-8-sig')

    # 데이터 로드 + 참조값 계산
    df = pd.read_csv(csv_path)
    df = add_reference_columns(df)
    df['id'] = df.index
    df['date_dt'] = pd.to_datetime(df['date'])
    df['month'] = df['date_dt'].dt.to_period('M')

    # 누적 주행거리 역전 검사 준비 (전역)
    df = df.sort_values(by=['vehicle_id', 'date_dt'])
    df['prev_cum_dist'] = df.groupby('vehicle_id')['cumulative_distance'].shift(1)
    mask_cum_error = (
        (df['cumulative_distance'].notna())
        & (df['prev_cum_dist'].notna())
        & (df['cumulative_distance'] < df['prev_cum_dist'])
    )

    # 비동기 배치 준비
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    connector = aiohttp.TCPConnector(limit=10, force_close=True)
    total = 0

    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []

        for month, group in df.groupby('month'):
            stats = {
                'avg_dist': group['distance'].mean(),
                'avg_eff': group['fuel_efficiency'].mean(),
                'avg_fuel': group['consumed_fuel'].mean(),
            }

            # ----- 의심 데이터 필터 (5개 조건) -----

            # 조건 1: 연비 시스템 불일치
            mask_fuel = (
                (group['consumed_fuel'] > 0)
                & (group['fuel_efficiency'] > 0)
                & (abs(
                    (group['distance'] / group['consumed_fuel'] - group['fuel_efficiency'])
                    / group['fuel_efficiency']
                ) > LIMITS['FUEL_ERROR_TOLERANCE'])
            )

            # 조건 2: 물리 시스템 불일치
            mask_phys = (
                (group['ref_dist_phys'].notna())
                & (group['distance'] > 0)
                & (abs(group['distance'] - group['ref_dist_phys'])
                   / group['distance'] > LIMITS['PHYS_ERROR_TOLERANCE'])
            )

            # 조건 3: 시간 이상
            def is_invalid_time(t):
                if pd.isna(t) or ':' not in str(t):
                    return False
                try:
                    h, m, s = map(int, str(t).split(':'))
                    return h >= LIMITS['MAX_HOURS_PER_DAY'] or m >= 60
                except:
                    return True
            mask_time = group['time'].apply(is_invalid_time)

            # 조건 4: 요소수 단위 의심
            mask_reurea = (group['reurea'].notna()) & (group['reurea'].isin([1, 2, 6]))

            # 조건 5: 누적거리 역전
            mask_cum = mask_cum_error.loc[group.index]

            # 의심 데이터 추출
            suspect = group[
                mask_fuel | mask_phys | mask_time | mask_reurea | mask_cum
            ].copy()

            if suspect.empty:
                continue

            # AI에 보낼 컬럼
            target_cols = [
                'id', 'date', 'vehicle_id', 'distance', 'consumed_fuel',
                'fuel_efficiency', 'time', 'speed', 'reurea',
                'cumulative_distance', 'prev_cum_dist', 'ref_time',
            ]
            for col in target_cols:
                if col not in suspect.columns:
                    suspect[col] = None

            # 배치 분할 (15건씩)
            for i in range(0, len(suspect), 15):
                batch = suspect.iloc[i:i + 15][target_cols]

                async def process(b=batch, s=stats):
                    data_json = b.to_json(orient='records', force_ascii=False)
                    prompt = get_prompt(s, data_json)
                    return await call_gemini(session, prompt, semaphore)

                tasks.append(process())

        print(f"📦 {len(tasks)}개 배치 예약됨. 실행 중...")

        for future in asyncio.as_completed(tasks):
            proposals = await future
            if not proposals:
                continue

            res_df = pd.DataFrame(proposals)
            if res_df.empty or 'target' not in res_df.columns:
                continue

            # 안전장치
            res_df = res_df[res_df.apply(validate_proposal, axis=1)]
            if res_df.empty:
                continue

            # 원본에서 날짜/차량 매핑
            res_df['id'] = res_df['id'].astype(int)
            merged = res_df.merge(
                df[['id', 'date', 'vehicle_id']], on='id', how='left'
            )

            cols = ['id', 'date', 'vehicle_id', 'target',
                    'original', 'proposed', 'reference', 'reason']
            for c in cols:
                if c not in merged.columns:
                    merged[c] = None

            merged[cols].dropna(subset=['id']).to_csv(
                output_path, mode='a', header=False,
                index=False, encoding='utf-8-sig',
            )
            total += len(merged)
            print(f"  ✅ +{len(merged)}건 (누적 {total})")

    # 최종 정렬
    try:
        final = pd.read_csv(output_path)
        if not final.empty:
            final.sort_values('id').to_csv(
                output_path, index=False, encoding='utf-8-sig'
            )
    except Exception:
        pass

    print(f"✅ STEP 3 완료: {output_path}")
    return output_path


# =================================================================
# 단독 테스트
# =================================================================
if __name__ == "__main__":
    import os

    test_path = STAGING_DIR / "messy_cleaned_TEST.csv"
    if not test_path.exists():
        test_path = STAGING_DIR / "messy_cleaned.csv"

    if test_path.exists():
        if os.name == 'nt':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(step3_clean_dirty(test_path, test_mode=True))
    else:
        print(f"❌ 테스트 파일 없음: {test_path}")