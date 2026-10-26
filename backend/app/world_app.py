"""Standalone A2 fixture service: uvicorn app.world_app:create_world_app --factory.

Each process has its own in-memory worlds; restarting discards them. Use one
worker. This factory avoids campaign initialization, databases and model APIs.
"""
import os
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.worlds import router
from app.services.world.control import WorldService
from app.services.world.store import FixtureBaselineStore


def install_world_routes(app, store=None):
    app.state.world_service = WorldService(
        store if store is not None else FixtureBaselineStore(
            clock=lambda: int(time.time() * 1000)))
    app.include_router(router)


def create_world_app(*, store=None, allowed_origins=None):
    app = FastAPI(title='Jity World Fixture API', version='2')
    if allowed_origins is None:
        allowed_origins = [origin.strip() for origin in os.environ.get(
            'WORLD_ALLOWED_ORIGINS',
            'http://localhost:3000,http://127.0.0.1:3000,'
            'http://localhost:3001,http://127.0.0.1:3001,'
            'http://localhost:3100,http://127.0.0.1:3100').split(',') if origin.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=list(allowed_origins),
                       allow_credentials=True, allow_methods=['*'], allow_headers=['*'])
    install_world_routes(app, store)
    return app


def create_persistent_world_app():
    """Opt-in SQLite service with transactional A3 authority and recovery.

    WORLD_SQLITE_PATH is required so startup cannot silently use memory or
    create a database in an unexpected working directory.
    """
    from app.database.world_store import SQLiteBaselineStore

    path = os.environ.get('WORLD_SQLITE_PATH')
    if not path:
        raise RuntimeError('WORLD_SQLITE_PATH is required for the persistent world app')
    app = create_world_app(store=SQLiteBaselineStore(path))
    app.title = 'Jity World Persistent Development API'
    return app
