from dataclasses import dataclass
from enum import Enum,auto
from datetime import datetime

class SyncStatus(Enum):
    SYNCED = auto()
    DIRTY = auto()
    PENDING = auto()
    CONFLICT = auto()
    DELETED = auto()

class SyncAction(Enum):
    NO_ACTION = auto()
    UPLOAD = auto()
    DOWNLOAD = auto()
    CONFLICT = auto()
    UPLOAD_TOMBSTONE = auto()

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

class TransferStatus(Enum):
    QUEUED = auto()
    IN_PROGRESS = auto()
    COMPLETED = auto()
    FAILED = auto()
    RETRYING = auto()

class TransferDirection(Enum):
    UPLOAD = auto()
    DOWNLOAD = auto()

@dataclass (frozen=True)
class ScanResult:
    relative_path: str
    size_bytes: int
    modified_time: float
    inode: int | None

@dataclass (frozen=True)
class LocalFileState:
    scan: ScanResult
    file_hash : str

@dataclass (frozen=True)
class RemoteFileState:
    relative_path: str
    version_id: str
    file_hash: str
    size_bytes: int
    deleted: bool
    updated_at: datetime

@dataclass (frozen=True)
class SyncRecord:
    relative_path: str
    file_hash: str
    size_bytes: int
    modified_time: float
    server_version_id: str | None
    sync_status: SyncStatus
    deleted: bool
    last_scanned_at: datetime
    last_synced_at: datetime

@dataclass (frozen=True)
class Change:
    relative_path: str
    change_type: ChangeType
    old_metadata: ScanResult | None
    new_metadata: ScanResult | None

@dataclass (frozen=True)
class ChangeSet:
    added: list[Change]
    deleted: list[Change]
    modified: list[Change]
    unchanged: list[Change]
    
    def iter_changed(self):
        change_list = self.added + self.deleted + self.modified
        return change_list

@dataclass (frozen=True)
class Operation:
    action: SyncAction
    relative_path: str
    local_state: LocalFileState | None
    remote_state: RemoteFileState | None
    base_version_id: str | None 
    decision_row: DecisionRow

@dataclass (frozen=True)
class Plan:
    operations : list[Operation]
