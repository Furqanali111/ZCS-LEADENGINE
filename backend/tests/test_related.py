from app.models import Contact, Organization


def make(db, npi, name="Org", **kw):
    o = Organization(npi=npi, name=name, organization_type="practice", state="TX", **kw)
    db.add(o)
    db.commit()
    return o


def official(db, org, first, last, role="authorized_official"):
    db.add(Contact(organization_id=org.id, first_name=first, last_name=last, role=role, source_key="npi_registry"))
    db.commit()


def related(client, org):
    r = client.get(f"/api/leads/{org.id}/related")
    assert r.status_code == 200
    return {x["id"]: x for x in r.json()}


def test_same_phone_ignores_format_and_country_code(client, db):
    a = make(db, "1", "Alpha", phone="(555) 123-4567")
    b = make(db, "2", "Beta", phone="1-555-123-4567")
    make(db, "3", "Gamma", phone="555-123-9999")
    got = related(client, a)
    assert list(got) == [str(b.id)] and got[str(b.id)]["reasons"] == ["same_phone"]


def test_same_name_normalizes_case_punctuation_and_legal_suffix(client, db):
    a = make(db, "1", "Sunrise Family Medicine, P.C.")
    b = make(db, "2", "SUNRISE  family medicine LLC")
    make(db, "3", "Sunrise Family Medicine Associates")
    assert list(related(client, a)) == [str(b.id)]


def test_same_parent_and_same_website(client, db):
    a = make(db, "1", "Alpha", parent_organization_name="Big Health", website="https://www.alpha-med.com/about")
    b = make(db, "2", "Beta", parent_organization_name=" big health ", website="http://alpha-med.com")
    c = make(db, "3", "Gamma", website="https://notalpha-med.com")
    got = related(client, a)
    assert list(got) == [str(b.id)] and set(got[str(b.id)]["reasons"]) == {"same_parent", "same_website"}
    assert str(c.id) not in got


def test_same_official_only_for_authorized_official_role(client, db):
    a, b, c = make(db, "1", "Alpha"), make(db, "2", "Beta"), make(db, "3", "Gamma")
    official(db, a, "Jane", "Doe")
    official(db, b, "jane", "DOE")
    official(db, c, "Jane", "Doe", role="staff")
    got = related(client, a)
    assert list(got) == [str(b.id)] and got[str(b.id)]["reasons"] == ["same_official"]


def test_empty_values_never_match(client, db):
    a = make(db, "1", "", phone="", parent_organization_name="", website="")
    make(db, "2", "", phone="", parent_organization_name="", website="")
    make(db, "3", "LLC", phone=None)
    official(db, a, "", "")
    assert related(client, a) == {}
    assert related(client, make(db, "4", "LLC")) == {}  # name is only a suffix


def test_excludes_self_lists_suppressed_and_sorts_most_reasons_first(client, db):
    a = make(db, "1", "Alpha", phone="5551234567", parent_organization_name="Grp")
    weak = make(db, "2", "Other", phone="5551234567", fit_score=99)
    strong = make(db, "3", "Third", phone="5551234567", parent_organization_name="Grp", crm_status="do_not_contact", owner="Ali")
    r = client.get(f"/api/leads/{a.id}/related").json()
    assert [x["id"] for x in r] == [str(strong.id), str(weak.id)]
    assert r[0]["owner"] == "Ali" and r[0]["crm_status"] == "do_not_contact" and r[0]["reasons"] == ["same_phone", "same_parent"]


def test_capped_at_20_and_404(client, db):
    a = make(db, "0", "Alpha", parent_organization_name="Grp")
    for i in range(1, 26):
        make(db, str(i), f"Org {i}", parent_organization_name="Grp")
    assert len(client.get(f"/api/leads/{a.id}/related").json()) == 20
    assert client.get("/api/leads/00000000-0000-0000-0000-000000000000/related").status_code == 404
