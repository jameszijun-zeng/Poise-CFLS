from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from poise.core.config import get_settings
from poise.core.database import get_db
from poise.core.security import create_access_token, verify_password
from poise.domain.models import User
from poise.domain.schemas import TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    user = db.scalar(select(User).where(User.username == form.username))
    if not user or not user.is_active or not verify_password(form.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    settings = get_settings()
    token = create_access_token(
        subject=user.id,
        role=user.role,
        extra={"entity_id": user.entity_id, "username": user.username},
    )
    return TokenResponse(
        access_token=token,
        expires_in_minutes=settings.api_jwt_expire_minutes,
    )
