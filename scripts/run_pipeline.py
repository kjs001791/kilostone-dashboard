"""
KiloStone 통합 데이터 파이프라인 (CLI 진입점)

Usage:
  python scripts/run_pipeline.py --input data/raw/파일.xlsx                  # 전체 (Step1~3)
  python scripts/run_pipeline.py --input data/raw/파일.xlsx --skip-ai        # AI 생략 (Step1~2)
  python scripts/run_pipeline.py --approve data/staging/cleaning_proposal.csv # 승인 (Step4~5)
  python scripts/run_pipeline.py --approve data/staging/dirty_applied.csv --force  # 강제 적재
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# scripts/ 디렉토리를 path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.step1_messy_clean import step1_clean_messy
from pipeline.step2_messy_check import step2_check_messy
from pipeline.step3_dirty_clean import step3_clean_dirty
from pipeline.step4_apply_proposal import step4_approve
from pipeline.step5_dirty_check import step5_validate_and_load, step5_force_load


def main():
    parser = argparse.ArgumentParser(
        description="KiloStone Data Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 전체 실행 (Step1 → Step2 → Step3 → 정지)
  python scripts/run_pipeline.py --input data/raw/driving_log_2016_2020.xlsx

  # AI 생략 (Step1 → Step2만)
  python scripts/run_pipeline.py --input data/raw/driving_log_2016_2020.xlsx --skip-ai

  # 제안서 검토 완료 후 승인 (Step4 → Step5 → DB 적재)
  python scripts/run_pipeline.py --approve data/staging/cleaning_proposal_20250101_120000.csv

  # 이슈 감수하고 강제 적재
  python scripts/run_pipeline.py --approve data/staging/dirty_applied.csv --force
        """,
    )
    parser.add_argument("--input", type=str, help="원본 엑셀 파일 경로")
    parser.add_argument("--approve", type=str, help="검토 완료된 제안 CSV 경로 (또는 dirty_applied.csv)")
    parser.add_argument("--skip-ai", action="store_true", help="Gemini API 생략 (Step1~2만)")
    parser.add_argument("--force", action="store_true", help="Step5 검증 실패 시에도 강제 적재")
    args = parser.parse_args()

    # ----------------------------------------------------------
    # 인자 검증
    # ----------------------------------------------------------
    if not args.input and not args.approve:
        parser.print_help()
        return

    if args.input and args.approve:
        print("❌ --input과 --approve는 동시에 사용할 수 없습니다.")
        return

    # ----------------------------------------------------------
    # 경로 A: --input (Step1 → Step2 → Step3)
    # ----------------------------------------------------------
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
            # Step 3: Dirty 정제 (비동기)
            if os.name == 'nt':
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            proposal_path = asyncio.run(step3_clean_dirty(cleaned_path))

            print("\n" + "=" * 60)
            print("🛑 자동 정지: 제안서를 검토하세요")
            print(f"📄 제안서: {proposal_path}")
            print(f"✅ 검토 후: python scripts/run_pipeline.py --approve {proposal_path}")
            print("=" * 60)

    # ----------------------------------------------------------
    # 경로 B: --approve (Step4 → Step5)
    # ----------------------------------------------------------
    elif args.approve:
        approve_path = Path(args.approve)
        if not approve_path.exists():
            print(f"❌ 파일 없음: {approve_path}")
            return

        # --force + dirty_applied 직접 지정 시 → 바로 강제 적재
        if args.force and "dirty_applied" in approve_path.name:
            step5_force_load(approve_path)
            print("\n" + "=" * 60)
            print("🎉 강제 적재 완료!")
            print("=" * 60)
            return

        # Step 4: 제안 적용
        applied_path = step4_approve(approve_path)

        # Step 5: 최종 검증 + DB 적재
        success = step5_validate_and_load(applied_path)

        if success:
            print("\n" + "=" * 60)
            print("🎉 파이프라인 완료!")
            print("=" * 60)
        elif args.force:
            # Step5 실패했지만 --force 옵션 있음 → 강제 적재
            print("\n⚡ --force 옵션 감지. 강제 적재 진행...")
            step5_force_load(applied_path)
            print("\n" + "=" * 60)
            print("🎉 강제 적재 완료! (이슈 감수)")
            print("=" * 60)
        else:
            print("\n💡 이슈 감수하고 적재하려면:")
            print(f"   python scripts/run_pipeline.py --approve {approve_path} --force")


if __name__ == "__main__":
    main()