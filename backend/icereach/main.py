"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings
from .db import Base, engine

# Importing models populates Base.metadata for create_all / Alembic autogenerate.
from . import models  # noqa: F401

# CSRF is enforced for state-changing requests authenticated by the session cookie.
# Exempt: login/signup (no session yet) and any request bearing an API key.
_CSRF_EXEMPT_PATHS = {"/api/auth/login", "/api/auth/signup"}
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method
        needs_check = (
            method not in _SAFE_METHODS
            and path.startswith("/api/")
            and path not in _CSRF_EXEMPT_PATHS
            and not request.headers.get("Authorization", "").lower().startswith("bearer ")
        )
        if needs_check:
            from .security.sessions import verify_csrf
            cookie = request.cookies.get(settings.csrf_cookie, "")
            header = request.headers.get("X-CSRF-Token", "")
            if not cookie or not header or cookie != header or not verify_csrf(header):
                return JSONResponse(status_code=403, content={"detail": "CSRF validation failed"})
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Dev convenience: ensure schema exists. Production uses Alembic migrations.
    Base.metadata.create_all(engine)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="iceReach", version="0.2.0", lifespan=lifespan)

    app.add_middleware(CSRFMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from .routers import api_keys, auth
    app.include_router(auth.router)
    app.include_router(api_keys.router)

    # Routers added as their work-streams land:
    for module_name in ("contacts", "lists", "segments", "sending_domains",
                        "campaigns", "analytics", "ai", "public", "jobs"):
        try:
            mod = __import__(f"icereach.routers.{module_name}", fromlist=["router"])
            app.include_router(mod.router)
        except ModuleNotFoundError:
            pass

    @app.get("/health", tags=["meta"])
    def health():
        return {"status": "ok", "service": "iceReach", "version": app.version}

    return app


app = create_app()
