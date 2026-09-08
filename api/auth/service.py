import os
import bcrypt
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from sqlalchemy import text
from sqlalchemy.engine import Engine


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def get_active_user(username: str, engine: Engine) -> Optional[dict]:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, username, role FROM users WHERE username = :u AND is_active = TRUE"),
            {"u": username}
        ).mappings().one_or_none()
    return dict(row) if row else None


def authenticate_user(username: str, password: str, engine: Engine) -> Optional[dict]:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, username, password_hash, role, is_active FROM users WHERE username = :u"),
            {"u": username}
        ).mappings().one_or_none()

    if row is None or not row["is_active"]:
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    return {"id": row["id"], "username": row["username"], "role": row["role"]}


def create_access_token(username: str, role: str, user_id: int) -> str:
    expire_minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
    expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    payload = {"sub": username, "role": role, "id": user_id, "exp": expire, "type": "access"}
    return jwt.encode(payload, os.getenv("JWT_SECRET_KEY"), algorithm="HS256")


def create_refresh_token(username: str) -> str:
    expire_days = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    expire = datetime.now(timezone.utc) + timedelta(days=expire_days)
    payload = {"sub": username, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, os.getenv("JWT_SECRET_KEY"), algorithm="HS256")


def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET_KEY"), algorithms=["HS256"])
        if payload.get("type") != "access":
            return None
        return {"username": payload.get("sub"), "role": payload.get("role", "driver"), "id": payload.get("id")}
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
