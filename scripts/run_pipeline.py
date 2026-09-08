"""
KiloStone 통합 데이터 파이프라인 (CLI 진입점)
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
from pipeline.pipeline_tracker import start_run, finish_run, fail_run
from pipeline.notifier import send_alert_email


def main():
    parser = argparse.ArgumentParser(
        description="KiloStone Data Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 폴더 내 모든 엑셀 파일 처리 (Step1 → Step2 → Step3)
  python scripts/run_pipeline.py --input data/raw/

  # 특정 파일 하나만 처리
  python scripts/run_pipeline.py --input data/raw/driving_log_2016_2020.xlsx

  # AI 생략 (Step1 → Step2만)
  python scripts/run_pipeline.py --input data/raw/ --skip-ai

  # 제안서 검토 완료 후 승인 (Step4 → Step5 → DB 적재)
  python scripts/run_pipeline.py --approve data/staging/cleaning_proposal_xxx.csv --run-id 123
        """,
    )
    parser.add_argument("--input", type=str, help="원본 엑셀 파일 경로 또는 폴더 경로")
    parser.add_argument("--approve", type=str, help="검토 완료된 제안 CSV 경로 (또는 dirty_applied.csv)")
    parser.add_argument("--skip-ai", action="store_true", help="AI API 생략 (Step1~2만)")
    parser.add_argument("--force", action="store_true", help="Step5 검증 실패 시에도 강제 적재")
    parser.add_argument("--run-id", type=int, help="이어받을 파이프라인 실행 ID")
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

        # 파일 목록 수집 (이력 기록용)
        if input_path.is_dir():
            file_names = [f.name for f in input_path.glob("*.xls*") if not f.name.startswith("~$")]
        else:
            file_names = [input_path.name]

        # 파이프라인 실행 시작 기록
        run_id = start_run(file_names)
        print(f"📝 파이프라인 실행 ID: {run_id}")

        try:
            # Step 1: Messy 정제
            cleaned_path = step1_clean_messy(args.input)

            # Step 2: Messy 검증
            step2_check_messy(cleaned_path)

            if args.skip_ai:
                print("\n" + "=" * 60)
                print("⏭️  AI 정제 생략됨 (--skip-ai)")
                print(f"💡 이어서 적재하려면: python scripts/run_pipeline.py --approve {cleaned_path} --run-id {run_id}")
                print("=" * 60)
            else:
                # Step 3: Dirty 정제 (비동기)
                if os.name == 'nt':
                    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
                proposal_path = asyncio.run(step3_clean_dirty(cleaned_path))

                print("\n" + "=" * 60)
                print("🛑 자동 정지: 제안서를 검토하세요")
                print(f"📄 제안서: {proposal_path}")
                print(f"✅ 검토 후: python scripts/run_pipeline.py --approve {proposal_path} --run-id {run_id}")
                print("=" * 60)

        except Exception as e:
            print(f"❌ 파이프라인 중단: {e}")
            fail_run(run_id, str(e))
            sys.exit(1)

    # ----------------------------------------------------------
    # 경로 B: --approve (Step4 → Step5)
    # ----------------------------------------------------------
    elif args.approve:
        approve_path = Path(approve_path := args.approve)
        if not approve_path.exists():
            print(f"❌ 파일 없음: {approve_path}")
            return

        run_id = args.run_id
        rows_processed, rows_rejected = 0, 0
        success = False

        try:
            # --force + dirty_applied 직접 지정 시 → 바로 강제 적재
            if args.force and "dirty_applied" in approve_path.name:
                rows_processed, rows_rejected = step5_force_load(approve_path)
                success = True
            else:
                # Step 4: 제안 적용
                applied_path = step4_approve(approve_path)

                # Step 5: 최종 검증 + DB 적재
                success, rows_processed, rows_rejected = step5_validate_and_load(applied_path)

                if not success and args.force:
                    # Step5 실패했지만 --force 옵션 있음 → 강제 적재
                    print("\n⚡ --force 옵션 감지. 강제 적재 진행...")
                    rows_processed, rows_rejected = step5_force_load(applied_path)
                    success = True

            # 실행 이력 완료 처리
            if success and run_id:
                finish_run(run_id, rows_processed, rows_rejected)
                rejection_rate = (rows_rejected / rows_processed * 100) if rows_processed > 0 else 0.0
                send_alert_email(run_id, rows_processed, rows_rejected, rejection_rate)
                print("\n" + "=" * 60)
                print("🎉 파이프라인 이력 기록 및 완료!")
                print("=" * 60)
            elif not success:
                print("\n💡 이슈 감수하고 적재하려면:")
                print(f"   python scripts/run_pipeline.py --approve {approve_path} --run-id {run_id} --force")

        except Exception as e:
            print(f"❌ 적재 중단: {e}")
            if run_id:
                fail_run(run_id, str(e))
            sys.exit(1)


if __name__ == "__main__":
    main()
