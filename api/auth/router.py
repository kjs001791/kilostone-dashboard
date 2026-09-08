from fastapi import APIRouter, HTTPException, Response, Request, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine
from api.schemas.auth import LoginRequest, TokenResponse
from api.auth.service import authenticate_user, create_access_token, create_refresh_token, decode_refresh_token, get_active_user
from api.dependencies import get_db_engine
import os

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
REFRESH_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, response: Response, engine: Engine = Depends(get_db_engine)):
    user = authenticate_user(body.username, body.password, engine)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="아이디 또는 비밀번호가 틀렸습니다.")

    access_token = create_access_token(user["username"], user["role"], user["id"])
    refresh_token = create_refresh_token(user["username"])

    response.set_cookie(
        key=REFRESH_COOKIE,
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24 * REFRESH_EXPIRE_DAYS,
    )
    return {"access_token": access_token, "token_type": "bearer", "role": user["role"]}


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, engine: Engine = Depends(get_db_engine)):
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="refresh_token 쿠키가 없습니다.")

    username = decode_refresh_token(token)
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않거나 만료된 refresh token입니다.")

    user = get_active_user(username, engine)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="사용자를 찾을 수 없습니다.")

    return {"access_token": create_access_token(username, user["role"], user["id"]), "token_type": "bearer", "role": user["role"]}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key=REFRESH_COOKIE, httponly=True, secure=True, samesite="lax")
    return {"message": "로그아웃 되었습니다."}
