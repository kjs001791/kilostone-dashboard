"""
Step 5: 최종 무결성 검증 + DB 적재
dirty_applied.csv를 검증하여 통과하면 DB에 적재, 실패하면 리포트 출력 후 중단.
"""

import os
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.schema_config import (
    LIMITS, FINAL_COLUMNS,
    STAGING_DIR, PROCESSED_DIR, BACKUP_DIR, PROJECT_ROOT,
    convert_time_to_hours,
)


# =================================================================
# 검증 로직
# =================================================================
def run_dirty_check(df):
    """
    최종 데이터 건전성 검사.
    Returns: issues 리스트 (빈 리스트면 통과)
    """
    df = df.copy()

    # 전처리
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values(by=['vehicle_id', 'date'])

    df['time_h'] = df['time'].apply(convert_time_to_hours)
    df['time_idl_h'] = df['time_idle'].apply(convert_time_to_hours) if 'time_idle' in df.columns else 0
    df['time_pto_h'] = df['time_pto'].apply(convert_time_to_hours) if 'time_pto' in df.columns else 0

    issues = []

    # ----------------------------------------------------------
    # Check 1: 누적 주행거리 역전
    # ----------------------------------------------------------
    print("  [Check 1] 누적 주행거리 역전 검사...")
    for vid, group in df.groupby('vehicle_id'):
        group = group.sort_values('date')
        prev_cum = None

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
                        'message': f"누적거리 역전 (이전: {prev_cum} > 현재: {curr_cum})",
                    })

            if pd.notna(curr_cum):
                prev_cum = curr_cum

    check1_count = len(issues)
    print(f"    → {check1_count}건 발견")

    # ----------------------------------------------------------
    # Check 2: 물리적 한계 초과
    # ----------------------------------------------------------
    print("  [Check 2] 물리적 한계값 검사...")
    before_count = len(issues)

    for idx, row in df.iterrows():
        row_id = row.get('id', idx)

        # 속도
        if pd.notna(row.get('speed')) and row['speed'] > LIMITS['MAX_SPEED']:
            issues.append({
                'id': row_id,
                'date': row['date'],
                'issue_type': 'Outlier',
                'column': 'speed',
                'value': row['speed'],
                'message': f"속도 과다 ({row['speed']} > {LIMITS['MAX_SPEED']} km/h)",
            })

        # 연비 범위
        if pd.notna(row.get('fuel_efficiency')):
            if row['fuel_efficiency'] < LIMITS['EFFICIENCY_MIN']:
                issues.append({
                    'id': row_id,
                    'date': row['date'],
                    'issue_type': 'Outlier',
                    'column': 'fuel_efficiency',
                    'value': row['fuel_efficiency'],
                    'message': f"연비 과소 ({row['fuel_efficiency']} < {LIMITS['EFFICIENCY_MIN']})",
                })
            elif row['fuel_efficiency'] > LIMITS['EFFICIENCY_MAX']:
                issues.append({
                    'id': row_id,
                    'date': row['date'],
                    'issue_type': 'Outlier',
                    'column': 'fuel_efficiency',
                    'value': row['fuel_efficiency'],
                    'message': f"연비 과다 ({row['fuel_efficiency']} > {LIMITS['EFFICIENCY_MAX']})",
                })

        # 운행 시간
        if pd.notna(row.get('time_h')) and row['time_h'] > LIMITS['TIME_MAX_HOURS']:
            issues.append({
                'id': row_id,
                'date': row['date'],
                'issue_type': 'Outlier',
                'column': 'time',
                'value': row.get('time'),
                'message': f"운행 시간 과다 ({row['time_h']:.1f}h > {LIMITS['TIME_MAX_HOURS']}h)",
            })

        # 거리
        if pd.notna(row.get('distance')) and row['distance'] > LIMITS['MAX_DISTANCE']:
            issues.append({
                'id': row_id,
                'date': row['date'],
                'issue_type': 'Outlier',
                'column': 'distance',
                'value': row['distance'],
                'message': f"거리 과다 ({row['distance']} > {LIMITS['MAX_DISTANCE']} km)",
            })

    check2_count = len(issues) - before_count
    print(f"    → {check2_count}건 발견")

    # ----------------------------------------------------------
    # Check 3: 수학적 정합성 (distance vs speed × time)
    # ----------------------------------------------------------
    print("  [Check 3] 수학적 정합성 검사...")
    before_count = len(issues)

    for idx, row in df.iterrows():
        dist = row.get('distance')
        speed = row.get('speed')
        time_h = row.get('time_h')

        if pd.notna(dist) and pd.notna(speed) and pd.notna(time_h):
            if dist > 0 and time_h > 0:
                calc_dist = speed * time_h
                error_ratio = abs(dist - calc_dist) / dist

                if error_ratio > LIMITS['DIST_CALC_TOLERANCE']:
                    issues.append({
                        'id': row.get('id', idx),
                        'date': row['date'],
                        'issue_type': 'Math Mismatch',
                        'column': 'distance/speed/time',
                        'value': f"Dist:{dist} vs Calc:{calc_dist:.1f}",
                        'message': f"물리적 거리 불일치 ({error_ratio * 100:.1f}%)",
                    })

    # ----------------------------------------------------------
    # Check 4: 스카니아 로직 검증 (IDL + PTO <= TOT)
    # ----------------------------------------------------------
    print("  [Check 4] 스카니아 복합 로직 검증...")
    for idx, row in df.iterrows():
        # 연료 (TOT >= IDL + PTO)
        fuel_tot = row.get('consumed_fuel', 0)
        fuel_idl = row.get('consumed_fuel_idle', 0)
        fuel_pto = row.get('consumed_fuel_pto', 0)
        
        if pd.notna(fuel_tot) and (pd.notna(fuel_idl) or pd.notna(fuel_pto)):
            if fuel_idl + fuel_pto > fuel_tot + 0.1: # 0.1L 오차 허용
                issues.append({
                    'id': row.get('id', idx),
                    'date': row['date'],
                    'issue_type': 'Logic Error',
                    'column': 'consumed_fuel',
                    'value': fuel_tot,
                    'message': f"스카니아 연료 로직 오류 (TOT:{fuel_tot} < IDL+PTO:{fuel_idl + fuel_pto})",
                })
        
        # 시간 (TOT >= IDL + PTO)
        time_h = row.get('time_h', 0)
        time_idl_h = row.get('time_idl_h', 0)
        time_pto_h = row.get('time_pto_h', 0)
        
        if pd.notna(time_h) and (pd.notna(time_idl_h) or pd.notna(time_pto_h)):
            if time_idl_h + time_pto_h > time_h + 0.02: # 약 1분 오차 허용
                issues.append({
                    'id': row.get('id', idx),
                    'date': row['date'],
                    'issue_type': 'Logic Error',
                    'column': 'time',
                    'value': row.get('time'),
                    'message': f"스카니아 시간 로직 오류 (TOT:{time_h:.2f}h < IDL+PTO:{time_idl_h + time_pto_h:.2f}h)",
                })

    check4_count = len(issues) - before_count
    print(f"    → {len(issues) - before_count}건 발견")

    return issues


# =================================================================
# DB 적재
# =================================================================
def load_to_db(df):
    """source='pipeline' 데이터만 교체 적재"""
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine.url import URL

    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    host = os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT", "3306"))
    dbname = os.getenv("DB_NAME")

    url = URL.create(
        "mysql+pymysql",
        username=user, password=password,
        host=host, port=port, database=dbname,
    )
    engine = create_engine(url)

    # 백업
    backup_path = BACKUP_DIR / f"before_pipeline_{datetime.now():%Y%m%d_%H%M%S}.csv"
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
# Step 5 메인
# =================================================================
def step5_validate_and_load(applied_path, test_mode=False):
    """
    최종 검증 → 통과 시 DB 적재 + processed에 최종 CSV 저장.
    실패 시 리포트 출력 + 적재 중단.
    Returns: (success: bool, rows_processed: int, rows_rejected: int)
    """
    print("\n" + "=" * 60)
    print("🔍 STEP 5: 최종 무결성 검증" + (" (TEST MODE)" if test_mode else ""))
    print("=" * 60)

    applied_path = Path(applied_path)
    tag = "_TEST" if test_mode else ""

    if not applied_path.exists():
        print(f"❌ 파일 없음: {applied_path}")
        sys.exit(1)

    df = pd.read_csv(applied_path)
    print(f"  📄 검증 대상: {applied_path} ({len(df)}행)")

    # 검증 실행
    issues = run_dirty_check(df)
    
    rows_processed = len(df)
    rows_rejected = len(issues)

    # ----------------------------------------------------------
    # 결과 처리
    # ----------------------------------------------------------
    if issues:
        # 리포트 저장
        report_path = STAGING_DIR / f"dirty_check_report{tag}.csv"
        report_df = pd.DataFrame(issues)
        report_df = report_df[['id', 'date', 'issue_type', 'column', 'value', 'message']]
        report_df.to_csv(report_path, index=False, encoding='utf-8-sig')

        print("\n" + "-" * 40)
        print(f"⚠️ {len(issues)}건의 이상 데이터 발견")
        print(f"  - Logic Error: {sum(1 for i in issues if i['issue_type'] == 'Logic Error')}건")
        print(f"  - Outlier: {sum(1 for i in issues if i['issue_type'] == 'Outlier')}건")
        print(f"  - Math Mismatch: {sum(1 for i in issues if i['issue_type'] == 'Math Mismatch')}건")
        print(f"📄 리포트: {report_path}")
        print("-" * 40)

        # 사용자 판단 요청
        print("\n선택지:")
        print("  1) 리포트 확인 후 수동 수정 → 다시 --approve 실행")
        print("  2) 이슈를 감수하고 강제 적재하려면 --force 옵션 추가")

        if not test_mode:
            # --force 옵션 체크는 run_pipeline.py에서 처리
            print("\n❌ 적재 중단. 리포트를 확인하세요.")
            return False, rows_processed, rows_rejected
        else:
            print("\n🧪 테스트 모드: DB 적재 건너뜀")
            return False, rows_processed, rows_rejected
    else:
        print("\n" + "-" * 40)
        print("✅ 검증 통과! 이상 데이터 없음.")
        print("-" * 40)

    # ----------------------------------------------------------
    # 통과 → 최종 CSV 저장 + DB 적재
    # ----------------------------------------------------------
    # 최종 CSV
    final_csv = PROCESSED_DIR / f"driving_log_final{tag}.csv"
    df.to_csv(final_csv, index=False, encoding='utf-8-sig')
    print(f"  💾 최종 CSV: {final_csv}")

    # DB 적재 (테스트 모드에서는 건너뜀)
    if test_mode:
        print("  🧪 테스트 모드: DB 적재 건너뜀")
    else:
        load_to_db(df)

    return True, rows_processed, rows_rejected


def step5_force_load(applied_path):
    """이슈 감수하고 강제 적재 (--force용)"""
    print("\n" + "=" * 60)
    print("⚡ STEP 5: 강제 적재 (이슈 감수)")
    print("=" * 60)

    applied_path = Path(applied_path)
    df = pd.read_csv(applied_path)

    # 최종 CSV
    final_csv = PROCESSED_DIR / "driving_log_final.csv"
    df.to_csv(final_csv, index=False, encoding='utf-8-sig')
    print(f"  💾 최종 CSV: {final_csv}")

    # DB 적재
    load_to_db(df)
    
    # 강제 적재 시에도 통계는 계산
    issues = run_dirty_check(df)
    return len(df), len(issues)


# =================================================================
# 단독 테스트
# =================================================================
if __name__ == "__main__":
    test_path = STAGING_DIR / "dirty_applied_TEST.csv"
    if not test_path.exists():
        test_path = STAGING_DIR / "dirty_applied.csv"

    if test_path.exists():
        step5_validate_and_load(test_path, test_mode=True)
    else:
        print(f"❌ 테스트 파일 없음: {test_path}")
        print(f"   Step4를 먼저 실행하세요.")