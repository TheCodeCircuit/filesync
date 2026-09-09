"""
The entry point of the whole backend server.

Running `uvicorn app.main:app` starts everything defined here: it
builds the FastAPI application, wires up our routers (groups of related
endpoints), and sets up code that should run once at startup/shutdown.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import Base, engine
from app import models
from app.routers.devices import router as device_router
from app.routers.sync_spaces import router as sync_space_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    @asynccontextmanager + a function containing exactly one `yield`
    is Python's way of writing "run setup code, then (later) run
    teardown code" as a single readable block, instead of two separate
    functions.

    Everything BEFORE yield  -> runs once, when the server starts.
    Everything AFTER  yield  -> runs once, when the server shuts down.

    On startup: create any database tables that don't exist yet.
    On shutdown: nothing needed yet, just log that we're stopping.
    """
    print("Server startup...")

    # create_all() looks at every class that inherits from Base and runs
    # "CREATE TABLE IF NOT EXISTS ..." for each one.
    Base.metadata.create_all(bind=engine)
    yield
    print("Server shutdown...")

"""@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)"""
# on_event Deprecated, hence using Lifespan parameter

app = FastAPI(title="Filesync Backend",
            lifespan=lifespan)

app.include_router(device_router)
app.include_router(sync_space_router)

@app.get("/health", tags=["health check"])
def health_check():
    return {"status":"ok"}
