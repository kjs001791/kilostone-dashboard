"""
Step 2: Messy 정제 검증
컬럼 존재, 값 범위, 스키마 시점 변화, 시간 포맷을 검사합니다.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.schema_config import FINAL_COLUMNS, STAGING_DIR


def step2_check_messy(csv_path, test_mode=False):
    """
    Messy 정제 결과 검증.
    Returns: 발견된 이슈 수 (int)
    """
    print("\n" + "=" * 60)
    print("🔍 STEP 2: Messy 정제 검증")
    print("=" * 60)

    df = pd.read_csv(csv_path)
    df['date'] = pd.to_datetime(df['date'])
    issues = 0

    # ----------------------------------------------------------
    # Check 1: 필수 컬럼 존재
    # ----------------------------------------------------------
    print("\n[Check 1] 필수 컬럼 존재 확인")
    for col in FINAL_COLUMNS:
        if col not in df.columns:
            print(f"  🚨 필수 컬럼 누락: {col}")
            issues += 1
    if issues == 0:
        print("  ✅ 전체 컬럼 정상")

    # ----------------------------------------------------------
    # Check 2: 연비 범위 (컬럼 밀림 탐지)
    # ----------------------------------------------------------
    print("\n[Check 2] 연비 > 10 (컬럼 밀림 의심)")
    bad_eff = df[df['fuel_efficiency'] > 10]
    if not bad_eff.empty:
        print(f"  🚨 연비 > 10: {len(bad_eff)}건")
        print(bad_eff[['date', 'fuel_efficiency', 'distance']].head(3).to_string(index=False))
        issues += 1
    else:
        print("  ✅ 정상")

    # ----------------------------------------------------------
    # Check 3: 거리 < 5km (연비가 거리로 밀렸을 가능성)
    # ----------------------------------------------------------
    print("\n[Check 3] 거리 < 5km")
    bad_dist = df[(df['distance'] < 5) & (df['distance'] > 0)]
    if not bad_dist.empty:
        print(f"  🚨 거리 < 5km: {len(bad_dist)}건")
        print(bad_dist[['date', 'distance', 'fuel_efficiency']].head(3).to_string(index=False))
        issues += 1
    else:
        print("  ✅ 정상")

    # ----------------------------------------------------------
    # Check 4: 스키마 시점 검증 (MAN / 대우 / 스카니아)
    # ----------------------------------------------------------
    print("\n[Check 4] 스키마 시점별 데이터 정합성 검증")
    
    daewoo_start = pd.to_datetime("2019-04-01")
    scania_start = pd.to_datetime("2023-12-01")

    # 1. MAN 기간 (~2019.03)
    df_man = df[df['date'] < daewoo_start]
    if len(df_man) > 0:
        man_cum_null_pct = df_man['cumulative_distance'].isna().sum() / len(df_man) * 100
        man_speed_null_pct = df_man['speed'].isna().sum() / len(df_man) * 100
        print(f"  🚜 [MAN ~2019.03] {len(df_man)}행")
        print(f"    - 누적거리 Null 비율: {man_cum_null_pct:.1f}% (높아야 정상)")
        print(f"    - 속도 Null 비율: {man_speed_null_pct:.1f}% (낮아야 정상)")
        if man_cum_null_pct < 80:
            print("    🚨 MAN 데이터에 누적거리가 너무 많이 채워져 있음")
            issues += 1
        if man_speed_null_pct > 30:
            print("    🚨 MAN 데이터에 속도가 너무 많이 누락됨")
            issues += 1

    # 2. 대우프리마 기간 (2019.04~2023.11)
    df_daewoo = df[(df['date'] >= daewoo_start) & (df['date'] < scania_start)]
    if len(df_daewoo) > 0:
        daewoo_cum_null_pct = df_daewoo['cumulative_distance'].isna().sum() / len(df_daewoo) * 100
        daewoo_speed_null_pct = df_daewoo['speed'].isna().sum() / len(df_daewoo) * 100
        print(f"  🚛 [대우프리마 2019.04~2023.11] {len(df_daewoo)}행")
        print(f"    - 누적거리 Null 비율: {daewoo_cum_null_pct:.1f}% (낮아야 정상)")
        print(f"    - 속도 Null 비율: {daewoo_speed_null_pct:.1f}% (높아야 정상)")
        if daewoo_cum_null_pct > 30:
            print("    🚨 대우 데이터에 누적거리가 너무 많이 누락됨")
            issues += 1
        if daewoo_speed_null_pct < 80:
            print("    🚨 대우 데이터에 속도 값이 불필요하게 채워져 있음")
            issues += 1

    # 3. 스카니아 기간 (2023.12~)
    df_scania = df[df['date'] >= scania_start]
    if len(df_scania) > 0:
        scania_cum_null_pct = df_scania['cumulative_distance'].isna().sum() / len(df_scania) * 100
        scania_speed_null_pct = df_scania['speed'].isna().sum() / len(df_scania) * 100
        scania_extra_null_pct = df_scania['fuel_rate_per_hour'].isna().sum() / len(df_scania) * 100
        print(f"  🏎️ [스카니아 2023.12~] {len(df_scania)}행")
        print(f"    - 누적거리 Null 비율: {scania_cum_null_pct:.1f}% (낮아야 정상)")
        print(f"    - 속도/시간 Null 비율: {scania_speed_null_pct:.1f}% (낮아야 정상)")
        print(f"    - 전용컬럼(l/h) Null 비율: {scania_extra_null_pct:.1f}% (낮아야 정상)")
        if scania_cum_null_pct > 20 or scania_speed_null_pct > 20 or scania_extra_null_pct > 20:
            print("    🚨 스카니아 데이터에 필수 정보가 누락됨")
            issues += 1

    # ----------------------------------------------------------
    # Check 5: 시간 포맷 검증
    # ----------------------------------------------------------
    print("\n[Check 5] 시간 컬럼 포맷 검증 (문자열 HH:MM:SS 여부)")
    time_not_null = df[df['time'].notna()]
    if len(time_not_null) > 0:
        non_string = time_not_null[
            time_not_null['time'].apply(lambda x: not isinstance(x, str))
        ]
        if not non_string.empty:
            print(f"  🚨 문자열이 아닌 시간 데이터: {len(non_string)}건")
            print(non_string[['date', 'time']].head(3).to_string(index=False))
            issues += 1
        else:
            print("  ✅ 전체 문자열 포맷 정상")
    else:
        print("  ℹ️  시간 데이터 없음 (전체 Null)")

    # ----------------------------------------------------------
    # 결과 서머리
    # ----------------------------------------------------------
    print("\n" + "-" * 40)
    if issues == 0:
        print("✅ Messy 검증 통과! 이슈 없음.")
    else:
        print(f"⚠️ {issues}개 이슈 발견. 계속 진행합니다.")
    print("-" * 40)

    return issues


# =================================================================
# 단독 테스트
# =================================================================
if __name__ == "__main__":
    test_path = STAGING_DIR / "messy_cleaned_TEST.csv"
    if not test_path.exists():
        test_path = STAGING_DIR / "messy_cleaned.csv"
    if test_path.exists():
        step2_check_messy(test_path, test_mode=True)
    else:
        print(f"❌ 테스트 파일 없음: {test_path}")