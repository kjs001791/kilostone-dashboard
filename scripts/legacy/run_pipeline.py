"""
KiloStone 통합 데이터 파이프라인
Usage:
  python run_pipeline.py --input data/raw/파일.xlsx                  # 전체 실행 (messy → dirty → 제안서)
  python run_pipeline.py --input data/raw/파일.xlsx --skip-ai        # AI 생략 (messy만)
  python run_pipeline.py --approve data/cleaning_proposal_ai_xxx.csv # 검토 완료 후 DB 적재
"""

import argparse
import pandas as pd
import numpy as np
import json
import os
import re
import sys
import asyncio
import aiohttp
import warnings
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

warnings.filterwarnings("ignore")

# 프로젝트 루트
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

# =================================================================
# 설정
# =================================================================
COLUMN_MAPPING = {
    'date': ['날짜', '일자'],
    'fuel_efficiency': ['연비', '1일 평균연비', '1일평균연비', '평균연비', '연    비'],
    'speed': ['평균 운행속도', '평균운행속도', '평균 운행 속도'],
    'time': ['총 운행시간', '운행시간', '총 운행 시간'],
    'distance': ['1일 주행거리', '1일주행거리', '총 운행거리', '운행거리'],
    'cumulative_distance': ['총 주행거리', '총주행거리', '누적주행거리', '누적 운행거리'],
    'consumed_fuel': ['연료 소모량', '1일 연료소모량', '소모량', '연료소모량'],
    'refuel': ['연료주입량', '주입량', '연료 주입량'],
    'reurea': ['요소수', '요소수주입', '요소수 주입량']
}

FINAL_COLUMNS = [
    'date', 'vehicle_id', 'fuel_efficiency', 'speed', 'time',
    'distance', 'cumulative_distance', 'consumed_fuel', 'refuel', 'reurea'
]

LIMITS = {
    'PHYS_ERROR_TOLERANCE': 0.20,
    'FUEL_ERROR_TOLERANCE': 0.01,
    'MAX_HOURS_PER_DAY': 16,
    'MAX_SPEED': 110,
    'MAX_DISTANCE': 1000
}

API_KEY = os.getenv("GOOGLE_API_KEY")
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEY}" if API_KEY else None
CONCURRENCY_LIMIT = 5


# =================================================================
# 유틸리티 함수
# =================================================================
def extract_vehicle_id(df_head):
    try:
        val = str(df_head.columns[0]) + " " + str(df_head.iloc[0, 0])
        if '대우' in val or '프리마' in val: return 'Daewoo Prima'
        if '만' in val or 'MAN' in val: return 'MAN TGX'
        if '스카니아' in val: return 'Scania'
        return 'Unknown Vehicle'
    except:
        return 'Unknown Vehicle'


def fix_time_format(val):
    if pd.isna(val) or str(val).strip() == '' or str(val).strip() == '0':
        return None
    val_str = str(val).strip()
    if ':' in val_str:
        return val_str
    hours, minutes = 0, 0
    match = re.search(r'(\d+)\D+(\d+)', val_str)
    if match:
        hours, minutes = int(match.group(1)), int(match.group(2))
    else:
        try:
            float_val = float(val_str)
            hours = int(float_val)
            decimal_part = round(float_val - hours, 2)
            if decimal_part > 0:
                minutes = int(decimal_part * 100)
        except:
            return None
    return f"{hours:02d}:{minutes:02d}:00"


def clean_numeric(val):
    if pd.isna(val): return None
    s = str(val).replace(',', '').strip()
    try:
        return float(s)
    except:
        return None


def convert_time_to_hours(x):
    if pd.isna(x): return None
    if isinstance(x, (int, float)): return float(x)
    try:
        parts = str(x).strip().split(':')
        if len(parts) == 3: return int(parts[0]) + int(parts[1]) / 60 + int(parts[2]) / 3600
        elif len(parts) == 2: return int(parts[0]) + int(parts[1]) / 60
        return float(x)
    except:
        return None


# =================================================================
# STEP 1: Messy 정제
# =================================================================
def process_sheet(file_path, sheet_name):
    try:
        df_raw = pd.read_excel(file_path, sheet_name=sheet_name, header=None, nrows=20)
    except:
        return None

    vehicle_id = extract_vehicle_id(df_raw)

    header_idx = -1
    for i, row in df_raw.iterrows():
        row_str = " ".join([str(x) for x in row.values])
        if '날짜' in row_str:
            header_idx = i
            break

    if header_idx == -1:
        return None

    df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_idx)

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

    for col in FINAL_COLUMNS:
        if col not in df.columns:
            df[col] = None
    df = df[FINAL_COLUMNS]

    df = df.dropna(subset=['date'])
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date'])
    df['vehicle_id'] = vehicle_id

    num_cols = ['fuel_efficiency', 'speed', 'distance', 'cumulative_distance', 'consumed_fuel', 'refuel', 'reurea']
    for col in num_cols:
        df[col] = df[col].apply(clean_numeric)
    df['time'] = df['time'].apply(fix_time_format)

    return df


def step1_clean_messy(input_file: Path) -> Path:
    print("\n" + "=" * 60)
    print("📋 STEP 1: Messy Data 정제")
    print("=" * 60)

    output_dir = PROJECT_ROOT / 'data' / 'processed'
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / 'messy_cleaned.csv'

    xls = pd.ExcelFile(input_file)
    all_data = []

    for sheet in xls.sheet_names:
        print(f"  Processing: {sheet}...", end=" ")
        processed = process_sheet(input_file, sheet)
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
    numeric_targets = [c for c in ['distance', 'refuel', 'reurea', 'consumed_fuel'] if c in final_df.columns]
    mask_no_numeric = (final_df[numeric_targets].fillna(0) == 0).all(axis=1)
    if 'time' in final_df.columns:
        mask_no_time = final_df['time'].isna() | (final_df['time'].astype(str).str.strip() == '0')
    else:
        mask_no_time = True
    final_df = final_df[~(mask_no_numeric & mask_no_time)]
    print(f"🧹 유령 데이터 제거: {before} → {len(final_df)} ({before - len(final_df)}건)")

    final_df = final_df.sort_values(by='date')
    final_df.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"✅ STEP 1 완료: {output_file}")
    return output_file


# =================================================================
# STEP 2: Messy 검증
# =================================================================
def step2_check_messy(csv_path: Path):
    print("\n" + "=" * 60)
    print("🔍 STEP 2: Messy 정제 검증")
    print("=" * 60)

    df = pd.read_csv(csv_path)
    df['date'] = pd.to_datetime(df['date'])
    issues = 0

    # 컬럼 존재
    for col in FINAL_COLUMNS:
        if col not in df.columns:
            print(f"🚨 필수 컬럼 누락: {col}")
            issues += 1

    # 연비 범위
    bad_eff = df[df['fuel_efficiency'] > 10]
    if not bad_eff.empty:
        print(f"🚨 연비 > 10: {len(bad_eff)}건 (컬럼 밀림 의심)")
        issues += 1

    # 거리 범위
    bad_dist = df[(df['distance'] < 5) & (df['distance'] > 0)]
    if not bad_dist.empty:
        print(f"🚨 거리 < 5km: {len(bad_dist)}건")
        issues += 1

    if issues == 0:
        print("✅ Messy 검증 통과!")
    else:
        print(f"⚠️ {issues}개 이슈 발견. 계속 진행합니다.")


# =================================================================
# STEP 3: Dirty 정제 (Gemini API)
# =================================================================
def add_reference_columns(df):
    df = df.replace([np.inf, -np.inf], np.nan)
    for col, new in {'speed': 'speed_num', 'consumed_fuel': 'fuel_num',
                     'fuel_efficiency': 'eff_num', 'distance': 'dist_num'}.items():
        df[new] = pd.to_numeric(df[col], errors='coerce')
    df['time_num'] = df['time'].apply(convert_time_to_hours)
    df['ref_dist_phys'] = (df['speed_num'] * df['time_num']).round(2)
    df['ref_dist_fuel'] = (df['fuel_num'] * df['eff_num']).round(2)
    df['ref_fuel'] = df.apply(lambda x: round(x['dist_num'] / x['eff_num'], 2) if pd.notnull(x['eff_num']) and x['eff_num'] > 0 else 0, axis=1)
    df['ref_efficiency'] = df.apply(lambda x: round(x['dist_num'] / x['fuel_num'], 2) if pd.notnull(x['fuel_num']) and x['fuel_num'] > 0 else 0, axis=1)
    df['ref_speed'] = df.apply(lambda x: round(x['dist_num'] / x['time_num'], 2) if pd.notnull(x['time_num']) and x['time_num'] > 0 else 0, axis=1)
    df['ref_time'] = df.apply(lambda x: round(x['dist_num'] / x['speed_num'], 2) if pd.notnull(x['speed_num']) and x['speed_num'] > 0 else 0, axis=1)
    return df


def validate_proposal(row):
    try:
        target, val, orig = row['target'], row['proposed'], row['original']
        if pd.isna(val): return True
        if target == 'reurea':
            if pd.isna(orig) or str(orig).strip() == '': return False
            try:
                if float(orig) >= 10 and abs(float(orig) - float(val)) > 5: return False
            except: pass
        if target == 'time':
            parts = str(val).split(':')
            if len(parts) >= 1 and int(parts[0]) >= 24: return False
        elif target == 'distance' and float(val) > LIMITS['MAX_DISTANCE']: return False
        elif target == 'speed' and float(val) > LIMITS['MAX_SPEED']: return False
        return True
    except:
        return False


async def call_gemini(session, prompt, semaphore, retries=3):
    headers = {'Content-Type': 'application/json'}
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"}
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
                    else: return []
            except:
                await asyncio.sleep(3)
    return []


def get_prompt(stats, data_json):
    """Gemini 프롬프트 생성"""
    few_shot = """
    [Case 1: Reurea Unit] Input: reurea=6 → Output: proposed=20 (Standard 20L)
    [Case 2: Copy-Paste] Input: dist==fuel=133.51 → Output: recalc distance
    [Case 3: Digit Omission] Input: dist=36.9, ref=538.75 → Output: 536.9 (missing '5')
    [Case 4: Fuel Digit] Input: fuel=17.51, ref=179.17 → Output: 179.51 (missing '9')
    [Case 5: Fat Finger] Input: dist=4718.1, ref=478.8 → Output: 478.1
    [Case 6: Keypad Typo] Input: dist=638.1, ref=537.3 → Output: 538.1 (6→5)
    [Case 7: Cumulative Regression] Input: cum < prev → Output: null (manual check)
    [Case 8: Time >20h] Input: time=35:27 → Output: 03:27:00
    [Case 9: Distance >1500] Input: dist=5305 → Output: 530.5 (decimal error)
    [Case 10: Ambiguous] → Output: target=manual_check, proposed=null
    """
    return f"""You are a Data Cleaning Expert. Detect and fix typos.
    Context: Avg Dist={stats['avg_dist']:.1f}, Avg Eff={stats['avg_eff']:.2f}, Avg Fuel={stats['avg_fuel']:.1f}
    
    Rules:
    1. Compare Original vs Reference values
    2. Fix with minimum edits to original digits
    3. If ambiguous, set target=manual_check, proposed=null
    
    {few_shot}
    
    Output JSON list: [{{"id":int,"target":str,"original":val,"proposed":val,"reference":val,"reason":str}}]
    If all valid, return [].
    
    Data: {data_json}"""


async def step3_clean_dirty(csv_path: Path) -> Path:
    print("\n" + "=" * 60)
    print("🤖 STEP 3: Dirty Data 정제 (Gemini API)")
    print("=" * 60)

    if not API_KEY:
        print("❌ GOOGLE_API_KEY가 .env에 없습니다.")
        sys.exit(1)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = PROJECT_ROOT / 'data' / f'cleaning_proposal_ai_{timestamp}.csv'

    header_df = pd.DataFrame(columns=['id', 'date', 'vehicle_id', 'target', 'original', 'proposed', 'reference', 'reason'])
    header_df.to_csv(output_path, index=False, encoding='utf-8-sig')

    df = pd.read_csv(csv_path)
    df = add_reference_columns(df)
    df['id'] = df.index
    df['date_dt'] = pd.to_datetime(df['date'])
    df['month'] = df['date_dt'].dt.to_period('M')
    df = df.sort_values(by=['vehicle_id', 'date_dt'])
    df['prev_cum_dist'] = df.groupby('vehicle_id')['cumulative_distance'].shift(1)
    mask_cum_error = (df['cumulative_distance'].notna()) & (df['prev_cum_dist'].notna()) & (df['cumulative_distance'] < df['prev_cum_dist'])

    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    connector = aiohttp.TCPConnector(limit=10, force_close=True)
    total = 0

    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        for month, group in df.groupby('month'):
            stats = {'avg_dist': group['distance'].mean(), 'avg_eff': group['fuel_efficiency'].mean(), 'avg_fuel': group['consumed_fuel'].mean()}

            mask_fuel = (group['consumed_fuel'] > 0) & (group['fuel_efficiency'] > 0) & \
                        (abs((group['distance'] / group['consumed_fuel'] - group['fuel_efficiency']) / group['fuel_efficiency']) > LIMITS['FUEL_ERROR_TOLERANCE'])
            mask_phys = (group['ref_dist_phys'].notna()) & (group['distance'] > 0) & \
                        (abs(group['distance'] - group['ref_dist_phys']) / group['distance'] > LIMITS['PHYS_ERROR_TOLERANCE'])

            def is_invalid_time(t):
                if pd.isna(t) or ':' not in str(t): return False
                try:
                    h, m, s = map(int, str(t).split(':'))
                    return h >= LIMITS['MAX_HOURS_PER_DAY'] or m >= 60
                except: return True
            mask_time = group['time'].apply(is_invalid_time)
            mask_reurea = (group['reurea'].notna()) & (group['reurea'].isin([1, 2, 6]))
            mask_cum = mask_cum_error.loc[group.index]

            suspect = group[mask_fuel | mask_phys | mask_time | mask_reurea | mask_cum].copy()
            if suspect.empty:
                continue

            target_cols = ['id', 'date', 'vehicle_id', 'distance', 'consumed_fuel',
                           'fuel_efficiency', 'time', 'speed', 'reurea',
                           'cumulative_distance', 'prev_cum_dist', 'ref_time']
            for col in target_cols:
                if col not in suspect.columns: suspect[col] = None

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
            if proposals:
                res_df = pd.DataFrame(proposals)
                if res_df.empty or 'target' not in res_df.columns: continue
                res_df = res_df[res_df.apply(validate_proposal, axis=1)]
                if res_df.empty: continue
                res_df['id'] = res_df['id'].astype(int)
                merged = res_df.merge(df[['id', 'date', 'vehicle_id']], on='id', how='left')
                cols = ['id', 'date', 'vehicle_id', 'target', 'original', 'proposed', 'reference', 'reason']
                for c in cols:
                    if c not in merged.columns: merged[c] = None
                merged[cols].dropna(subset=['id']).to_csv(output_path, mode='a', header=False, index=False, encoding='utf-8-sig')
                total += len(merged)
                print(f"  ✅ +{len(merged)}건 (누적 {total})")

    # 정렬
    try:
        final = pd.read_csv(output_path)
        if not final.empty:
            final.sort_values('id').to_csv(output_path, index=False, encoding='utf-8-sig')
    except: pass

    print(f"✅ STEP 3 완료: {output_path}")
    return output_path


# =================================================================
# STEP 4: AI 제안 적용 + DB 적재
# =================================================================
def step4_approve_and_load(proposal_path: Path):
    print("\n" + "=" * 60)
    print("💾 STEP 4: 제안 적용 + DB 적재")
    print("=" * 60)

    # messy_cleaned 찾기
    messy_path = PROJECT_ROOT / 'data' / 'processed' / 'messy_cleaned.csv'
    if not messy_path.exists():
        print(f"❌ {messy_path} 없음. --input으로 먼저 실행하세요.")
        sys.exit(1)

    df = pd.read_csv(messy_path)
    proposal = pd.read_csv(proposal_path)

    # 제안 적용
    valid = proposal[(proposal['target'] != 'manual_check') & (proposal['proposed'].notna())]
    print(f"  반영할 제안: {len(valid)}건")

    count = 0
    for _, row in valid.iterrows():
        try:
            idx = int(row['id'])
            col = row['target']
            val = row['proposed']
            if idx in df.index and col in df.columns:
                if pd.api.types.is_numeric_dtype(df[col]):
                    val = float(val)
                df.at[idx, col] = val
                count += 1
        except Exception as e:
            print(f"  ⚠️ ID {row['id']} 오류: {e}")

    print(f"  ✅ {count}건 적용됨")

    # 최종 CSV 저장
    final_path = PROJECT_ROOT / 'data' / 'processed' / 'final_cleaned.csv'
    df.to_csv(final_path, index=False, encoding='utf-8-sig')

    # DB 적재
    _load_to_db(df)


def _load_to_db(df):
    """DB에 적재 (source='pipeline' 데이터만 교체)"""
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine.url import URL
    import urllib.parse

    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    host = os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT", "3306"))
    dbname = os.getenv("DB_NAME")

    url = URL.create("mysql+pymysql", username=user, password=password, host=host, port=port, database=dbname)
    engine = create_engine(url)

    # 백업
    backup_dir = PROJECT_ROOT / 'data' / 'backups'
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"before_pipeline_{datetime.now():%Y%m%d_%H%M%S}.csv"

    existing = pd.read_sql("SELECT * FROM driving_logs", engine)
    existing.to_csv(backup_path, index=False, encoding='utf-8-sig')
    print(f"  📦 백업 완료: {backup_path} ({len(existing)}건)")

    # pipeline 데이터만 삭제
    with engine.connect() as conn:
        result = conn.execute(text("DELETE FROM driving_logs WHERE source = 'pipeline'"))
        conn.commit()
        print(f"  🗑️ 기존 pipeline 데이터 {result.rowcount}건 삭제")

    # 적재
    valid_columns = [c for c in FINAL_COLUMNS if c in df.columns]
    load_df = df[valid_columns].copy()
    load_df['source'] = 'pipeline'
    load_df = load_df.where(pd.notnull(load_df), None)

    load_df.to_sql('driving_logs', engine, if_exists='append', index=False)
    print(f"  ✅ DB 적재 완료: {len(load_df)}건 (source='pipeline')")
    print(f"  ℹ️  manual 데이터는 보존됨")


# =================================================================
# 메인
# =================================================================
def main():
    parser = argparse.ArgumentParser(description="KiloStone Data Pipeline")
    parser.add_argument("--input", type=str, help="원본 엑셀 파일 경로")
    parser.add_argument("--approve", type=str, help="검토 완료된 제안 CSV 경로")
    parser.add_argument("--skip-ai", action="store_true", help="Gemini API 생략")
    args = parser.parse_args()

    if not args.input and not args.approve:
        parser.print_help()
        return

    if args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"❌ 파일 없음: {input_path}")
            return

        # Step 1: Messy 정제
        cleaned_path = step1_clean_messy(input_path)

        # Step 2: Messy 검증
        step2_check_messy(cleaned_path)

        if args.skip_ai:
            print("\n" + "=" * 60)
            print("⏭️  AI 정제 생략됨 (--skip-ai)")
            print(f"📄 결과: {cleaned_path}")
            print("=" * 60)
        else:
            # Step 3: Dirty 정제
            if os.name == 'nt':
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            proposal_path = asyncio.run(step3_clean_dirty(cleaned_path))

            print("\n" + "=" * 60)
            print("🛑 자동 정지: 제안서를 검토하세요")
            print(f"📄 제안서: {proposal_path}")
            print(f"✅ 검토 후: python run_pipeline.py --approve {proposal_path}")
            print("=" * 60)

    elif args.approve:
        approve_path = Path(args.approve)
        if not approve_path.exists():
            print(f"❌ 파일 없음: {approve_path}")
            return
        step4_approve_and_load(approve_path)

        print("\n" + "=" * 60)
        print("🎉 파이프라인 완료!")
        print("=" * 60)


if __name__ == "__main__":
    main()