from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import os
from fastapi.middleware.cors import CORSMiddleware
from .routers import importer, games, steps
from .routers import auth
from .routers import admin
from .routers import calendar as calendar_router
import asyncio
from .updater import run_scheduler
from .db import init_db, SessionLocal, User
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
app.include_router(auth.router, prefix=api_prefix, tags=["auth"])
app.include_router(admin.router, prefix=api_prefix, tags=["admin"])
app.include_router(calendar_router.router, prefix=api_prefix, tags=["calendar"])

"""
Static frontend
- If React+Vite build exists at web/dist, serve it at '/'
- Fallback to existing 'static' folder otherwise
"""
if os.path.isdir("web/dist"):
    app.mount("/", StaticFiles(directory="web/dist", html=True), name="spa")
else:
    app.mount("/", StaticFiles(directory="static", html=True), name="static")

@app.on_event("startup")
def on_startup():
    init_db()
    # Launch background updater
    loop = asyncio.get_event_loop()
    loop.create_task(run_scheduler())
    # Optional admin bootstrap
    if settings.admin_bootstrap_email and settings.admin_bootstrap_password:
        db = SessionLocal()
        try:
            exists = db.query(User).filter(User.email == settings.admin_bootstrap_email.lower()).one_or_none()
            if not exists and db.query(User).count() == 0:
                # defer import to avoid circular
                from .routers.auth import hash_password
                admin = User(email=settings.admin_bootstrap_email.lower(), password_hash=hash_password(settings.admin_bootstrap_password), role="admin")
                db.add(admin)
                db.commit()
        finally:
            db.close()
