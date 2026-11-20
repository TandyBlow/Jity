"""Run the progress store as its own service, without the world API.

    cd backend
    uvicorn app.services.local_progress.standalone:app --port 8010

Environment:
    LOCAL_PROGRESS_DB                  default data/local_progress.sqlite3
    LOCAL_PROGRESS_TOKEN              optional bearer token
    LOCAL_PROGRESS_CORS_ORIGINS       comma-separated browser origins
    LOCAL_PROGRESS_MAX_PAYLOAD_BYTES  default 4194304
    LOCAL_PROGRESS_MAX_SNAPSHOTS      default 5000 per world
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.local_progress import router
from app.services.local_progress.settings import cors_origins


def create_app() -> FastAPI:
    app = FastAPI(title="Jity local progress sync", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
