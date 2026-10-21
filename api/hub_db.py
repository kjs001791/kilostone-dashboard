"""PostgreSQL 허브(스키마 hub) 연결. 기존 MariaDB 엔진(api/dependencies.py)과 별개다.

비밀번호는 코드에 두지 않는다. libpq 비밀번호 파일(%APPDATA%\\postgresql\\pgpass.conf)을 쓴다.
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

DEFAULT_DSN = "postgresql+psycopg://postgres@localhost:5432/kilostone"

_engine: Engine | None = None


def get_hub_dsn() -> str:
    return os.getenv("KILOSTONE_PG_DSN", DEFAULT_DSN)


def get_hub_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(get_hub_dsn(), pool_pre_ping=True)
    return _engine
