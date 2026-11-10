import logging

from fastapi import FastAPI, Request
from starlette.exceptions import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import health
from app.config import get_settings

CODES = {400: "bad_request", 404: "not_found", 405: "method_not_allowed", 409: "conflict", 422: "validation_error"}


def _error(status: int, message: str, code: str | None = None) -> JSONResponse:
    code = code or CODES.get(status, "http_error" if status < 500 else "server_error")
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    app = FastAPI(title="ZCS LeadEngine")
    app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin], allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException):
        return _error(exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        msg = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        return _error(422, msg)

    app.include_router(health.router)
    return app
