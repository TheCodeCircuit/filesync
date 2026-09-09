"""
Sets up the actual connection to our SQLite database.

FastAPI handles many requests. Each request that needs to
touch the database should get its OWN safe connection ("session"), use
it, then give it back. This file provides that
consistently everywhere in the app, instead of every router file
reinventing database-connection logic.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import STORAGE_DIR, DATABASE_URL

STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# connect_args={"check_same_thread": False} is SQLite-specific:
# by default, SQLite refuses to let a connection be used by more than
# one thread. FastAPI can run request-handling code across multiple
# threads, so without this flag we'd get random "wrong thread" errors.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

# autoflush=False, autocommit=False: we want FULL manual control over
# when data actually gets written to the database (via explicit
# db.commit() calls in our routers).
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)

class Base(DeclarativeBase):
    pass

def get_db():
    """
    Here's the flow for one request:
      1. FastAPI calls get_db()
      2. We create a new session
      3. `yield db` PAUSES this function and hands `db` to the endpoint
      4. The endpoint runs, using `db` to read/write data
      5. When the endpoint finishes (success OR error), execution comes
         back here, after the yield
      6. `finally: db.close()` always runs, guaranteeing the connection
         is released even if the endpoint crashed
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

""" SQLite by default doesn't handle multiple people writing 
at the same time very gracefully. There's a simple one-line fix 
(turning on something called "WAL mode") """