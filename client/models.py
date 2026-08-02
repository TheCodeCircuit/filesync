"""
Core data models for the FileSync client.

These dataclasses are frozen (immutable) by design: state transitions are
expressed by constructing a new instance (dataclasses.replace), never by
mutating an existing one. That's what makes state changes traceable once
these objects start flowing through scanner -> change_detector ->
sync_planner -> api_client -> local_db.
"""

from dataclasses import dataclass
from enum import Enum, auto
from datetime import datetime


class SyncStatus(str, Enum):
    """Mirrors local_files.sync_status in DATABASE_SCHEMA.md exactly.
    The str mixin means the enum's value IS the string SQLite stores,
    so there's no manual str(...) <-> Enum(...) translation layer
    needed at the local_db.py boundary, and comparisons like
    `record.sync_status == "synced"` just work."""
    SYNCED = "synced"
    DIRTY = "dirty"
    PENDING = "pending"
    CONFLICT = "conflict"
    DELETED = "deleted"


class SyncAction(Enum):
    """Output of sync_planner: what should happen to one file.
    This is a decision, not a stored row -- no str mixin needed."""
    NO_ACTION = auto()
    UPLOAD = auto()
    DOWNLOAD = auto()
    CONFLICT = auto()
    UPLOAD_TOMBSTONE = auto()
    APPLY_REMOTE_DELETE = auto()  # symmetric with UPLOAD_TOMBSTONE


class ChangeType(Enum):
    ADDED = auto()
    DELETED = auto()
    MODIFIED = auto()
    UNCHANGED = auto()


class DecisionRow(Enum):
    NO_CHANGE = auto()
    LOCAL_CHANGE = auto()
    REMOTE_CHANGE = auto()
    LOCAL_DELETE = auto()
    REMOTE_DELETE = auto()
    BOTH_MODIFIED = auto()
    DELETE_MODIFY_CONFLICT = auto()


class TransferStatus(str, Enum):
    """Mirrors pending_transfers.status.
    OPEN QUESTION: DATABASE_SCHEMA.md documents this column's values as
    pending/running/failed/done, which don't line up 1:1 with the names
    below, and RETRYING has no dedicated column counterpart there (the
    schema tracks retries via retry_count on a pending/failed row).
    Left as-is for now since it's not blocking models.py/config.py --
    reconcile this before local_db.py or transfer_queue.py."""
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class TransferDirection(str, Enum):
    """Mirrors pending_transfers.direction."""
    UPLOAD = "upload"
    DOWNLOAD = "download"


@dataclass(frozen=True)
class UserConfig:
    sync_folder: str | None
    server_url: str | None


@dataclass(frozen=True)
class ServerIdentity:
    device_id: str | None
    sync_space_id: str | None
    access_token: str | None
    refresh_token: str | None


@dataclass(frozen=True)
class ClientConfig:
    user: UserConfig
    identity: ServerIdentity


@dataclass(frozen=True)
class ScanResult:
    relative_path: str
    size_bytes: int
    modified_time: float
    inode: int | None


@dataclass(frozen=True)
class LocalFileState:
    scan: ScanResult
    file_hash: str

    @property
    def relative_path(self) -> str:
        """Thin passthrough so callers don't need to know LocalFileState
        wraps a ScanResult just to read the path."""
        return self.scan.relative_path


@dataclass(frozen=True)
class RemoteFileState:
    relative_path: str
    version_id: str
    file_hash: str
    size_bytes: int
    deleted: bool
    updated_at: datetime


@dataclass(frozen=True)
class SyncRecord:
    relative_path: str
    file_hash: str
    size_bytes: int
    modified_time: float
    server_version_id: str | None
    sync_status: SyncStatus
    deleted: bool
    last_scanned_at: datetime
    last_synced_at: datetime | None  # None until the file has synced once


@dataclass(frozen=True)
class Change:
    relative_path: str
    change_type: ChangeType
    old_metadata: SyncRecord | None       # last known state, from local_db
    new_metadata: LocalFileState | None   # freshly scanned + hashed state


@dataclass(frozen=True)
class ChangeSet:
    added: list[Change]
    deleted: list[Change]
    modified: list[Change]
    unchanged: list[Change]

    def iter_changed(self):
        change_list = self.added + self.deleted + self.modified
        return change_list


@dataclass(frozen=True)
class Operation:
    action: SyncAction
    relative_path: str
    local_state: LocalFileState | None
    remote_state: RemoteFileState | None
    base_version_id: str | None
    decision_row: DecisionRow


@dataclass(frozen=True)
class Plan:
    operations: list[Operation]
