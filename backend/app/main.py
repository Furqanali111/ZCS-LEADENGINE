import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from starlette.exceptions import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import dashboard, exports, health, leads, pipeline, search, sources
from app.config import get_settings
from app.errors import AppError

logger = logging.getLogger(__name__)

CODES = {400: "bad_request", 404: "not_found", 405: "method_not_allowed", 409: "conflict", 422: "validation_error"}


def _error(status: int, message: str, code: str | None = None) -> JSONResponse:
    code = code or CODES.get(status, "http_error" if status < 500 else "server_error")
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def create_app(testing: bool = False) -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if not testing:
            from app.db import SessionLocal
            from app.worker import pause_running_jobs, start_worker

            with SessionLocal() as session:
                pause_running_jobs(session)
            start_worker(SessionLocal)
        yield

    app = FastAPI(title="ZCS LeadEngine", lifespan=lifespan)
    app.state.testing = testing
    app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin], allow_methods=["*"], allow_headers=["*"], expose_headers=["Content-Disposition"])

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException):
        return _error(exc.status_code, str(exc.detail))

    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError):
        return _error(exc.status, exc.message, exc.code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        msg = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        return _error(422, msg)

    @app.exception_handler(Exception)
    async def unhandled_error(_: Request, exc: Exception):
        logger.exception("unhandled error: %s", type(exc).__name__)
        return _error(500, "Internal server error")

    app.include_router(health.router)
    app.include_router(sources.router)
    app.include_router(search.router)
    app.include_router(leads.router)
    app.include_router(exports.router)
    app.include_router(pipeline.router)
    app.include_router(dashboard.router)
    return app
