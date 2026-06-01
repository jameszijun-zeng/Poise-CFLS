from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from poise.core.database import get_db
from poise.core.rbac import CurrentUser, get_current_user
from poise.domain.models import User
from poise.domain.schemas import UserOut

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=UserOut)
def get_me(
    current: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    user = db.get(User, current.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return user
