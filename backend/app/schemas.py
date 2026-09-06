"""
Defines the shape of data going OVER THE NETWORK (request bodies and
JSON responses) -- as opposed to models.py, which defines the shape of
data INSIDE the database.

Naming convention used everywhere in this file:
  - "...Create" classes = what the CLIENT sends us when creating something
  - "...Response" classes = what WE send back to the client.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

class DeviceCreate(BaseModel):
    """
    What a client must send us in the body of POST /devices.
    Matches API_CONTRACT.md's example: {"name": "Laptop"}
    """

    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """
        Runs automatically whenever a DeviceCreate is built (i.e. every
        time a request comes in). Strips surrounding whitespace and
        rejects a name that's nothing but whitespace.
        """
        cleaned_name = value.strip()

        if not cleaned_name:
            raise ValueError("Device name can not be empty.")

        return cleaned_name

class DeviceResponse(BaseModel):
    """
    What we send BACK to the client after registering (or listing) a
    device. This has to match API_CONTRACT.md's documented response
    shape exactly.
    """

    # from_attributes=True tells Pydantic: "it's okay to build this
    # response object by reading ATTRIBUTES off a SQLAlchemy Device
    # object (device.id, device.name, ...), not just from a plain dict."
    # Without this, passing a Device object into DeviceResponse would fail.
    model_config = ConfigDict(from_attributes=True)

    # validation_alias="id" tells Pydantic: "the database column is called 'id',
    # but call it 'device_id' in our Python code and JSON responses."
    # This keeps the API contract (device_id in JSON) while respecting the DB schema (id column).
    device_id: str = Field(validation_alias="id")
    name: str
    created_at: datetime
    last_seen_at: datetime

class SyncSpaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        cleaned_name = value.strip()

        if not cleaned_name:
            raise ValueError("Sync Space name can not be empty.")
        
        return cleaned_name

class SyncSpaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sync_space_id: str = Field(validation_alias="id")
    name: str
    created_at: datetime
