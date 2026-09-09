"""
Handles physically saving uploaded file bytes to disk, safely.

Storage layout on disk:
  backend/storage/tmp/      <- incoming uploads land here first
  backend/storage/objects/  <- verified files live here permanently,
                                named by their own hash (content-addressed)
"""
import shutil
from pathlib import Path
from uuid import uuid4

from app.config import STORAGE_DIR

TMP_DIR = STORAGE_DIR / "tmp"
OBJECTS_DIR = STORAGE_DIR / "objects"

TMP_DIR.mkdir(parents=True, exist_ok=True)
OBJECTS_DIR.mkdir(parents=True, exist_ok=True)

def new_temp_path() -> Path:
    """
    Generates a fresh, unique location inside storage/tmp/ for one
    incoming upload to be written to.

    A UUID guarantees no collision,
    regardless of what the clients happen to be uploading.
    """
    return TMP_DIR / f"upload_{uuid4}.tmp"

def save_upload_to_temp(file_obj, destination: Path):
    """
    Streams an incoming upload's bytes to a temporary file on disk.

    We stream in chunks here because a large upload 
    shouldn't require holding the entire file in memory at once.
    """
    CHUNK_SIZE = 1024 * 1024 # 1 MB

    # "wb" = write, binary mode. Binary because
    #  we're saving raw bytes exactly as
    # received, not text that's been decoded/re-encoded.
    with open(destination, "wb") as out_file:
        while True:
            chunk = file_obj.read(CHUNK_SIZE)
            if not chunk:
                break
            out_file.write(chunk)

def object_path_for_hash(file_hash: str) -> Path:
    """
    Given a file's hash, returns where it SHOULD live permanently in
    storage/objects/

    This is the "content-addressed" naming scheme: the hash itself
    becomes the filename. Two files with identical content will
    always compute to this same path, which is exactly what gives us
    free deduplication.
    """
    return OBJECTS_DIR / file_hash

def commit_temp_file(temp_path: Path, file_hash: str) -> Path:
    """
    Moves a verified temp file into its permanent home in
    storage/objects/, named by its hash.

    Only call this AFTER verify_file_hash() (from hashing.py) has
    confirmed the temp file's actual content matches the claimed hash --
    this function doesn't re-check anything itself, it just performs
    the action.

    Returns the final permanent path (this is what gets saved into
    FileVersion.storage_path).
    """
    final_path = object_path_for_hash(file_hash)

    # Deduplication in action: if a file with this exact hash already
    # exists in permanent storage (from some earlier upload -- possibly
    # a completely different FileVersion row, possibly even a
    # different sync space), we don't need to save it again. 
    if final_path.exists():
        temp_path.unlink() # deletes the non redundant temp file
        return final_path

    # shutil.move() is used instead of Path.rename() because rename()
    # can fail if tmp/ and objects/ are on different physical
    # drives/filesystems. shutil.move() safely falls
    # back to a copy+delete in that situation instead of just crashing.
    shutil.move(temp_path, final_path)
    return final_path

def discard_temp_file(temp_path: Path) -> None:
    """
    Deletes a temp file that failed verification (hash mismatch) or
    otherwise shouldn't be kept.

    missing_ok=True: don't crash if the file's somehow already gone.
    """
    temp_path.unlink(missing_ok=True)