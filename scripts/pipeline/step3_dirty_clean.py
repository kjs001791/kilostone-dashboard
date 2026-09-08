"""
Step 3: Dirty Data 정제 (AI API)
의심 데이터를 필터링하고, AI API에 비동기 배치 요청하여 수정 제안서(proposal) 생성.
"""

import sys
import json
import asyncio
import abc
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
# AI Provider 추상화
# =================================================================
class AIProvider(abc.ABC):
    @abc.abstractmethod
    async def call(self, session, prompt, semaphore, retries=3):
        pass

class GeminiProvider(AIProvider):
    def __init__(self, api_key, api_url):
        self.api_key = api_key
        self.api_url = api_url

    async def call(self, session, prompt, semaphore, retries=3):
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
                    async with session.post(self.api_url, headers=headers, json=data) as resp:
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

# 향후 ClaudeProvider, OpenAIProvider 등 추가 가능

def get_ai_provider():
    import os
    provider_name = os.getenv("AI_PROVIDER", "gemini").lower()
    if provider_name == "gemini":
        return GeminiProvider(API_KEY, API_URL)
    # elif provider_name == "claude":
    #     return ClaudeProvider(...)
    else:
        # Default to Gemini
        return GeminiProvider(API_KEY, API_URL)


# =================================================================
# 참조값 계산
# =================================================================
def add_reference_columns(df):
    """원본 값으로부터 교차검증용 참조값(Reference) 계산"""
    df = df.replace([np.inf, -np.inf], np.nan)

    num_cols = {
        'speed': 'speed_num',
        'consumed_fuel': 'fuel_num',
        'fuel_efficiency': 'eff_num',
        'distance': 'dist_num',
        'consumed_fuel_idle': 'fuel_idl_num',
        'consumed_fuel_pto': 'fuel_pto_num',
    }
    for col, new in num_cols.items():
        if col in df.columns:
            df[new] = pd.to_numeric(df[col], errors='coerce')
        else:
            df[new] = 0

    df['time_num'] = df['time'].apply(convert_time_to_hours)
    df['time_idl_num'] = df['time_idle'].apply(convert_time_to_hours) if 'time_idle' in df.columns else 0
    df['time_pto_num'] = df['time_pto'].apply(convert_time_to_hours) if 'time_pto' in df.columns else 0

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
    
    # 스카니아 전용: 시간당 연료 소모율 검증 (fuel_rate_per_hour ≈ consumed_fuel / time)
    df['ref_fuel_rate'] = df.apply(
        lambda x: round(x['fuel_num'] / x['time_num'], 2)
        if pd.notnull(x['time_num']) and x['time_num'] > 0 else 0,
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

        if 'time' in target:
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
    # 프롬프트 및 Few-Shot 예제 (스카니아 특화 포함)
    # =================================================================
    few_shot_examples = """
    [Case 1: Unit Error (Reurea)]
    - Input: {"id": 10, "reurea": 6}
    - Reasoning: Single digit reurea (1~9) is a recording error. Force replace with standard unit 20L.
    - Output: [{"id": 10, "target": "reurea", "original": 6, "proposed": 20, "reference": null, "reason": "Unit error (6->20L)."}]

    [Case 2: Scania Logic Error (IDL + PTO > TOT)]
    - Input: {"id": 301, "consumed_fuel": 150.5, "consumed_fuel_idle": 120.0, "consumed_fuel_pto": 50.5}
    - Reasoning: IDL(120) + PTO(50.5) = 170.5, which is > TOT(150.5). Impossible. Typo in IDL: 12.0 is more likely.
    - Output: [{"id": 301, "target": "consumed_fuel_idle", "original": 120.0, "proposed": 12.0, "reference": null, "reason": "Scania Logic Error: IDL+PTO > TOT. Corrected IDL decimal (120->12.0)."}]

    [Case 3: Digit Omission (Leading Digit)]
    - Input: {"id": 41, "distance": 36.9, "ref_dist_fuel": 538.75}
    - Reasoning: Original (36.9) too small vs Ref (538.75). Missing leading '5'.
    - Output: [{"id": 41, "target": "distance", "original": 36.9, "proposed": 536.9, "reference": 538.75, "reason": "Missing leading digit '5' (36.9->536.9)."}]

    [Case 4: Scania Fuel Rate Inconsistency]
    - Input: {"id": 402, "fuel_rate_per_hour": 1.1, "consumed_fuel": 110.5, "time": "10:00:00"}
    - Reasoning: Fuel(110.5) / Time(10h) = 11.05. Original fuel_rate(1.1) is missing a digit.
    - Output: [{"id": 402, "target": "fuel_rate_per_hour", "original": 1.1, "proposed": 11.1, "reference": 11.05, "reason": "Fuel rate typo (1.1->11.1) based on fuel/time ratio."}]

    [Case 5: Fat Finger (Double Entry)]
    - Input: {"id": 22, "distance": 4718.1, "ref_dist_fuel": 478.8}
    - Reasoning: 4718.1 impossible (>1500km). Double-tapped '1'.
    - Output: [{"id": 22, "target": "distance", "original": 4718.1, "proposed": 478.1, "reference": 478.8, "reason": "Fat finger typo (4718.1->478.1)."}]

    [Case 6: Scania Time Logic (IDL+PTO > TOT)]
    - Input: {"id": 505, "time": "12:00:00", "time_idle": "10:30:00", "time_pto": "05:00:00"}
    - Reasoning: IDL+PTO (15.5h) > TOT(12h). PTO 05:00 likely typo for 00:50 or 01:00.
    - Output: [{"id": 505, "target": "time_pto", "original": "05:00:00", "proposed": null, "reference": null, "reason": "Scania Time Logic Error: IDL+PTO > TOT. Manual check required."}]

    [Case 7: Cumulative Distance Regression]
    - Input: {"id": 1254, "cumulative_distance": 131185.0, "prev_cum_dist": 131343.0}
    - Reasoning: Current < Previous. Impossible.
    - Output: [{"id": 1254, "target": "cumulative_distance", "original": 131185.0, "proposed": null, "reference": 131343.0, "reason": "Cumulative distance regression. Manual Check."}]
    """

    prompt = f"""
    You are a Data Cleaning Expert for Heavy-duty Truck Logs.
    Your goal is to detect and fix typos by comparing 'User Input' vs 'Calculated Reference'.

    [Scania Vehicle Specifics]
    - TOT (Total) = Driving + IDL (Idle) + PTO.
    - So, TOT >= IDL + PTO must hold for both Fuel and Time.
    - fuel_rate_per_hour (L/h) should be approximately consumed_fuel / time.

    [Context Info (Averages)]
    {context_info}

    [Logic: Visual Pattern Matching]
    1. Compare Original vs Reference.
    2. If significantly different, check for missing digits, misplaced decimals, or keypad neighbors.
    3. Priority: Keep most original digits. Use manual_check if ambiguous.

    [Output Schema]
    Return a JSON list. If valid, return [].
    {{
        "id": (int), "target": (str), "original": (value), "proposed": (value), "reference": (value), "reason": (str)
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
    의심 데이터 필터링 → AI API 배치 호출 → 제안서 CSV 생성.
    Returns: 제안서 파일 경로 (Path)
    """
    print("\n" + "=" * 60)
    print("🤖 STEP 3: Dirty Data 정제 (AI API)")
    print("=" * 60)

    provider = get_ai_provider()
    if not provider.api_key:
        print("❌ API Key가 .env에 없습니다.")
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

            # ----- 의심 데이터 필터 -----

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
            
            # 조건 6: 스카니아 로직 에러 (IDL+PTO > TOT)
            mask_scania = (
                ((group['fuel_idl_num'] + group['fuel_pto_num']) > group['fuel_num'] + 0.1) |
                ((group['time_idl_num'] + group['time_pto_num']) > group['time_num'] + 0.02)
            )

            # 의심 데이터 추출
            suspect = group[
                mask_fuel | mask_phys | mask_time | mask_reurea | mask_cum | mask_scania
            ].copy()

            if suspect.empty:
                continue

            # AI에 보낼 컬럼
            target_cols = [
                'id', 'date', 'vehicle_id', 'distance', 'consumed_fuel',
                'fuel_efficiency', 'time', 'speed', 'reurea',
                'cumulative_distance', 'prev_cum_dist', 'ref_time',
                'fuel_rate_per_hour', 'consumed_fuel_idle', 'consumed_fuel_pto',
                'time_idle', 'time_pto', 'ref_fuel_rate'
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
                    return await provider.call(session, prompt, semaphore)

                tasks.append(process())

        print(f"📦 {len(tasks)}개 배치 예약됨. (무료 API 제한을 위해 순차 처리 및 휴식 도입)")
        
        completed = 0
        for future in asyncio.as_completed(tasks):
            proposals = await future
            completed += 1
            
            # 요청 간 강제 휴식 (RPM 제한 회피)
            await asyncio.sleep(3) 

            if not proposals:
                print(f"  [{completed}/{len(tasks)}] ⏩ Skip (No proposals or Error)")
                continue

            res_df = pd.DataFrame(proposals)
            if res_df.empty or 'target' not in res_df.columns:
                print(f"  [{completed}/{len(tasks)}] ⏩ Skip (Empty result)")
                continue

            # 안전장치
            res_df = res_df[res_df.apply(validate_proposal, axis=1)]
            if res_df.empty:
                print(f"  [{completed}/{len(tasks)}] ⏩ Skip (Invalid proposals filtered)")
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
            
            # 진행률 실시간 출력
            pct = (completed / len(tasks)) * 100
            print(f"  [{completed}/{len(tasks)}] ✅ +{len(merged)}건 반영 완료 ({pct:.1f}%)")

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