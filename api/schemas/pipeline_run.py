from pydantic import BaseModel
from datetime import datetime
from typing import Optional
import json

class PipelineRunResponse(BaseModel):
    run_id: int
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: str
    input_files: Optional[list[str]] = None
    rows_processed: int
    rows_rejected: int
    rejection_rate: float
    error_message: Optional[str] = None

    @classmethod
    def from_row(cls, row: dict) -> "PipelineRunResponse":
        data = dict(row)
        if data.get("input_files"):
            try:
                data["input_files"] = json.loads(data["input_files"])
            except:
                data["input_files"] = None
        return cls(**data)
