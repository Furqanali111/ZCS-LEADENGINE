from collections import Counter
from datetime import datetime
from io import BytesIO
from uuid import UUID

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Organization
from app.schemas import LeadFilters
from app.services.leads import lead_query

HEADERS = ["Organization Name", "DBA Name", "Specialty", "Organization Type", "Parent Organization", "Business Phone",
           "Fax", "Contact Person", "Contact Title", "Contact Phone", "Address", "City", "State", "ZIP", "NPI",
           "Lead Score", "Lead Priority", "Outreach Status", "Source", "Collected On"]
CONTACT_HEADERS = ["Organization Name", "NPI", "First Name", "Last Name", "Title", "Phone", "Role"]
SOURCE_NAMES = {"npi_registry": "CMS NPI Registry"}
# Light fills with dark text; the label is always in the cell, so colour is never the only signal.
PRIORITY_FILLS = {"Critical": "F4B6B6", "High": "F9D5A7", "Medium": "FFF2A8", "Low": "D9D9D9"}
STATUS_FILLS = {"New": "DDE7F5", "Researching": "C9DAF8", "Email sent": "D5E8D4", "Called": "B7E1CD",
                "Follow up required": "FFE0B2", "Interested": "C6EFCE", "Meeting scheduled": "A9D8A9",
                "Not interested": "E0E0E0", "Converted": "8FD19E", "Do not contact": "F4B6B6"}
LOADS = (selectinload(Organization.contacts), selectinload(Organization.locations), selectinload(Organization.source_records))
MAX_WIDTH = 50


def label(value: str | None) -> str:
    return value.replace("_", " ").capitalize() if value else ""


def _put(ws, row: list) -> None:
    """Appends a row; strings are forced to text so =, +, -, @ (or tab/CR) can never run as a formula."""
    ws.append(row)
    for cell in ws[ws.max_row]:
        if isinstance(cell.value, str):
            cell.data_type = "s"


def _finish(ws) -> None:
    for i, col in enumerate(ws.columns, 1):
        longest = max((len(str(c.value)) for c in col if c.value is not None), default=0)
        ws.column_dimensions[get_column_letter(i)].width = min(longest + 2, MAX_WIDTH)


def _header(ws, headers: list[str]) -> None:
    _put(ws, headers)
    for c in ws[1]:
        c.font = Font(bold=True)
    ws.freeze_panes = "A2"


def _fill(cell, fills: dict[str, str]) -> None:
    if cell.value in fills:
        cell.fill = PatternFill("solid", fgColor=fills[cell.value])


def describe(filters: LeadFilters | None, ids: list[UUID] | None) -> str:
    if ids:
        return f"{len(ids)} selected leads"
    used = {k: v for k, v in (filters.model_dump() if filters else {}).items() if v is not None}
    return ", ".join(f"{k}={v}" for k, v in used.items()) or "None"


def build_workbook(session: Session, *, filters: LeadFilters | None, ids: list[UUID] | None) -> bytes:
    o = Organization
    stmt = select(o).where(o.id.in_(ids)) if ids else lead_query(filters or LeadFilters())
    orgs = session.scalars(stmt.options(*LOADS).order_by(o.fit_score.desc().nulls_last(), o.name, o.id)).all()

    wb = Workbook()
    leads = wb.active
    leads.title = "All Leads"
    _header(leads, HEADERS)
    contacts = wb.create_sheet("Contacts")
    _header(contacts, CONTACT_HEADERS)

    for org in orgs:
        by_role = {c.role: c for c in org.contacts}
        person = by_role.get("authorized_official") or by_role.get("provider")
        loc = next((x for x in org.locations if x.is_primary), org.locations[0] if org.locations else None)
        src = org.source_records[0] if org.source_records else None
        _put(leads, [
            org.name, org.dba_name, org.primary_taxonomy_desc, label(org.organization_type),
            org.parent_organization_name, org.phone, org.fax,
            f"{person.first_name} {person.last_name}".strip() if person else None,
            person.title if person else None, person.phone if person else None,
            " ".join(p for p in (loc.address_1, loc.address_2) if p) if loc else None,
            org.city, org.state, loc.zip if loc else None, org.npi, org.fit_score,
            label(org.priority), label(org.crm_status),
            SOURCE_NAMES.get(src.source_key, src.source_key) if src else None,
            src.collected_at.replace(tzinfo=None).date() if src else None,
        ])
        row = leads.max_row
        leads.cell(row, 20).number_format = "yyyy-mm-dd"
        _fill(leads.cell(row, 17), PRIORITY_FILLS)
        _fill(leads.cell(row, 18), STATUS_FILLS)
        for c in org.contacts:
            _put(contacts, [org.name, org.npi, c.first_name, c.last_name, c.title, c.phone, c.role])

    for ws in (leads, contacts):
        _finish(ws)
        ws.auto_filter.ref = ws.dimensions

    summary = wb.create_sheet("Summary")
    _put(summary, ["Exported at", datetime.now().strftime("%Y-%m-%d %H:%M")])
    _put(summary, ["Filters", describe(filters, ids)])
    _put(summary, ["Total leads", len(orgs)])
    for title, counts in (("By priority", Counter(label(x.priority) or "Unscored" for x in orgs)),
                          ("By status", Counter(label(x.crm_status) for x in orgs)),
                          ("By state", Counter(x.state for x in orgs))):
        _put(summary, [])
        _put(summary, [title, "Leads"])
        summary.cell(summary.max_row, 1).font = Font(bold=True)
        for k, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            _put(summary, [k, n])
    _finish(summary)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
