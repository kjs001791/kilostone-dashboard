import json
import os
from datetime import datetime
from pathlib import Path
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Path relative to api/auth/middleware.py -> ../../data
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
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
        # Apply only to login endpoint
        # Use endswith or contains to be safer against trailing slashes or full URLs
        if LOGIN_PATH not in request.url.path:
            return await call_next(request)

        ip = _get_ip(request)

        if is_blocked(ip):
            return JSONResponse(
                status_code=403,
                content={"detail": f"IP {ip}가 차단되었습니다. 관리자에게 문의하세요."}
            )

        response = await call_next(request)

        # Increase attempt count on 401 Unauthorized
        if response.status_code == 401:
            count = increment_attempts(ip)
            if count >= MAX_ATTEMPTS:
                block_ip(ip)
        elif response.status_code == 200:
            reset_attempts(ip)

        return response
