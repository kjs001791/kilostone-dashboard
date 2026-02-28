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
    # Check 4: 스키마 시점 검증 (2019.05 전후)
    # ----------------------------------------------------------
    print("\n[Check 4] 스키마 시점 변화 검증 (2019.05 기준)")
    split_date = pd.to_datetime("2019-05-01")

    df_old = df[df['date'] < split_date]
    df_new = df[df['date'] >= split_date]

    if len(df_old) > 0:
        old_cum_null_pct = df_old['cumulative_distance'].isna().sum() / len(df_old) * 100
        print(f"  [과거 ~2019.04] {len(df_old)}행")
        print(f"    누적거리 Null 비율: {old_cum_null_pct:.1f}% (높아야 정상)")
        if old_cum_null_pct < 80:
            print(f"    🚨 과거 데이터에 누적거리가 너무 많이 채워져 있음")
            issues += 1

    if len(df_new) > 0:
        new_speed_null_pct = df_new['speed'].isna().sum() / len(df_new) * 100
        new_time_null_pct = df_new['time'].isna().sum() / len(df_new) * 100
        print(f"  [최신 2019.05~] {len(df_new)}행")
        print(f"    속도 Null 비율: {new_speed_null_pct:.1f}% (100%에 가까워야 정상)")
        print(f"    시간 Null 비율: {new_time_null_pct:.1f}% (100%에 가까워야 정상)")
        if new_speed_null_pct < 90:
            print(f"    🚨 최신 데이터에 속도 값이 너무 많이 채워져 있음")
            issues += 1
        if new_time_null_pct < 90:
            print(f"    🚨 최신 데이터에 시간 값이 너무 많이 채워져 있음")
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