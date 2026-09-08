"""
파이프라인 성과 측정 스크립트
Before(Messy 정제 후) vs After(AI 반영 후) 오류율 비교
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from pipeline.schema_config import LIMITS, convert_time_to_hours


def count_issues(df):
    """dirty_check 로직으로 이상치 건수 카운트"""
    df = df.copy()
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.sort_values(by=['vehicle_id', 'date'])
    df['time_h'] = df['time'].apply(convert_time_to_hours)
    
    issue_ids = set()

    # Check 1: 누적거리 역전
    for vid, group in df.groupby('vehicle_id'):
        group = group.sort_values('date')
        prev_cum = None
        for idx, row in group.iterrows():
            curr_cum = row.get('cumulative_distance')
            if pd.notna(curr_cum) and pd.notna(prev_cum):
                if curr_cum < prev_cum:
                    issue_ids.add(idx)
            if pd.notna(curr_cum):
                prev_cum = curr_cum

    # Check 2: 물리적 한계
    for idx, row in df.iterrows():
        if pd.notna(row.get('speed')) and row['speed'] > LIMITS['MAX_SPEED']:
            issue_ids.add(idx)
        if pd.notna(row.get('fuel_efficiency')):
            if row['fuel_efficiency'] < LIMITS['EFFICIENCY_MIN']:
                issue_ids.add(idx)
            elif row['fuel_efficiency'] > LIMITS['EFFICIENCY_MAX']:
                issue_ids.add(idx)
        if pd.notna(row.get('time_h')) and row['time_h'] > LIMITS['TIME_MAX_HOURS']:
            issue_ids.add(idx)
        if pd.notna(row.get('distance')) and row['distance'] > LIMITS['MAX_DISTANCE']:
            issue_ids.add(idx)

    # Check 3: 수학적 정합성
    for idx, row in df.iterrows():
        dist = row.get('distance')
        speed = row.get('speed')
        time_h = row.get('time_h')
        if pd.notna(dist) and pd.notna(speed) and pd.notna(time_h):
            if dist > 0 and time_h > 0:
                calc_dist = speed * time_h
                error_ratio = abs(dist - calc_dist) / dist
                if error_ratio > LIMITS['DIST_CALC_TOLERANCE']:
                    issue_ids.add(idx)

    return len(issue_ids)


def main():
    # 파일 경로
    before_path = PROJECT_ROOT / "data" / "staging" / "messy_cleaned.csv"
    after_path = PROJECT_ROOT / "data" / "processed" / "driving_log_2016_2020_final.csv"
    proposal_path = PROJECT_ROOT / "data" / "staging" / "cleaning_proposal_20260120_163939.csv"

    # 파일 존재 체크
    for p, name in [(before_path, "Before(messy_cleaned)"), 
                     (after_path, "After(final)"),
                     (proposal_path, "Proposal")]:
        if not p.exists():
            print(f"❌ {name} 파일 없음: {p}")
            sys.exit(1)

    # Before
    df_before = pd.read_csv(before_path)
    total = len(df_before)
    before_issues = count_issues(df_before)

    # After
    df_after = pd.read_csv(after_path)
    after_issues = count_issues(df_after)

    # Proposal 분석
    proposal = pd.read_csv(proposal_path)
    total_proposals = len(proposal)
    auto_fix = len(proposal[
        (proposal['target'] != 'manual_check') & 
        (proposal['proposed'].notna())
    ])
    manual_check = len(proposal[proposal['target'] == 'manual_check'])

    # 계산
    improved = before_issues - after_issues
    improvement_rate = (improved / before_issues * 100) if before_issues > 0 else 0

    # 결과 출력
    print("\n" + "=" * 50)
    print("📊 KiloStone 파이프라인 성과 측정")
    print("=" * 50)

    print(f"\n총 데이터: {total}건")

    print(f"\n[Before] Messy 정제만 한 상태")
    print(f"  이상치: {before_issues}건")
    print(f"  오류율: {before_issues / total * 100:.1f}%")

    print(f"\n[AI 투입]")
    print(f"  Gemini 제안: {total_proposals}건")
    print(f"  자동 수정:   {auto_fix}건")
    print(f"  사람 위임:   {manual_check}건")

    print(f"\n[After] AI 반영 후 최종")
    print(f"  이상치: {after_issues}건")
    print(f"  오류율: {after_issues / total * 100:.1f}%")

    print(f"\n[성과]")
    print(f"  개선 건수: {improved}건")
    print(f"  개선율:    {improvement_rate:.1f}%")
    print(f"  오류율:    {before_issues / total * 100:.1f}% → {after_issues / total * 100:.1f}%")

    print("\n" + "=" * 50)


if __name__ == "__main__":
    main()