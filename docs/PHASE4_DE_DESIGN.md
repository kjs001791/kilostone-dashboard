# Phase 4 — 데이터 엔지니어링 고도화 설계서

> 이 문서는 구현 담당자(Gemini)를 위한 상세 명세서입니다.
> Phase 1 파이프라인이 안정화된 후 진행합니다. 설계 결정은 확정되었으며 임의로 변경하지 마세요.

---

## 0. Phase 4 범위 요약

| 작업 | 변경 대상 |
|------|----------|
| `pipeline_runs` 테이블 신규 생성 | DB (DDL) |
| 파이프라인 실행 시 이력 기록 | `scripts/run_pipeline.py` + `scripts/pipeline/step5_dirty_check.py` |
| 이력 조회 API 추가 | `api/routers/pipeline_runs.py` (신규) |
| 대시보드 품질 배너 | `frontend/src/components/dashboard/PipelineBanner.tsx` (신규) |
| 이상치 초과 시 이메일 알림 | `scripts/pipeline/notifier.py` (신규) |
| `.env` 추가 항목 | SMTP 설정 |

---

## 1. DB 스키마 변경

### `pipeline_runs` 테이블 생성

`scripts/db_initializer.py` 또는 별도 마이그레이션 스크립트에서 실행.
기존 `driving_logs` 테이블은 수정하지 않음.

```sql
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id          INT AUTO_INCREMENT PRIMARY KEY,
    started_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at     TIMESTAMP NULL,
    status          ENUM('running', 'completed', 'failed') NOT NULL DEFAULT 'running',
    input_files     TEXT NULL,            -- JSON 배열 문자열 예: '["file1.xlsx","file2.xlsx"]'
    rows_processed  INT NOT NULL DEFAULT 0,
    rows_rejected   INT NOT NULL DEFAULT 0,
    rejection_rate  FLOAT NOT NULL DEFAULT 0.0,   -- rows_rejected / rows_processed * 100
    error_message   TEXT NULL
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

---

## 2. 파이프라인 계측 (Instrumentation)

### 2-1. `scripts/pipeline/pipeline_tracker.py` (신규 파일)

파이프라인 실행 이력을 DB에 기록하는 유틸리티 모듈.
`scripts/run_pipeline.py`와 `step5_dirty_check.py`에서 import해서 사용.

```python
"""
파이프라인 실행 이력 기록 유틸리티
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from sqlalchemy import text

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.services.database import get_db_engine


def start_run(input_files: list[str]) -> int:
    """
    파이프라인 실행 시작 기록. run_id 반환.
    input_files: 처리할 파일명 목록 (경로 아님, 파일명만)
    """
    engine = get_db_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                INSERT INTO pipeline_runs (started_at, status, input_files)
                VALUES (:started_at, 'running', :input_files)
            """),
            {
                "started_at": datetime.now(),
                "input_files": json.dumps(input_files, ensure_ascii=False),
            }
        )
        conn.commit()
        return result.lastrowid


def finish_run(run_id: int, rows_processed: int, rows_rejected: int):
    """
    파이프라인 정상 완료 기록.
    rejection_rate = rows_rejected / rows_processed * 100 (처리 건수가 0이면 0.0)
    """
    rejection_rate = (rows_rejected / rows_processed * 100) if rows_processed > 0 else 0.0
    engine = get_db_engine()
    with engine.connect() as conn:
        conn.execute(
            text("""
                UPDATE pipeline_runs
                SET finished_at     = :finished_at,
                    status          = 'completed',
                    rows_processed  = :rows_processed,
                    rows_rejected   = :rows_rejected,
                    rejection_rate  = :rejection_rate
                WHERE run_id = :run_id
            """),
            {
                "finished_at": datetime.now(),
                "rows_processed": rows_processed,
                "rows_rejected": rows_rejected,
                "rejection_rate": round(rejection_rate, 2),
                "run_id": run_id,
            }
        )
        conn.commit()


def fail_run(run_id: int, error_message: str):
    """
    파이프라인 오류 종료 기록.
    """
    engine = get_db_engine()
    with engine.connect() as conn:
        conn.execute(
            text("""
                UPDATE pipeline_runs
                SET finished_at   = :finished_at,
                    status        = 'failed',
                    error_message = :error_message
                WHERE run_id = :run_id
            """),
            {
                "finished_at": datetime.now(),
                "error_message": error_message[:2000],  # TEXT 컬럼 초과 방지
                "run_id": run_id,
            }
        )
        conn.commit()
```

---

### 2-2. `scripts/pipeline/notifier.py` (신규 파일)

이상치 비율 초과 시 이메일 알림.

```python
"""
파이프라인 이상치 알림 (이메일)
rejection_rate > ALERT_THRESHOLD 일 때 호출
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

ALERT_THRESHOLD = float(os.getenv("ALERT_REJECTION_THRESHOLD", "5.0"))  # 기본 5%


def send_alert_email(run_id: int, rows_processed: int, rows_rejected: int, rejection_rate: float):
    """
    rejection_rate > ALERT_THRESHOLD 일 때 알림 이메일 발송.
    SMTP 설정이 없으면 콘솔 경고만 출력하고 종료 (예외 발생 금지).
    """
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    alert_email = os.getenv("ALERT_EMAIL")

    if rejection_rate <= ALERT_THRESHOLD:
        return  # 임계치 미만 → 발송 안 함

    if not all([smtp_host, smtp_user, smtp_password, alert_email]):
        print(f"⚠️  [알림 생략] rejection_rate={rejection_rate:.1f}% — SMTP 환경변수 미설정")
        return

    subject = f"[KiloStone] 파이프라인 이상치 경고 — dirty 비율 {rejection_rate:.1f}%"
    body = (
        f"파이프라인 실행 ID: {run_id}\n"
        f"처리 건수: {rows_processed}건\n"
        f"이상치(rejected): {rows_rejected}건\n"
        f"이상치 비율: {rejection_rate:.1f}%\n\n"
        f"설정 임계값({ALERT_THRESHOLD}%)을 초과했습니다. 데이터를 확인하세요."
    )

    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = alert_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, alert_email, msg.as_string())
        print(f"📧 알림 이메일 발송 완료 → {alert_email}")
    except Exception as e:
        print(f"⚠️  이메일 발송 실패 (무시하고 계속): {e}")
```

---

### 2-3. `scripts/run_pipeline.py` 수정

기존 `main()` 함수를 아래와 같이 수정.
**변경되는 부분만** 표기 — 나머지 로직은 그대로 유지.

```python
# 기존 import 아래에 추가
from pipeline.pipeline_tracker import start_run, finish_run, fail_run
from pipeline.notifier import send_alert_email
```

`--input` 경로 (Step1~3) 블록:

```python
if args.input:
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ 파일 없음: {input_path}")
        return

    # 파일 목록 수집 (디렉토리인 경우 모든 xlsx)
    if input_path.is_dir():
        file_names = [f.name for f in input_path.glob("*.xlsx")]
    else:
        file_names = [input_path.name]

    # ★ 실행 시작 기록
    run_id = start_run(file_names)
    print(f"📝 파이프라인 실행 ID: {run_id}")

    try:
        cleaned_path = step1_clean_messy(input_path)
        step2_check_messy(cleaned_path)

        if args.skip_ai:
            # skip-ai 모드는 DB 적재 없이 종료 → 이력도 종료하지 않음 (running 상태 유지)
            print("\n⏭️  AI 정제 생략됨 (--skip-ai). 이력 상태는 'running'으로 유지됩니다.")
            # 이력 종료는 --approve 단계에서 처리
        else:
            if os.name == 'nt':
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            proposal_path = asyncio.run(step3_clean_dirty(cleaned_path))
            print(f"\n🛑 자동 정지: 제안서를 검토하세요\n📄 {proposal_path}")
            print(f"✅ 검토 후: python scripts/run_pipeline.py --approve {proposal_path} --run-id {run_id}")
            # run_id를 제안서 파일명 옆에 전달해서 --approve 단계에서 이어받음

    except Exception as e:
        fail_run(run_id, str(e))
        raise
```

`--approve` 경로 (Step4~5) 블록:

```python
elif args.approve:
    approve_path = Path(args.approve)
    if not approve_path.exists():
        print(f"❌ 파일 없음: {approve_path}")
        return

    # run_id를 인자에서 받거나, None으로 진행 (이력 업데이트 생략)
    run_id = args.run_id  # --run-id 인자로 전달받음 (없으면 None)

    try:
        if args.force and "dirty_applied" in approve_path.name:
            rows_processed, rows_rejected = step5_force_load(approve_path)
        else:
            applied_path = step4_approve(approve_path)
            success, rows_processed, rows_rejected = step5_validate_and_load(applied_path)

            if not success and not args.force:
                print("\n💡 이슈 감수하고 적재하려면 --force 옵션 추가")
                return

            if not success and args.force:
                rows_processed, rows_rejected = step5_force_load(applied_path)

        # ★ 완료 기록
        if run_id:
            finish_run(run_id, rows_processed, rows_rejected)
            rejection_rate = (rows_rejected / rows_processed * 100) if rows_processed > 0 else 0.0
            send_alert_email(run_id, rows_processed, rows_rejected, rejection_rate)

        print("\n🎉 파이프라인 완료!")

    except Exception as e:
        if run_id:
            fail_run(run_id, str(e))
        raise
```

`argparse`에 `--run-id` 인자 추가:
```python
parser.add_argument("--run-id", type=int, default=None, help="파이프라인 실행 ID (--approve 단계에서 사용)")
```

---

### 2-4. `step5_dirty_check.py` 반환값 수정

현재 `step5_validate_and_load`는 `bool`을 반환합니다.
Phase 4에서는 `(success: bool, rows_processed: int, rows_rejected: int)` 튜플을 반환하도록 수정.

`step5_force_load` 역시 `(rows_processed: int, rows_rejected: int)` 튜플을 반환하도록 수정.

구체적 수정 위치: `step5_dirty_check.py` 내 DB 적재 직후.
- `rows_processed`: DB에 INSERT된 행 수
- `rows_rejected`: Step 2/5 검증에서 `is_dirty=True` 또는 rejected로 분류된 행 수

---

## 3. FastAPI 엔드포인트 추가

### `api/schemas/pipeline_run.py` (신규)

```python
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
import json

class PipelineRunResponse(BaseModel):
    run_id: int
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: str                         # 'running', 'completed', 'failed'
    input_files: Optional[list[str]] = None
    rows_processed: int
    rows_rejected: int
    rejection_rate: float
    error_message: Optional[str] = None

    @classmethod
    def from_row(cls, row: dict) -> "PipelineRunResponse":
        data = dict(row)
        # input_files는 DB에 JSON 문자열로 저장됨 → 파싱
        if data.get("input_files"):
            try:
                data["input_files"] = json.loads(data["input_files"])
            except (json.JSONDecodeError, TypeError):
                data["input_files"] = None
        return cls(**data)
```

### `api/routers/pipeline_runs.py` (신규)

```python
from fastapi import APIRouter, Depends, Query
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
    """최근 파이프라인 실행 이력 목록 (최신순)"""
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
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="완료된 파이프라인 실행 이력이 없습니다.")

    return PipelineRunResponse.from_row(dict(row))
```

### `api/main.py` 라우터 등록 추가

기존 `main.py`의 `app.include_router(stats_router)` 아래에 추가:

```python
from api.routers.pipeline_runs import router as pipeline_runs_router
app.include_router(pipeline_runs_router)
```

---

## 4. 프론트엔드: 데이터 품질 배너

### `src/types/pipeline_run.ts` (신규)

```typescript
export interface PipelineRun {
  run_id: number;
  started_at: string;
  finished_at: string | null;
  status: "running" | "completed" | "failed";
  input_files: string[] | null;
  rows_processed: number;
  rows_rejected: number;
  rejection_rate: number;
  error_message: string | null;
}
```

### `src/lib/api.ts`에 추가

기존 `statsApi` 객체 아래에 추가:

```typescript
export const pipelineApi = {
  latest: () => apiFetch<import("@/types/pipeline_run").PipelineRun>("/pipeline-runs/latest"),
  list: (limit = 20) => apiFetch<import("@/types/pipeline_run").PipelineRun[]>(`/pipeline-runs?limit=${limit}`),
};
```

### `src/components/dashboard/PipelineBanner.tsx` (신규)

대시보드 상단에 최근 파이프라인 실행 결과를 표시하는 배너.
정상(< 5%): 파란색, 경고(≥ 5%): 노란색, 오류: 빨간색.

```typescript
"use client";

import { useEffect, useState } from "react";
import { pipelineApi } from "@/lib/api";
import { PipelineRun } from "@/types/pipeline_run";
import { format } from "date-fns";
import { ko } from "date-fns/locale";
import { AlertTriangle, CheckCircle, XCircle, Info } from "lucide-react";

const ALERT_THRESHOLD = 5.0;  // 서버와 동일값 유지

export default function PipelineBanner() {
  const [run, setRun] = useState<PipelineRun | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    pipelineApi.latest()
      .then(setRun)
      .catch(() => setError(true));
  }, []);

  if (error || !run) return null;

  const isAlert = run.rejection_rate >= ALERT_THRESHOLD;
  const isFailed = run.status === "failed";

  const colorClass = isFailed
    ? "bg-red-950 border-red-800 text-red-300"
    : isAlert
    ? "bg-yellow-950 border-yellow-700 text-yellow-300"
    : "bg-blue-950 border-blue-800 text-blue-300";

  const Icon = isFailed ? XCircle : isAlert ? AlertTriangle : CheckCircle;

  const dateLabel = run.finished_at
    ? format(new Date(run.finished_at), "M월 d일 HH:mm", { locale: ko })
    : "-";

  return (
    <div className={`flex items-center gap-2 px-3 py-2 rounded-md border text-xs ${colorClass}`}>
      <Icon className="w-4 h-4 flex-shrink-0" />
      {isFailed ? (
        <span>최근 파이프라인 실패 ({dateLabel}) — {run.error_message?.slice(0, 80)}</span>
      ) : (
        <span>
          최근 배치: {dateLabel} · 처리 {run.rows_processed.toLocaleString("ko")}건
          {run.rows_rejected > 0 && (
            <> · dirty <strong>{run.rejection_rate.toFixed(1)}%</strong> ({run.rows_rejected}건)</>
          )}
          {!isAlert && run.rows_rejected === 0 && " · 이상치 없음"}
        </span>
      )}
    </div>
  );
}
```

### `src/app/dashboard/page.tsx` 수정

기존 `<h1>대시보드</h1>` 아래에 배너 삽입:

```typescript
import PipelineBanner from "@/components/dashboard/PipelineBanner";

// ... 기존 return 내부, h1 태그 바로 아래에 추가:
<PipelineBanner />
```

---

## 5. `.env` 추가 항목

```env
# 이메일 알림 (선택 — 없으면 콘솔 경고만 출력하고 무시)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=발신_이메일@gmail.com
SMTP_PASSWORD=Gmail_앱_비밀번호   # Google 계정 → 2단계 인증 → 앱 비밀번호에서 생성
ALERT_EMAIL=수신_이메일@gmail.com
ALERT_REJECTION_THRESHOLD=5.0     # 이 값(%) 초과 시 알림 발송
```

**Gmail 앱 비밀번호 생성 방법:**
1. Google 계정 → 보안 → 2단계 인증 활성화
2. "앱 비밀번호" 메뉴 → 앱: 기타(직접 입력) → "KiloStone" → 생성
3. 표시되는 16자리 비밀번호를 `SMTP_PASSWORD`에 입력

---

## 6. API 엔드포인트 요약 (Phase 4 추가분)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/pipeline-runs` | 최근 실행 이력 목록 (기본 20건) |
| GET | `/pipeline-runs/latest` | 가장 최근 완료된 실행 결과 |

---

## 7. 구현 순서 권고

1. DB `pipeline_runs` 테이블 생성 (DDL 실행)
2. `scripts/pipeline/pipeline_tracker.py` 생성
3. `scripts/pipeline/notifier.py` 생성
4. `scripts/pipeline/step5_dirty_check.py` 반환값 수정 (bool → tuple)
5. `scripts/run_pipeline.py` 수정 (계측 코드 추가)
6. `api/schemas/pipeline_run.py` 생성
7. `api/routers/pipeline_runs.py` 생성
8. `api/main.py` 라우터 등록
9. `src/types/pipeline_run.ts` 생성
10. `src/lib/api.ts`에 `pipelineApi` 추가
11. `src/components/dashboard/PipelineBanner.tsx` 생성
12. `src/app/dashboard/page.tsx`에 배너 삽입
13. `.env` SMTP 항목 추가
14. 파이프라인 테스트 실행 → `pipeline_runs` 테이블 기록 확인
15. `GET /pipeline-runs/latest` 응답 확인
16. 대시보드 배너 표시 확인
17. `ALERT_REJECTION_THRESHOLD=0` 으로 임시 설정하여 이메일 발송 테스트
