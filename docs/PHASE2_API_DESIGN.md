# Phase 2 — FastAPI 백엔드 구현 설계서

> 이 문서는 구현 담당자(Gemini)를 위한 상세 명세서입니다.
> 설계 결정은 이미 완료되었으며, 임의로 변경하지 마세요.

---

## 0. 전제 조건 및 금지사항

**반드시 지킬 것:**
- `api/` 디렉토리 내부 어디서도 `import streamlit` 금지
- `@st.cache_data`, `st.error()`, `st.session_state` 등 Streamlit API 일절 사용 금지
- 기존 `app/` 디렉토리 코드는 수정하지 않음 (Streamlit 앱과 병렬 운영)
- DB 쿼리는 반드시 `sqlalchemy.text()` + named parameter (`:param_name`) 사용 — f-string SQL 절대 금지
- 모든 에러는 `raise HTTPException(status_code=..., detail="...")` 로 처리

**참고할 기존 파일:**
- `app/services/database.py` — DB 엔진 생성 패턴 참고
- `app/services/data_validator.py` — 검증 로직 참고 (포팅 대상)
- `app/auth/login_guard.py` — IP 차단 로직 참고 (포팅 대상)

---

## 1. 신규 패키지 설치

`requirements.txt` 하단에 아래 항목 추가:

```
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4
```

기존 패키지 (`sqlalchemy`, `pymysql`, `python-dotenv`) 는 그대로 재사용.

---

## 2. `.env` 추가 항목

기존 `.env` 파일에 아래 항목 추가 (DB 관련 기존 항목은 그대로 유지):

```env
# FastAPI Auth
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=<bcrypt 해시값 — 아래 생성 방법 참고>
JWT_SECRET_KEY=<랜덤 32바이트 hex — 아래 생성 방법 참고>
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# CORS
FRONTEND_URL=http://localhost:3000
```

**해시값 생성 방법 (최초 1회 실행):**
```python
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"])
print(pwd_context.hash("실제_비밀번호"))
```

**JWT_SECRET_KEY 생성 방법:**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## 3. 디렉토리 구조 (신규 생성)

```
api/
├── Dockerfile
├── __init__.py
├── main.py
├── dependencies.py
├── auth/
│   ├── __init__.py
│   ├── router.py
│   ├── service.py
│   └── middleware.py
├── routers/
│   ├── __init__.py
│   ├── logs.py
│   └── stats.py
└── schemas/
    ├── __init__.py
    ├── auth.py
    ├── log.py
    └── stats.py
```

---

## 4. DB 스키마 (최종 확정)

Phase 1 완료 후 `driving_logs` 테이블의 전체 컬럼:

| 컬럼명 | 타입 | Nullable | 비고 |
|--------|------|----------|------|
| id | INT AUTO_INCREMENT | NO | PK |
| date | DATE | NO | |
| vehicle_id | VARCHAR(50) | NO | |
| distance | FLOAT | NO | km |
| cumulative_distance | FLOAT | YES | MAN은 NULL |
| speed | FLOAT | YES | 대우프리마는 NULL |
| time | VARCHAR(10) | YES | HH:MM 형식 |
| time_idle | VARCHAR(10) | YES | 스카니아 전용 |
| time_pto | VARCHAR(10) | YES | 스카니아 전용 |
| fuel_efficiency | FLOAT | YES | km/L |
| fuel_rate_per_hour | FLOAT | YES | 스카니아 전용, L/h |
| consumed_fuel | FLOAT | YES | L |
| consumed_fuel_idle | FLOAT | YES | 스카니아 전용 |
| consumed_fuel_pto | FLOAT | YES | 스카니아 전용 |
| refuel | FLOAT | YES | L |
| reurea | FLOAT | YES | L |
| source | VARCHAR(20) | NO | 'pipeline' or 'manual' |
| created_at | TIMESTAMP | NO | DEFAULT CURRENT_TIMESTAMP |

---

## 5. 파일별 구현 명세

### 5-1. `api/schemas/log.py`

```python
from pydantic import BaseModel, field_validator
from datetime import date, datetime
from typing import Optional

class DrivingLogBase(BaseModel):
    date: date
    vehicle_id: str
    distance: float
    cumulative_distance: Optional[float] = None
    speed: Optional[float] = None
    time: Optional[str] = None          # "HH:MM" 형식
    time_idle: Optional[str] = None
    time_pto: Optional[str] = None
    fuel_efficiency: Optional[float] = None
    fuel_rate_per_hour: Optional[float] = None
    consumed_fuel: Optional[float] = None
    consumed_fuel_idle: Optional[float] = None
    consumed_fuel_pto: Optional[float] = None
    refuel: Optional[float] = None
    reurea: Optional[float] = None

class DrivingLogCreate(DrivingLogBase):
    # 아래 validator들은 app/services/data_validator.py 로직을 Pydantic으로 포팅한 것
    @field_validator('fuel_efficiency')
    @classmethod
    def check_fuel_efficiency(cls, v):
        if v is not None and not (1.0 <= v <= 5.0):
            raise ValueError(f"연비 {v} km/L가 허용 범위(1.0~5.0)를 벗어났습니다.")
        return v

    @field_validator('distance')
    @classmethod
    def check_distance(cls, v):
        if v is not None and not (10 <= v <= 1500):
            raise ValueError(f"주행거리 {v} km가 비정상적입니다.")
        return v

    @field_validator('speed')
    @classmethod
    def check_speed(cls, v):
        if v is not None and not (5 <= v <= 120):
            raise ValueError(f"평균속도 {v} km/h가 비정상적입니다.")
        return v

class DrivingLogUpdate(DrivingLogBase):
    # PUT 시 모든 필드 선택적 (date 포함)
    date: Optional[date] = None
    vehicle_id: Optional[str] = None
    distance: Optional[float] = None

class DrivingLogResponse(DrivingLogBase):
    id: int
    source: str
    created_at: datetime

    model_config = {"from_attributes": True}

class LogsPage(BaseModel):
    total: int
    page: int
    per_page: int
    items: list[DrivingLogResponse]
```

### 5-2. `api/schemas/auth.py`

```python
from pydantic import BaseModel

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
```

### 5-3. `api/schemas/stats.py`

```python
from pydantic import BaseModel
from typing import Optional

class StatsSummary(BaseModel):
    total_distance: float
    avg_fuel_efficiency: Optional[float]
    total_consumed_fuel: Optional[float]
    total_records: int

class MonthlyStats(BaseModel):
    year: int
    month: int
    total_distance: float
    avg_fuel_efficiency: Optional[float]
    total_consumed_fuel: Optional[float]
    record_count: int

class StatsResponse(BaseModel):
    summary: StatsSummary
    monthly: list[MonthlyStats]
```

### 5-4. `api/dependencies.py`

`app/services/database.py`를 FastAPI용으로 재구현.
차이점: DEBUG print 제거, Streamlit 의존성 없음.

```python
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import URL
from pathlib import Path
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from api.auth.service import decode_access_token

env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=env_path)

_engine: Engine | None = None

def get_db_engine() -> Engine:
    global _engine
    if _engine is None:
        connection_url = URL.create(
            drivername="mysql+pymysql",
            username=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT", "3306")),
            database=os.getenv("DB_NAME"),
        )
        _engine = create_engine(connection_url, pool_recycle=3600, pool_pre_ping=True)
    return _engine

security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    token = credentials.credentials
    username = decode_access_token(token)
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않거나 만료된 토큰입니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return username
```

`pool_pre_ping=True` 추가: 쿼리 전 DB 연결 유효성 자동 확인 (MariaDB 재시작 후 연결 오류 방지).

### 5-5. `api/auth/service.py`

```python
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def authenticate_user(username: str, password: str) -> bool:
    expected_username = os.getenv("ADMIN_USERNAME")
    expected_hash = os.getenv("ADMIN_PASSWORD_HASH")
    if username != expected_username:
        return False
    return verify_password(password, expected_hash)

def create_access_token(username: str) -> str:
    expire_minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
    expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    payload = {"sub": username, "exp": expire, "type": "access"}
    return jwt.encode(payload, os.getenv("JWT_SECRET_KEY"), algorithm="HS256")

def create_refresh_token(username: str) -> str:
    expire_days = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    expire = datetime.now(timezone.utc) + timedelta(days=expire_days)
    payload = {"sub": username, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, os.getenv("JWT_SECRET_KEY"), algorithm="HS256")

def decode_access_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET_KEY"), algorithms=["HS256"])
        if payload.get("type") != "access":
            return None
        return payload.get("sub")
    except JWTError:
        return None

def decode_refresh_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET_KEY"), algorithms=["HS256"])
        if payload.get("type") != "refresh":
            return None
        return payload.get("sub")
    except JWTError:
        return None
```

### 5-6. `api/auth/middleware.py`

`app/auth/login_guard.py` 로직을 FastAPI 미들웨어로 포팅.
Streamlit 의존성 완전 제거. JSON 파일 기반 상태 유지 (기존과 동일 방식).

```python
import json
import os
from datetime import datetime
from pathlib import Path
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
BLOCKED_FILE = DATA_DIR / "api_blocked_ips.json"
ATTEMPTS_FILE = DATA_DIR / "api_login_attempts.json"
MAX_ATTEMPTS = 5
LOGIN_PATH = "/auth/login"

def _load(path: Path, default) -> dict:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        pass
    return default

def _save(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"

def is_blocked(ip: str) -> bool:
    data = _load(BLOCKED_FILE, {"blocked": []})
    return any(entry.get("ip") == ip for entry in data["blocked"])

def increment_attempts(ip: str) -> int:
    data = _load(ATTEMPTS_FILE, {})
    data[ip] = data.get(ip, 0) + 1
    _save(ATTEMPTS_FILE, data)
    return data[ip]

def reset_attempts(ip: str):
    data = _load(ATTEMPTS_FILE, {})
    data.pop(ip, None)
    _save(ATTEMPTS_FILE, data)

def block_ip(ip: str):
    data = _load(BLOCKED_FILE, {"blocked": []})
    if not any(e.get("ip") == ip for e in data["blocked"]):
        data["blocked"].append({"ip": ip, "blocked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        _save(BLOCKED_FILE, data)

class IPRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 로그인 엔드포인트에만 적용
        if request.url.path != LOGIN_PATH:
            return await call_next(request)

        ip = _get_ip(request)

        if is_blocked(ip):
            return JSONResponse(
                status_code=403,
                content={"detail": f"IP {ip}가 차단되었습니다. 관리자에게 문의하세요."}
            )

        response = await call_next(request)

        # 로그인 실패(401) 시 시도 횟수 증가
        if response.status_code == 401:
            count = increment_attempts(ip)
            if count >= MAX_ATTEMPTS:
                block_ip(ip)
        elif response.status_code == 200:
            reset_attempts(ip)

        return response
```

**주의**: 이 미들웨어는 `app/auth/login_guard.py`와 별개 파일을 씁니다 (`api_blocked_ips.json`, `api_login_attempts.json`). 기존 Streamlit 앱 차단 상태와 분리.

### 5-7. `api/auth/router.py`

```python
from fastapi import APIRouter, HTTPException, Response, Request, status
from fastapi.responses import JSONResponse
from api.schemas.auth import LoginRequest, TokenResponse
from api.auth.service import authenticate_user, create_access_token, create_refresh_token, decode_refresh_token
import os

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
REFRESH_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, response: Response):
    if not authenticate_user(body.username, body.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="아이디 또는 비밀번호가 틀렸습니다.")

    access_token = create_access_token(body.username)
    refresh_token = create_refresh_token(body.username)

    response.set_cookie(
        key=REFRESH_COOKIE,
        value=refresh_token,
        httponly=True,       # JS 접근 불가 (XSS 방어)
        secure=True,         # HTTPS 전용
        samesite="lax",
        max_age=60 * 60 * 24 * REFRESH_EXPIRE_DAYS,
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request):
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="refresh_token 쿠키가 없습니다.")

    username = decode_refresh_token(token)
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않거나 만료된 refresh token입니다.")

    return {"access_token": create_access_token(username), "token_type": "bearer"}

@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key=REFRESH_COOKIE, httponly=True, secure=True, samesite="lax")
    return {"message": "로그아웃 되었습니다."}
```

### 5-8. `api/routers/logs.py`

```python
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.engine import Engine
from typing import Optional
from datetime import date
from api.dependencies import get_db_engine, get_current_user
from api.schemas.log import DrivingLogCreate, DrivingLogUpdate, DrivingLogResponse, LogsPage

router = APIRouter(prefix="/logs", tags=["logs"])

ALL_COLUMNS = """
    id, date, vehicle_id, distance, cumulative_distance,
    speed, time, time_idle, time_pto,
    fuel_efficiency, fuel_rate_per_hour,
    consumed_fuel, consumed_fuel_idle, consumed_fuel_pto,
    refuel, reurea, source, created_at
"""

@router.get("", response_model=LogsPage)
def get_logs(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    vehicle_id: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    engine: Engine = Depends(get_db_engine),
    _: str = Depends(get_current_user),
):
    offset = (page - 1) * per_page
    filters = []
    params: dict = {"limit": per_page, "offset": offset}

    if vehicle_id:
        filters.append("vehicle_id = :vehicle_id")
        params["vehicle_id"] = vehicle_id
    if date_from:
        filters.append("date >= :date_from")
        params["date_from"] = date_from
    if date_to:
        filters.append("date <= :date_to")
        params["date_to"] = date_to

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    with engine.connect() as conn:
        total = conn.execute(text(f"SELECT COUNT(*) FROM driving_logs {where}"), params).scalar()
        rows = conn.execute(
            text(f"SELECT {ALL_COLUMNS} FROM driving_logs {where} ORDER BY date DESC LIMIT :limit OFFSET :offset"),
            params
        ).mappings().all()

    return {"total": total, "page": page, "per_page": per_page, "items": [dict(r) for r in rows]}


@router.post("", response_model=DrivingLogResponse, status_code=status.HTTP_201_CREATED)
def create_log(
    body: DrivingLogCreate,
    engine: Engine = Depends(get_db_engine),
    _: str = Depends(get_current_user),
):
    data = body.model_dump()
    data["source"] = "manual"

    columns = ", ".join(data.keys())
    placeholders = ", ".join(f":{k}" for k in data.keys())

    with engine.connect() as conn:
        result = conn.execute(text(f"INSERT INTO driving_logs ({columns}) VALUES ({placeholders})"), data)
        conn.commit()
        new_id = result.lastrowid

    with engine.connect() as conn:
        row = conn.execute(text(f"SELECT {ALL_COLUMNS} FROM driving_logs WHERE id = :id"), {"id": new_id}).mappings().one()
    return dict(row)


@router.put("/{log_id}", response_model=DrivingLogResponse)
def update_log(
    log_id: int,
    body: DrivingLogUpdate,
    engine: Engine = Depends(get_db_engine),
    _: str = Depends(get_current_user),
):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    if not data:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="수정할 필드가 없습니다.")

    data["source"] = "manual"
    data["id"] = log_id

    set_clause = ", ".join(f"{k} = :{k}" for k in data.keys() if k != "id")

    with engine.connect() as conn:
        result = conn.execute(text(f"UPDATE driving_logs SET {set_clause} WHERE id = :id"), data)
        conn.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"id={log_id} 기록을 찾을 수 없습니다.")

    with engine.connect() as conn:
        row = conn.execute(text(f"SELECT {ALL_COLUMNS} FROM driving_logs WHERE id = :id"), {"id": log_id}).mappings().one()
    return dict(row)


@router.delete("/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_log(
    log_id: int,
    engine: Engine = Depends(get_db_engine),
    _: str = Depends(get_current_user),
):
    with engine.connect() as conn:
        result = conn.execute(text("DELETE FROM driving_logs WHERE id = :id"), {"id": log_id})
        conn.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"id={log_id} 기록을 찾을 수 없습니다.")
```

### 5-9. `api/routers/stats.py`

```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.engine import Engine
from typing import Optional
from api.dependencies import get_db_engine, get_current_user
from api.schemas.stats import StatsResponse, StatsSummary, MonthlyStats

router = APIRouter(prefix="/stats", tags=["stats"])

@router.get("", response_model=StatsResponse)
def get_stats(
    vehicle_id: Optional[str] = None,
    year: Optional[int] = None,
    engine: Engine = Depends(get_db_engine),
    _: str = Depends(get_current_user),
):
    filters = []
    params = {}
    if vehicle_id:
        filters.append("vehicle_id = :vehicle_id")
        params["vehicle_id"] = vehicle_id
    if year:
        filters.append("YEAR(date) = :year")
        params["year"] = year

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    with engine.connect() as conn:
        summary_row = conn.execute(text(f"""
            SELECT
                COALESCE(SUM(distance), 0)        AS total_distance,
                AVG(fuel_efficiency)               AS avg_fuel_efficiency,
                SUM(consumed_fuel)                 AS total_consumed_fuel,
                COUNT(*)                           AS total_records
            FROM driving_logs {where}
        """), params).mappings().one()

        monthly_rows = conn.execute(text(f"""
            SELECT
                YEAR(date)              AS year,
                MONTH(date)             AS month,
                SUM(distance)           AS total_distance,
                AVG(fuel_efficiency)    AS avg_fuel_efficiency,
                SUM(consumed_fuel)      AS total_consumed_fuel,
                COUNT(*)                AS record_count
            FROM driving_logs {where}
            GROUP BY YEAR(date), MONTH(date)
            ORDER BY year ASC, month ASC
        """), params).mappings().all()

    return {
        "summary": dict(summary_row),
        "monthly": [dict(r) for r in monthly_rows],
    }
```

### 5-10. `api/main.py`

```python
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from api.auth.middleware import IPRateLimitMiddleware
from api.auth.router import router as auth_router
from api.routers.logs import router as logs_router
from api.routers.stats import router as stats_router
from api.dependencies import get_db_engine

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: DB 연결 미리 확인
    engine = get_db_engine()
    with engine.connect():
        pass
    yield
    # shutdown: 커넥션 풀 정리
    engine.dispose()

app = FastAPI(title="KiloStone API", version="1.0.0", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL", "http://localhost:3000")],
    allow_credentials=True,   # 쿠키 전달 허용 (refresh token)
    allow_methods=["*"],
    allow_headers=["*"],
)

# IP 차단 미들웨어
app.add_middleware(IPRateLimitMiddleware)

# 라우터 등록
app.include_router(auth_router)
app.include_router(logs_router)
app.include_router(stats_router)

@app.get("/health")
def health():
    return {"status": "ok"}
```

### 5-11. `api/Dockerfile`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 6. `docker-compose.yml` 변경사항

기존 `services:` 블록 안에 아래 서비스 추가. 기존 `app:`, `db:` 서비스는 수정하지 않음.

```yaml
  api:
    build:
      context: .
      dockerfile: api/Dockerfile
    image: kilostone-api:latest
    container_name: kilostone-api
    restart: unless-stopped
    expose:
      - "8000"
    env_file:
      - .env
    depends_on:
      - db
    networks:
      - proxy-network
      - kilostone-internal
```

---

## 7. Nginx 라우팅 설정 (서버에서 직접 수정)

EC2 서버의 기존 Nginx 설정 파일에 아래 블록 추가.
위치: `/etc/nginx/sites-available/kilostone` 또는 기존 설정 파일 내부.

```nginx
location /api/ {
    proxy_pass         http://kilostone-api:8000/;
    proxy_set_header   Host $host;
    proxy_set_header   X-Real-IP $remote_addr;
    proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header   X-Forwarded-Proto $scheme;
}
```

**주의**: `/api/` → `kilostone-api:8000/` trailing slash 필수. 없으면 경로 중복 발생.

---

## 8. 전체 API 엔드포인트 요약

| Method | Path | 인증 | 설명 |
|--------|------|------|------|
| POST | `/auth/login` | 없음 | 로그인, access_token 반환 + refresh_token 쿠키 설정 |
| POST | `/auth/refresh` | 쿠키 | access_token 재발급 |
| POST | `/auth/logout` | 없음 | refresh_token 쿠키 삭제 |
| GET | `/logs` | Bearer | 기록 목록 (페이지네이션, 필터) |
| POST | `/logs` | Bearer | 기록 추가 (source='manual' 자동 설정) |
| PUT | `/logs/{id}` | Bearer | 기록 수정 (source='manual' 자동 설정) |
| DELETE | `/logs/{id}` | Bearer | 기록 삭제 |
| GET | `/stats` | Bearer | 집계 통계 (전체 요약 + 월별 내역) |
| GET | `/health` | 없음 | 서버 상태 확인 |

---

## 9. 인증 흐름 요약

```
[프론트엔드]                    [FastAPI]
     │                              │
     │─── POST /auth/login ────────►│
     │◄── access_token (15분) ──────│
     │◄── refresh_token 쿠키 (7일) ─│
     │                              │
     │─── GET /logs                 │
     │    Authorization: Bearer ... │
     │◄── 데이터 ───────────────────│
     │                              │
     │  (15분 후 access_token 만료) │
     │─── POST /auth/refresh ──────►│  ← 쿠키 자동 전송
     │◄── 새 access_token ──────────│
```

- access_token: 메모리에만 보관 (localStorage X)
- refresh_token: httpOnly 쿠키 (JS 접근 불가, XSS 방어)
- 쿠키 전달: Next.js fetch 호출 시 `credentials: "include"` 필수

---

## 10. 구현 순서 권고

1. `api/schemas/` 4개 파일 생성
2. `api/dependencies.py` 생성
3. `api/auth/service.py` 생성
4. `api/auth/middleware.py` 생성
5. `api/auth/router.py` 생성
6. `api/routers/logs.py` 생성
7. `api/routers/stats.py` 생성
8. `api/main.py` 생성
9. `api/Dockerfile` 생성
10. `api/__init__.py`, `api/auth/__init__.py`, `api/routers/__init__.py`, `api/schemas/__init__.py` 생성 (빈 파일)
11. `requirements.txt` 4개 패키지 추가
12. `docker-compose.yml` api 서비스 추가
13. `.env` 신규 항목 추가 및 해시값 생성
14. `docker compose up -d --build api` 로 단독 실행 테스트
15. `GET /health` 응답 확인 후 인증 플로우 테스트
