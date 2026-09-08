from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from api.auth.service import hash_password
from api.dependencies import get_db_engine, require_admin, CurrentUser
from api.schemas.user import UserCreate, UserUpdate, UserResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserResponse])
def list_users(
    engine: Engine = Depends(get_db_engine),
    _: CurrentUser = Depends(require_admin),
):
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, username, role, is_active, created_at FROM users ORDER BY created_at")
        ).mappings().all()
    return [dict(r) for r in rows]


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreate,
    engine: Engine = Depends(get_db_engine),
    _: CurrentUser = Depends(require_admin),
):
    hashed = hash_password(body.password)
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("INSERT INTO users (username, password_hash, role) VALUES (:u, :h, :r)"),
                {"u": body.username, "h": hashed, "r": body.role},
            )
            conn.commit()
            new_id = result.lastrowid
            row = conn.execute(
                text("SELECT id, username, role, is_active, created_at FROM users WHERE id = :id"),
                {"id": new_id},
            ).mappings().one()
    except IntegrityError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 존재하는 아이디입니다.")
    return dict(row)


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    body: UserUpdate,
    engine: Engine = Depends(get_db_engine),
    current_user: CurrentUser = Depends(require_admin),
):
    updates: dict = {}
    if body.password is not None:
        updates["password_hash"] = hash_password(body.password)
    if body.role is not None:
        updates["role"] = body.role
    if body.is_active is not None:
        updates["is_active"] = body.is_active

    if not updates:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="변경할 항목이 없습니다.")

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["id"] = user_id

    with engine.connect() as conn:
        result = conn.execute(text(f"UPDATE users SET {set_clause} WHERE id = :id"), updates)
        conn.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다.")
        row = conn.execute(
            text("SELECT id, username, role, is_active, created_at FROM users WHERE id = :id"),
            {"id": user_id},
        ).mappings().one()
    return dict(row)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    engine: Engine = Depends(get_db_engine),
    current_user: CurrentUser = Depends(require_admin),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="자기 자신은 삭제할 수 없습니다.")
    with engine.connect() as conn:
        result = conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
        conn.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다.")
    return None
