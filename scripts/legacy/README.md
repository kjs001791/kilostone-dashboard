# Legacy Scripts (Archived)

파이프라인 통합(`run_pipeline.py`) 이전에 사용하던 개별 스크립트입니다.
현재는 사용하지 않으며, 원본 로직과 프롬프트 참고용으로 보관합니다.

## 파일 목록

| 파일 | 원래 역할 | 통합 위치 |
|------|----------|----------|
| `cleaning_messy_2016_2020.py` | Messy 정제 (2016-2020) | `pipeline/step1_messy_clean.py` |
| `cleaning_messy_2021_2025.py` | Messy 정제 (2021-2025) | 추후 step1에 period_4 추가 |
| `cleaning_dirty_2016_2020.py` | Dirty 정제 + Gemini 프롬프트 | `pipeline/step3_dirty_clean.py` |
| `messy_check.py` | Messy 검증 | `pipeline/step2_messy_check.py` |
| `dirty_check.py` | Dirty 최종 검증 | `pipeline/step5_dirty_check.py` |
| `apply_corrections.py` | AI 제안 수동 반영 | `pipeline/step4_apply_proposal.py` |

## 참고 사항

- `cleaning_dirty_2016_2020.py`에 **원본 Gemini 프롬프트**(Few-shot 10개 Case + Reasoning)가 보관되어 있습니다.
- `step3_dirty_clean.py`의 `get_prompt()` 함수에 원본을 복원할 때 이 파일을 참조하세요.