"""
Endpoints for creating and listing sync spaces.
"""

from uuid import uuid4

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import SyncSpace
from app.schemas import SyncSpaceCreate, SyncSpaceResponse

router = APIRouter(
    prefix="/sync-spaces",
    tags=["sync spaces"],
)

@router.post(
    "",
    response_model=SyncSpaceResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_sync_space(
    sync_space_data: SyncSpaceCreate,
    db: Session = Depends(get_db),
) -> SyncSpace:
    sync_space = SyncSpace(
        id=str(uuid4()),
        name=sync_space_data.name,
    )

    db.add(sync_space)
    db.commit()
    db.refresh(sync_space)

    return sync_space

@router.get(
    "",
    response_model=list[SyncSpaceResponse]
)
def list_sync_spaces(db: Session = Depends(get_db)) -> list[SyncSpace]:
    statement = select(SyncSpace).order_by(SyncSpace.created_at, SyncSpace.id)
    sync_spaces = list(db.scalars(statement).all())

    return sync_spaces
