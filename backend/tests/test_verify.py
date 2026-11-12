from pathlib import Path

import pytest

from app.services import verify as v

FX = Path(__file__).parent / "fixtures" / "web"


def fx(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


def test_registrable_domain():
    assert v.registrable_domain("www.Sunrise.com") == "sunrise.com"
    assert v.registrable_domain("a.b.sunrise.com") == "sunrise.com"


def test_page_text_drops_script_and_style():
    t = v.page_text(fx("practice_home.html"))
    assert "Sunrise Family Medicine" in t and "hidden@script.com" not in t
    assert "color:red" not in t and "  " not in t


def test_phone_match_any_formatting():
    text = v.page_text(fx("practice_home.html"))
    for p in ["8135550142", "(813) 555-0142", "+1 813-555-0142", "1-813-555-0142"]:
        assert v.verify_website(text, phones=[p], name="Zzz", city=None) == "phone"
    assert v.verify_website(text, phones=["8135559999"], name="Zzz", city=None) is None


def test_phone_not_inside_longer_digit_run():
    assert v.verify_website("id 1234567890123456", phones=["7890123456"], name="Q", city=None) is None
    assert v.verify_website("call 18135550142 now", phones=["8135550142"], name="Q", city=None) == "phone"


def test_name_city_match_with_suffixes():
    text = v.page_text(fx("practice_home.html"))
    assert v.verify_website(text, phones=[], name="SUNRISE FAMILY MEDICINE, P.A.", city="tampa") == "name_city"
    assert v.verify_website(text, phones=[], name="Sunrise Family Medicine PLLC", city="Miami") is None
    assert v.verify_website(text, phones=[], name="Sunrise Pediatrics LLC", city="Tampa") is None


def test_name_with_no_distinctive_words_never_matches():
    assert v.verify_website("PA MD LLC Tampa", phones=[], name="P.A. MD", city="Tampa") is None


def test_no_phone_lead_uses_name_city_only():
    text = v.page_text(fx("aggregator.html"))
    assert v.verify_website(text, phones=[], name="Sunrise Family Medicine", city="Tampa") == "name_city"
    assert v.verify_website(text, phones=[], name="Sunrise Family Medicine", city=None) is None


def test_aggregator_domain_dropped():
    urls = ["https://www.yelp.com/biz/x", "https://sunrisefm.com/a", "https://data.cms.gov/x", "https://m.facebook.com/s"]
    assert v.candidate_roots(urls) == ["https://sunrisefm.com/"]


def test_candidate_roots_dedupe_limit_order():
    urls = ["https://a.com/1", "http://www.a.com/2", "https://b.com", "https://c.com", "https://d.com"]
    assert v.candidate_roots(urls) == ["https://a.com/", "https://b.com/", "https://c.com/"]
    assert v.candidate_roots(urls, limit=1) == ["https://a.com/"]


def test_non_http_urls_dropped():
    urls = ["javascript:alert(1)", "mailto:a@b.com", "ftp://x.com/f", "//x.com", "", "https://ok.com/p"]
    assert v.candidate_roots(urls) == ["https://ok.com/"]


def test_page_links_and_relevant_links():
    links = v.page_links(fx("practice_home.html"), "https://www.sunrisefm.com/")
    assert ("https://www.sunrisefm.com/contact-us", "Contact") in links
    rel = v.relevant_links(links, "sunrisefm.com")
    assert rel == [
        "https://www.sunrisefm.com/about",
        "https://www.sunrisefm.com/contact-us",
        "https://www.sunrisefm.com/our-team",
    ]
    other = [("https://evil.com/contact", "Contact")]
    assert v.relevant_links(other, "sunrisefm.com") == []
    many = [(f"https://s.com/team{i}", "") for i in range(9)]
    assert len(v.relevant_links(many, "s.com")) == 4


def test_malformed_html_does_not_raise():
    h = fx("malformed.html")
    assert isinstance(v.page_text(h), str)
    assert isinstance(v.page_links(h, "https://a.com/"), list)
    assert isinstance(v.extract_emails(h, v.page_text(h), site_domain="y.com", phone_verified=False), list)
    for s in ["", "<", "<a href=", "<<<>>>", "&#99999999999;"]:
        v.page_text(s), v.page_links(s, "https://a.com"), v.extract_people(s)


def test_bytes_garbage_text():
    garbage = bytes(range(256)).decode("latin-1") * 50 + "\x00�"
    v.page_text(garbage)
    assert v.verify_website(garbage, phones=["8135550142"], name="X Y Z", city="A") is None
    assert v.extract_emails(garbage, garbage, site_domain="a.com", phone_verified=True) == []
    assert v.extract_people(garbage) == []
    v.extract_people("A " * 200000)


def test_email_lookalikes():
    html = fx("practice_contact.html")
    hits = v.extract_emails(html, v.page_text(html), site_domain="sunrisefm.com", phone_verified=False)
    assert [h.email for h in hits] == ["info@sunrisefm.com", "billing@sunrisefm.com"]
    assert v.extract_emails("", "logo@2x.png A@B.com.", site_domain="b.com", phone_verified=False)[0].email == "a@b.com"
    hits = v.extract_emails('<a href="mailto:a@b.com?subject=x">x</a>', "", site_domain="b.com", phone_verified=False)
    assert [h.email for h in hits] == ["a@b.com"]
    assert v.extract_emails("", "x@b.com.png y@b.com.pdf", site_domain="b.com", phone_verified=True) == []


def test_email_foreign_domain_needs_phone_verified():
    html = fx("practice_contact.html")
    text = v.page_text(html)
    off = [h.email for h in v.extract_emails(html, text, site_domain="sunrisefm.com", phone_verified=False)]
    on = [h.email for h in v.extract_emails(html, text, site_domain="sunrisefm.com", phone_verified=True)]
    assert "someone@otherdomain.org" not in off and "someone@otherdomain.org" in on


def test_email_not_decoded_or_built():
    assert v.extract_emails("", "info [at] a.com john(at)a.com", site_domain="a.com", phone_verified=True) == []


def test_long_run_without_at_is_linear():
    import time
    t0 = time.perf_counter()
    assert v.extract_emails("", "a" * 1_000_000, site_domain="a.com", phone_verified=True) == []
    assert time.perf_counter() - t0 < 1


def test_email_found_after_junk():
    hits = v.extract_emails("", "x" * 5000 + " jane@a.com", site_domain="a.com", phone_verified=False)
    assert [h.email for h in hits] == ["jane@a.com"]


@pytest.mark.parametrize("host", ["127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254", "localhost", "::1",
                                  "intranet", "a.localhost", "printer.local", "db.internal", "0.0.0.0", "224.0.0.1",
                                  "::ffff:127.0.0.1", ""])
def test_non_public_hosts(host):
    assert not v.is_public_host(host)


def test_public_hosts():
    assert v.is_public_host("example.com") and v.is_public_host("8.8.8.8") and v.is_public_host("WWW.Example.com.")


def test_candidate_roots_drops_non_public():
    urls = ["http://127.0.0.1/", "http://10.0.0.5/", "http://192.168.1.1/", "http://169.254.169.254/x",
            "http://localhost:8000/", "http://[::1]/", "http://intranet/", "https://good.example.com/a"]
    assert v.candidate_roots(urls) == ["https://good.example.com/"]


def test_person_with_suffixes():
    text = "Smith, John A., M.D., P.A. is our Medical Director."
    assert v.extract_people(text) == [v.PersonHit("John", "Smith", "MD")]
    p = v.extract_people(v.page_text(fx("practice_team.html")))
    names = {(x.first_name, x.last_name): x.title for x in p}
    assert names[("Jane", "Doe")].lower() == "practice manager"
    assert ("John", "Smith") in names


def test_title_without_name_yields_nothing():
    assert v.extract_people("Our Friendly Office Manager is here to help") == []
    assert v.extract_people("Family Medicine Center Owner") == []
    assert v.extract_people("Practice Manager") == []


def test_business_names_are_not_people():
    assert v.extract_people("Palm Beach Cardiology, P.A.") == []
    assert v.extract_people("Located in Harrisburg PA 17101. Jane Roe") == []
    assert v.extract_people("Sunrise Care Associates PLLC, Owner") == []


def test_abbreviation_title_only_directly_after_name():
    assert v.extract_people("Dr. John Smith, MD") == [v.PersonHit("John", "Smith", "MD")]
    assert v.extract_people("John Smith NP sees patients") == [v.PersonHit("John", "Smith", "NP")]
    assert v.extract_people("MD visits are booked. Jane Roe") == []


def test_title_must_be_adjacent_to_the_name():
    text = "Jane Doe, Practice Manager. Call Bob Ray today for owner"
    assert v.extract_people(text) == [v.PersonHit("Jane", "Doe", "practice manager")]
    assert v.extract_people("Owner: Bob Ray") == [v.PersonHit("Bob", "Ray", "owner")]
    assert v.extract_people("Bob Ray - Owner") == [v.PersonHit("Bob", "Ray", "owner")]
    assert v.extract_people("Bob Ray\nCEO") == [v.PersonHit("Bob", "Ray", "ceo")]
    assert v.extract_people("Bob Ray. Owner of nothing") == []


def test_email_rejects_instead_of_repairing():
    for bad in ["_a@b.com", "8135550142info@b.com", ".a@b.com", "a@b.c", "a@b.c1", "a@-b.com"]:
        assert v.extract_emails("", f"mail {bad} now", site_domain="b.com", phone_verified=True) == [], bad
    assert [h.email for h in v.extract_emails("", "(info@b.com)", site_domain="b.com", phone_verified=False)] == ["info@b.com"]


def test_non_string_items_are_skipped():
    assert v.candidate_roots([None, 5, "https://ok.com/x"]) == ["https://ok.com/"]
    text = "Call 813-555-0142"
    assert v.verify_website(text, phones=[None, 8135550142, "8135550142"], name="Zzz", city=None) == "phone"
    assert v.verify_website(text, phones=[None, 8135550142], name=None, city=5) is None
    assert v.verify_website(None, phones=None, name="Abc", city="Def") is None
