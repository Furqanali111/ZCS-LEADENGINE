import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_session

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
def health(session: Session = Depends(get_session)):
    try:
        session.execute(text("SELECT 1"))
    except Exception as e:
        logger.warning("health check failed: %s", type(e).__name__)
        return JSONResponse({"status": "degraded", "database": "error"}, status_code=503)
    return {"status": "ok", "database": "ok"}
