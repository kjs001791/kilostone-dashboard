"""
Step 4: AI 제안 적용
Gemini가 생성한 proposal CSV를 messy_cleaned에 반영하여 dirty_applied.csv 생성.
DB 적재는 하지 않음 (Step 5에서 검증 후 적재).
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.schema_config import STAGING_DIR


def step4_approve(proposal_path, test_mode=False):
    """
    제안서를 messy_cleaned에 반영.
    Returns: 반영된 DataFrame
    """
    print("\n" + "=" * 60)
    print("📝 STEP 4: AI 제안 적용")
    print("=" * 60)

    proposal_path = Path(proposal_path)
    tag = "_TEST" if test_mode else ""

    # messy_cleaned 찾기 (테스트 모드면 _TEST 파일 우선)
    if test_mode:
        messy_path = STAGING_DIR / "messy_cleaned_TEST.csv"
        if not messy_path.exists():
            messy_path = STAGING_DIR / "messy_cleaned.csv"
    else:
        messy_path = STAGING_DIR / "messy_cleaned.csv"

    if not messy_path.exists():
        print(f"❌ {messy_path} 없음. --input으로 Step1을 먼저 실행하세요.")
        sys.exit(1)

    if not proposal_path.exists():
        print(f"❌ 제안서 없음: {proposal_path}")
        sys.exit(1)

    # 데이터 로드
    df = pd.read_csv(messy_path)
    proposal = pd.read_csv(proposal_path)

    print(f"  📄 원본: {messy_path} ({len(df)}행)")
    print(f"  📄 제안서: {proposal_path} ({len(proposal)}행)")

    # manual_check 제외, proposed 값이 있는 것만
    valid = proposal[
        (proposal['target'] != 'manual_check')
        & (proposal['proposed'].notna())
    ].copy()

    # manual_check 건수 리포트
    manual_count = len(proposal[proposal['target'] == 'manual_check'])
    skipped_count = len(proposal) - len(valid) - manual_count
    print(f"  ℹ️  반영 대상: {len(valid)}건")
    print(f"  ℹ️  manual_check (수동 확인 필요): {manual_count}건")
    if skipped_count > 0:
        print(f"  ℹ️  기타 제외: {skipped_count}건")

    # 제안 반영
    success = 0
    errors = 0
    for _, row in valid.iterrows():
        try:
            idx = int(row['id'])
            col = row['target']
            val = row['proposed']

            if idx not in df.index:
                print(f"  ⚠️ ID {idx} 인덱스 범위 초과 → 건너뜀")
                errors += 1
                continue

            if col not in df.columns:
                print(f"  ⚠️ ID {idx} 컬럼 '{col}' 없음 → 건너뜀")
                errors += 1
                continue

            # 타입 맞추기
            if pd.api.types.is_numeric_dtype(df[col]):
                val = float(val)

            df.at[idx, col] = val
            success += 1

        except Exception as e:
            print(f"  ⚠️ ID {row['id']} 오류: {e}")
            errors += 1

    print(f"\n  ✅ 반영 성공: {success}건")
    if errors > 0:
        print(f"  ⚠️ 반영 실패: {errors}건")

    # 결과 저장
    output_path = STAGING_DIR / f"dirty_applied{tag}.csv"
    df.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"  💾 저장: {output_path}")

    return output_path


# =================================================================
# 단독 테스트
# =================================================================
if __name__ == "__main__":
    # 가장 최근 proposal 파일 자동 탐색
    proposals = sorted(STAGING_DIR.glob("cleaning_proposal_TEST_*.csv"))
    if not proposals:
        proposals = sorted(STAGING_DIR.glob("cleaning_proposal_*.csv"))

    if proposals:
        latest = proposals[-1]
        print(f"🔍 최근 제안서 사용: {latest}")
        step4_approve(latest, test_mode=True)
    else:
        print(f"❌ staging 폴더에 제안서 없음: {STAGING_DIR}")