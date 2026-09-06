"""
Endpoints for registering and listing devices.

Prefix "/devices" means every endpoint in this file automatically lives
under that path -- so @router.post("") below actually becomes POST /devices,
not POST /.
"""

from uuid import uuid4

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device
from app.schemas import DeviceCreate, DeviceResponse

router = APIRouter(
    prefix="/devices",
    tags=["devices"],   # groups these endpoints together in Swagger's UI
)

@router.post(
    "",
    response_model=DeviceResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_device(
    device_data: DeviceCreate,
    db: Session = Depends(get_db)   # Depends(get_db) runs get_db() from
                                       # database.py and hands us a fresh
                                       # session for this one request
) -> Device:
    device = Device(
        id=str(uuid4()),
        name=device_data.name,
    )

    db.add(device)      # stage the new row (not saved yet)
    db.commit()          # actually write it to the database
    db.refresh(device)   # re-read the row back from the DB, so `device`
                          # now has server-generated fields filled in
                          # (created_at, last_seen_at) that we didn't
                          # set manually

    return device

@router.get(
    "",
    response_model=list[DeviceResponse],
)
def list_devices(db: Session = Depends(get_db),) -> list[Device]:
    # select(Device) builds a "SELECT * FROM devices" query using
    # SQLAlchemy's ORM instead of writing raw SQL by hand -- this is
    # what protects us from SQL injection automatically.
    statement = select(Device).order_by(Device.created_at, Device.id)

    # db.scalars(...) runs the query and gives us Device objects
    # directly (rather than raw row tuples). .all() collects every
    # result into a list.
    devices = list(db.scalars(statement).all())

    return devices
