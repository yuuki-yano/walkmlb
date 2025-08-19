from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from .routers import importer, games, steps
from .routers import admin
from .routers import calendar as calendar_router
import asyncio
from .updater import run_scheduler
from .db import init_db
from .config import settings

root_path = settings.base_path.rstrip("/") if settings.base_path else ""
app = FastAPI(title="WalkMLB", root_path=root_path)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_prefix = (root_path + "/api") if root_path else "/api"
# Routers first (prefixは常に /api。root_path はASGI側で前置パスを扱う)
api_prefix = "/api"
app.include_router(importer.router, prefix=api_prefix, tags=["import"])
app.include_router(games.router, prefix=api_prefix, tags=["games"])
app.include_router(steps.router, prefix=api_prefix, tags=["steps"])
app.include_router(admin.router, prefix=api_prefix, tags=["admin"])
app.include_router(calendar_router.router, prefix=api_prefix, tags=["calendar"])

# Static frontend mounted at base path
# Static frontend mounted at app root (root_pathが外側のサブパスを表現)
app.mount("/", StaticFiles(directory="static", html=True), name="static")

@app.on_event("startup")
def on_startup():
    init_db()
    # Launch background updater
    loop = asyncio.get_event_loop()
    loop.create_task(run_scheduler())
