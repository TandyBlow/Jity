"""Jity RPG Scenario Generator API."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import backgrounds, campaigns, generate, meta, sessions, slots

settings = get_settings()

app = FastAPI(title="Jity RPG Scenario Generator API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://127.0.0.1:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Slots must be included before campaigns so /campaigns/slots
# doesn't get eaten by the /campaigns/{filename} catch-all.
app.include_router(slots.router)
app.include_router(campaigns.router)
app.include_router(sessions.router)
app.include_router(generate.router)
app.include_router(backgrounds.router)
app.include_router(meta.router)

settings.backgrounds_dir.mkdir(parents=True, exist_ok=True)
app.mount(
    "/background-assets",
    StaticFiles(directory=settings.backgrounds_dir),
    name="background-assets",
)
