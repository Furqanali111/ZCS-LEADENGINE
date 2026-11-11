import re
import uuid
from datetime import datetime, timezone
from io import BytesIO

from openpyxl import load_workbook

from app.models import Contact, Location, Organization, SourceRecord
from app.schemas import LeadFilters
from app.services.export import build_workbook

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def seed(db, name, npi, state="TX", score=80, priority="high", status="new", contacts=True):
    org = Organization(npi=npi, name=name, organization_type="practice", state=state, city="Austin", fit_score=score,
                       priority=priority, crm_status=status, primary_taxonomy_desc="Internal Medicine")
    db.add(org)
    db.flush()
    db.add(Location(organization_id=org.id, purpose="practice", address_1="2 Side St", zip="78701"))
    db.add(Location(organization_id=org.id, purpose="location", address_1="1 Main St", address_2="Suite 4", zip="78701", is_primary=True))
    if contacts:
        db.add(Contact(organization_id=org.id, first_name="Ann", last_name="Boss", title="Administrator", role="authorized_official", source_key="npi_registry"))
    db.add(SourceRecord(organization_id=org.id, source_key="npi_registry", external_id=npi, raw={},
                        collected_at=datetime(2026, 11, 11, 9, 30, tzinfo=timezone.utc)))
    db.commit()
    return org


def load(data):
    return load_workbook(BytesIO(data))


def export(db, filters=None, ids=None):
    return load(build_workbook(db, filters=filters, ids=ids))


def test_workbook_has_three_sheets(db):
    assert export(db).sheetnames == ["All Leads", "Contacts", "Summary"]


def test_all_leads_headers_match_spec(db):
    assert [c.value for c in export(db)["All Leads"][1]] == [
        "Organization Name", "DBA Name", "Specialty", "Organization Type", "Parent Organization", "Business Phone",
        "Fax", "Contact Person", "Contact Title", "Contact Phone", "Address", "City", "State", "ZIP", "NPI",
        "Lead Score", "Lead Priority", "Outreach Status", "Source", "Collected On"]


def test_row_values(db):
    seed(db, "Acme Clinic", "1111111111", priority="critical", status="email_sent", score=91)
    ws = export(db)["All Leads"]
    row = {h.value: c.value for h, c in zip(ws[1], ws[2])}
    assert row["Organization Name"] == "Acme Clinic"
    assert row["State"] == "TX"
    assert row["Lead Score"] == 91
    assert row["Lead Priority"] == "Critical"
    assert row["Outreach Status"] == "Email sent"
    assert row["Address"] == "1 Main St Suite 4"
    assert row["Source"] == "CMS NPI Registry"
    assert row["Collected On"].strftime("%Y-%m-%d") == "2026-11-11"
    assert row["Contact Person"] == "Ann Boss"
    assert ws["T2"].number_format == "yyyy-mm-dd"
    assert ws["Q2"].fill.fgColor.rgb.endswith("F4B6B6")
    contacts = export(db)["Contacts"]
    assert [c.value for c in contacts[2]][:3] == ["Acme Clinic", "1111111111", "Ann"]


def test_ids_override_filters(db):
    a = seed(db, "A Clinic", "1111111111", state="TX")
    seed(db, "B Clinic", "2222222222", state="FL")
    ws = export(db, filters=LeadFilters(state="FL"), ids=[a.id])["All Leads"]
    assert [r[0].value for r in ws.iter_rows(min_row=2)] == ["A Clinic"]


def test_filters_limit_rows(db):
    seed(db, "A Clinic", "1111111111", state="TX")
    seed(db, "B Clinic", "2222222222", state="FL")
    ws = export(db, filters=LeadFilters(state="FL"))["All Leads"]
    assert [r[0].value for r in ws.iter_rows(min_row=2)] == ["B Clinic"]


def test_formula_like_name_is_text(db):
    seed(db, "=HYPERLINK(1)", "1111111111")
    seed(db, "\t+cmd", "2222222222", score=10)
    ws = export(db)["All Leads"]
    assert ws["A2"].data_type == "s" and ws["A2"].value == "=HYPERLINK(1)"
    assert ws["A3"].data_type == "s" and ws["A3"].value == "\t+cmd"


def test_header_frozen_and_filtered(db):
    seed(db, "A Clinic", "1111111111")
    ws = export(db)["All Leads"]
    assert ws.freeze_panes == "A2"
    assert ws.auto_filter.ref == "A1:T2"
    assert ws["A1"].font.bold


def test_column_width_capped(db):
    seed(db, "N" * 200, "1111111111")
    ws = export(db)["All Leads"]
    assert ws.column_dimensions["A"].width == 50
    assert ws.column_dimensions["L"].width < 50


def test_summary_counts(db):
    seed(db, "A", "1111111111", priority="high", state="TX")
    seed(db, "B", "2222222222", priority="high", state="TX", status="called")
    seed(db, "C", "3333333333", priority="low", state="FL")
    rows = {r[0].value: r[1].value for r in export(db)["Summary"].iter_rows() if r[0].value}
    assert rows["Total leads"] == 3
    assert rows["High"] == 2 and rows["Low"] == 1
    assert rows["TX"] == 2 and rows["FL"] == 1
    assert rows["Called"] == 1 and rows["New"] == 2
    assert rows["Filters"] == "None"


def test_no_conversion_column(db):
    wb = export(db)
    for ws in wb:
        for c in ws[1]:
            assert "conversion" not in str(c.value).lower() and "probab" not in str(c.value).lower()


def test_empty_export_still_valid(db):
    wb = export(db)
    ws = wb["All Leads"]
    assert ws.max_row == 1 and ws["A1"].value == "Organization Name"
    assert wb["Summary"]["B3"].value == 0


def test_export_endpoint_returns_xlsx(client, db):
    a = seed(db, "A Clinic", "1111111111")
    r = client.post("/api/exports/excel", json={"ids": [str(a.id)]})
    assert r.status_code == 200
    assert r.headers["content-type"] == XLSX
    assert re.fullmatch(r'attachment; filename="zcs-leads-\d{8}-\d{4}\.xlsx"', r.headers["content-disposition"])
    assert load(r.content)["All Leads"]["A2"].value == "A Clinic"
    assert client.post("/api/exports/excel", json={}).status_code == 200


def test_export_endpoint_rejects_bad_body(client):
    assert client.post("/api/exports/excel", json={"nope": 1}).status_code == 422
    assert client.post("/api/exports/excel", json={"ids": [str(uuid.uuid4())] * 5001}).status_code == 422
    assert client.post("/api/exports/excel", json={"filters": {"state": "ZZ"}}).status_code == 422


def test_empty_ids_exports_no_leads(db):
    seed(db, "A Clinic", "1111111111")
    ws = export(db, ids=[])["All Leads"]
    assert ws.max_row == 1
