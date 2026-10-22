"""FastAPI application: API routes plus the static web app, in one process."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import documents, settings, tts
from .config import APP_NAME, APP_VERSION, Config
from .db import Database
from .extract import extract_markdown
from .state import AppState
from .tts import AudioCache, ModelManager, SynthService
from .welcome import WELCOME_MARKDOWN, WELCOME_TITLE

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
log = logging.getLogger("aloud")


def seed_welcome(state: AppState) -> None:
    if state.db.count_documents() == 0:
        state.store_document(extract_markdown(WELCOME_MARKDOWN), "bundled", None, WELCOME_TITLE)


def build_state(config: Config) -> AppState:
    config.ensure_dirs()
    db = Database(config.db_path)
    manager = ModelManager(config)
    cache = AudioCache(config.cache_dir, config.cache_max_bytes)
    synth = SynthService(config, manager, cache)
    return AppState(config=config, db=db, manager=manager, cache=cache, synth=synth)


def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config.from_env()
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        state = build_state(config)
        app.state.aloud = state
        seed_welcome(state)
        if config.auto_download:
            state.manager.start()
        log.info("%s %s ready, data in %s", APP_NAME, APP_VERSION, config.data_dir)
        try:
            yield
        finally:
            state.synth.close()
            state.db.close()

    app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan, docs_url="/api/docs")
    app.include_router(documents.router)
    app.include_router(tts.router)
    app.include_router(settings.router)

    @app.get("/api/health")
    def health(request: Request) -> dict[str, object]:
        state: AppState = request.app.state.aloud
        return {
            "ok": True,
            "name": APP_NAME,
            "version": APP_VERSION,
            "tts": state.manager.status.state,
        }

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, error: HTTPException) -> JSONResponse:
        return JSONResponse({"detail": error.detail}, status_code=error.status_code)

    @app.middleware("http")
    async def revalidate_static(request: Request, call_next):
        # Everything is served from localhost, so always revalidating (ETag) is cheap and
        # means an upgrade never leaves a browser running yesterday's scripts.
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    if WEB_DIR.exists():
        app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

        @app.get("/", include_in_schema=False)
        @app.get("/doc/{document_id}", include_in_schema=False)
        def index(document_id: str | None = None) -> FileResponse:
            return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})

        @app.get("/manifest.webmanifest", include_in_schema=False)
        def manifest() -> FileResponse:
            return FileResponse(
                WEB_DIR / "manifest.webmanifest", media_type="application/manifest+json"
            )

    return app


app = create_app()
