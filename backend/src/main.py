"""lychee backend — FastAPI application entrypoint."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.bootstrap import bootstrap
from src.catalog.router import router as catalog_router
from src.collections.router import router as collections_router
from src.core.config import settings
from src.core.exceptions import LycheeError
from src.core.logging import configure_logging, get_logger
from src.downloads.provider import register_provider
from src.downloads.router import router as downloads_router
from src.health.router import router as health_router
from src.integrations.router import router as integrations_router
from src.library.router import router as library_router
from src.progress.router import router as progress_router
from src.tasks.events import broker
from src.tasks.queue import queue
from src.tasks.router import router as tasks_router
from src.taxonomy.router import router as taxonomy_router

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    logger.info("application_startup", environment=settings.environment)
    if settings.auto_bootstrap:
        bootstrap()
    from src.providers.mangadex import MangaDexProvider
    from src.trackers.anilist import AniListTracker
    from src.trackers.base import register_tracker
    from src.trackers.mangaupdates import MangaUpdatesTracker
    from src.trackers.myanimelist import MyAnimeListTracker

    register_provider(MangaDexProvider())
    register_tracker(AniListTracker())
    register_tracker(MyAnimeListTracker())
    register_tracker(MangaUpdatesTracker())
    broker.bind_loop(asyncio.get_running_loop())
    yield
    queue.shutdown()
    logger.info("application_shutdown")


app = FastAPI(
    title="lychee",
    description="Self-hosted manga/comic/ebook media server",
    version="0.0.1",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Every error response has the shape ``{"error": {"code": <slug>, "message": <text>}}``.
_HTTP_ERROR_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
}


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content={"error": {"code": code, "message": message}}
    )


@app.exception_handler(LycheeError)
async def _domain_exception_handler(_request: Request, exc: LycheeError) -> JSONResponse:
    """Translate domain exceptions to their HTTP status (services stay HTTP-agnostic)."""
    return _error_response(exc.status_code, exc.code, exc.message)


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Pydantic request-validation failures → the standard error shape."""
    errors = exc.errors()
    message = "invalid request"
    if errors:
        loc = ".".join(str(part) for part in errors[0].get("loc", ()) if part != "body")
        detail = errors[0].get("msg", "invalid value")
        message = f"{loc}: {detail}" if loc else detail
    return _error_response(422, "validation_error", message)


@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Framework HTTP errors (unknown route, wrong method, …) → the standard error shape."""
    code = _HTTP_ERROR_CODES.get(exc.status_code, "error")
    return _error_response(exc.status_code, code, str(exc.detail))


app.include_router(health_router)
app.include_router(catalog_router)
app.include_router(library_router)
app.include_router(progress_router)
app.include_router(integrations_router)
app.include_router(taxonomy_router)
app.include_router(collections_router)
app.include_router(tasks_router)
app.include_router(downloads_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "lychee", "version": app.version, "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.main:app", host=settings.api_host, port=settings.api_port, reload=True)
