from datetime import datetime

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import ExportRequest
from app.services.export import build_workbook

router = APIRouter(prefix="/api/exports")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.post("/excel")
def export_excel(body: ExportRequest, session: Session = Depends(get_session)):
    data = build_workbook(session, filters=body.filters, ids=body.ids)
    name = f"zcs-leads-{datetime.now():%Y%m%d-%H%M}.xlsx"
    return Response(data, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"'})
