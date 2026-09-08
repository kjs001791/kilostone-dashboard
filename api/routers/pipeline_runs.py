from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import text
from sqlalchemy.engine import Engine
from api.dependencies import get_db_engine, get_current_user
from api.schemas.pipeline_run import PipelineRunResponse

router = APIRouter(prefix="/pipeline-runs", tags=["pipeline-runs"])

@router.get("", response_model=list[PipelineRunResponse])
def list_runs(
    limit: int = Query(20, ge=1, le=100),
    engine: Engine = Depends(get_db_engine),
    _: str = Depends(get_current_user),
):
    """최근 파이프라인 실행 이력 목록"""
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT run_id, started_at, finished_at, status,
                       input_files, rows_processed, rows_rejected,
                       rejection_rate, error_message
                FROM pipeline_runs
                ORDER BY started_at DESC
                LIMIT :limit
            """),
            {"limit": limit}
        ).mappings().all()
    return [PipelineRunResponse.from_row(dict(r)) for r in rows]


@router.get("/latest", response_model=PipelineRunResponse)
def get_latest_run(
    engine: Engine = Depends(get_db_engine),
    _: str = Depends(get_current_user),
):
    """가장 최근 완료된 파이프라인 실행 결과"""
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT run_id, started_at, finished_at, status,
                       input_files, rows_processed, rows_rejected,
                       rejection_rate, error_message
                FROM pipeline_runs
                WHERE status = 'completed'
                ORDER BY finished_at DESC
                LIMIT 1
            """)
        ).mappings().one_or_none()

    if row is None:
        raise HTTPException(status_code=404, detail="완료된 파이프라인 실행 이력이 없습니다.")

    return PipelineRunResponse.from_row(dict(row))
