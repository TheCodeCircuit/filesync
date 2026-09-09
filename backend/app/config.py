"""
Central place for filesystem paths the backend needs.

Why this file exists at all: hardcoding paths like "storage/filesync.db"
directly inside database.py would make it painful to change later (e.g.
when we eventually need a different path for tests). Keeping paths here
means every other file just imports the finished path instead of
building it themselves.
"""

from pathlib import Path

# Path(__file__) = the path to THIS file (config.py) itself.
# .resolve() = convert it to a full, unambiguous absolute path
# .parent = go up one folder (out of app/)
# .parent again = go up one more folder (out of backend/)
BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
DATABASE_PATH = STORAGE_DIR / "filesync.db"

# SQLAlchemy needs the database location as a special connection string,
# not just a plain file path. "sqlite:///" is the required prefix for
# SQLite specifically (other databases like Postgres use a different prefix).
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"