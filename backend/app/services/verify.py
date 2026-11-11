"""Pure website verification and contact extraction. No I/O, never raises on any input."""

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

BLOCKED_DOMAINS = frozenset(
    {
        "yelp.com", "healthgrades.com", "vitals.com", "zocdoc.com", "webmd.com",
        "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com",
        "youtube.com", "yellowpages.com", "manta.com", "bbb.org", "mapquest.com",
        "npino.com", "npiprofile.com", "doximity.com", "usnews.com", "ratemds.com",
        "wikipedia.org",
    }
)  # any .gov host is blocked separately

MAX_CHARS = 2_000_000  # shortcut: longer inputs are truncated, not a real practice page
LINK_WORDS = ("contact", "about", "team", "staff", "provider", "doctor", "physician", "our-team", "leadership")
GENERAL_LOCALS = frozenset(
    {"info", "office", "contact", "admin", "frontdesk", "appointments", "billing", "hello", "reception",
     "scheduling", "mail", "support"}
)
BAD_EMAIL_ENDINGS = (".png", ".jpg", ".gif", ".svg", ".webp", ".pdf")
NAME_SUFFIXES = {"pllc", "pa", "llc", "inc", "md"}
SKIP_TAGS = {"script", "style", "noscript", "template", "head"}


def registrable_domain(host: str) -> str:
    # shortcut: last two labels, wrong for co.uk style suffixes, fine for U.S. practices
    h = (host or "").strip().lower().rstrip(".").split(":")[0]
    if h.startswith("www."):
        h = h[4:]
    return ".".join(h.split(".")[-2:])


def _blocked(host: str) -> bool:
    d = registrable_domain(host)
    return d in BLOCKED_DOMAINS or d.endswith(".gov")


def candidate_roots(urls: list[str], limit: int = 3) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        try:
            parts = urlsplit((u or "").strip())
            host = (parts.hostname or "").lower()
        except ValueError:
            continue
        if parts.scheme not in ("http", "https") or not host or _blocked(host):
            continue
        dom = registrable_domain(host)
        if dom in seen:
            continue
        seen.add(dom)
        out.append(f"https://{host.removeprefix('www.')}/")
        if len(out) >= limit:
            break
    return out


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self.skip += 1
        self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS and self.skip:
            self.skip -= 1
        self.parts.append(" ")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def page_text(html: str) -> str:
    p = _Text()
    try:
        p.feed((html or "")[:MAX_CHARS])
        p.close()
    except Exception:  # noqa: BLE001 - malformed input must degrade to partial text
        pass
    return " ".join("".join(p.parts).split())


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self.href: str | None = None
        self.buf: list[str] = []

    def close_link(self):
        if self.href is not None:
            self.links.append((self.href, " ".join("".join(self.buf).split())))
        self.href, self.buf = None, []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.close_link()
            self.href = dict(attrs).get("href") or None

    def handle_endtag(self, tag):
        if tag == "a":
            self.close_link()

    def handle_data(self, data):
        if self.href is not None:
            self.buf.append(data)


def page_links(html: str, base_url: str) -> list[tuple[str, str]]:
    p = _Links()
    try:
        p.feed((html or "")[:MAX_CHARS])
        p.close()
        p.close_link()
    except Exception:  # noqa: BLE001
        pass
    out = []
    for href, text in p.links:
        try:
            absolute = urljoin(base_url, href.strip()).split("#")[0]
            if urlsplit(absolute).scheme in ("http", "https"):
                out.append((absolute, text))
        except ValueError:
            continue
    return out


def relevant_links(links: list[tuple[str, str]], site_domain: str, limit: int = 4) -> list[str]:
    out: list[str] = []
    for url, text in links:
        try:
            parts = urlsplit(url)
            if registrable_domain(parts.hostname or "") != site_domain:
                continue
        except ValueError:
            continue
        hay = f"{text} {parts.path}".lower()
        if any(w in hay for w in LINK_WORDS) and url not in out:
            out.append(url)
            if len(out) >= limit:
                break
    return out


# 10 digits, optionally with a leading 1, never touching other digits.
_PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.\-]{0,2})?\(?(\d{3})\)?[\s.\-]{0,2}(\d{3})[\s.\-]{0,2}(\d{4})(?!\d)")


def _phone10(raw: str) -> str | None:
    d = re.sub(r"\D", "", raw or "")
    if len(d) == 11 and d[0] == "1":
        d = d[1:]
    return d if len(d) == 10 else None


def _words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", s.lower().replace(".", "").replace("'", ""))


def verify_website(text: str, *, phones: list[str], name: str, city: str | None) -> str | None:
    text = (text or "")[:MAX_CHARS]
    wanted = {p for p in map(_phone10, phones) if p}
    if wanted and any("".join(m.groups()) in wanted for m in _PHONE.finditer(text)):
        return "phone"
    name_words = [w for w in _words(name or "") if len(w) >= 3 and w not in NAME_SUFFIXES]
    city_words = _words(city or "")
    if not name_words or not city_words:
        return None
    have = set(_words(text))
    return "name_city" if all(w in have for w in name_words + city_words) else None


@dataclass
class EmailHit:
    email: str
    general: bool


_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+")
_MAILTO = re.compile(r"mailto:([^\"'<>\s]*)", re.I)


def extract_emails(html: str, text: str, *, site_domain: str, phone_verified: bool) -> list[EmailHit]:
    html, text = (html or "")[:MAX_CHARS], (text or "")[:MAX_CHARS]
    found = [m for h in _MAILTO.findall(html) for m in _EMAIL.findall(h.split("?")[0])]
    found += _EMAIL.findall(text)
    out: list[EmailHit] = []
    seen: set[str] = set()
    for raw in found:
        email = raw.lower().strip(".,;:!?)(<>-_%+")
        local, _, domain = email.partition("@")
        if not local or email in seen or email.endswith(BAD_EMAIL_ENDINGS):
            continue
        if not (phone_verified or registrable_domain(domain) == site_domain):
            continue
        seen.add(email)
        out.append(EmailHit(email, local in GENERAL_LOCALS))
    return out


@dataclass
class PersonHit:
    first_name: str
    last_name: str
    title: str


_W = r"[A-Z][a-z]+(?:[-'][A-Z][a-z]+)*"
_RUN = re.compile(rf"(?:(?:Dr|Mr|Ms|Mrs)\.\s+)?{_W}(?:\s+(?:{_W}|[A-Z]\.))*")
_CRED = r"(?:M\.?D\.?|D\.?O\.?|N\.?P\.?|P\.?A\.?)"
_LAST_FIRST = re.compile(rf"\b({_W}), ({_W})(?: [A-Z]\.)?,\s*(?={_CRED}(?![A-Za-z]))")
_TITLE_WORDS = re.compile(
    r"(?i:\b(practice manager|office manager|billing manager|medical director|administrator|owner|director)\b)|\bCEO\b"
)
_TITLE_ABBR = re.compile(r"(?<![A-Za-z])(M\.D\.|MD|D\.O\.|DO|N\.P\.|NP|P\.A\.|PA)(?![A-Za-z])")
_STOP = {
    w.lower()
    for w in (
        "Medical Center Family Practice Office Manager Director Health Care Internal Medicine Dr Mr Ms Mrs Our "
        "Friendly Team Staff Meet Welcome About Contact Administrator Owner Billing Chief Executive Officer Clinic "
        "Physician Provider Providers Doctor Doctors Services Group Associates Patient Patients New Home Hours "
        "Location Locations Pediatrics Geriatrics Urgent Primary Specialty Hospital Wellness Senior Online Portal "
        "Request Appointment Appointments Insurance Accepted Phone Fax Email Address Monday Tuesday Wednesday "
        "Thursday Friday Saturday Sunday Read More Learn Click Here Call Today Schedule Visit Us The And For With"
    ).split()
}
_WINDOW = 60


def _trim(words: list[str]) -> list[str]:
    # heading words glued to a name ("Our Team Jane Doe") are dropped from the edges only
    while words and words[0].lower() in _STOP:
        words = words[1:]
    while words and words[-1].lower() in _STOP:
        words = words[:-1]
    return words


def _name_ok(words: list[str]) -> bool:
    return 2 <= len(words) <= 3 and not any(w.lower() in _STOP for w in words)


def extract_people(text: str) -> list[PersonHit]:
    text = (text or "")[:MAX_CHARS]
    names: list[tuple[int, int, str, str]] = []  # start, end, first, last
    for m in _LAST_FIRST.finditer(text):
        if _name_ok([m.group(1), m.group(2)]):
            names.append((m.start(), m.end(), m.group(2), m.group(1)))
    for m in _RUN.finditer(text):
        words = _trim([w for w in re.sub(r"^(?:Dr|Mr|Ms|Mrs)\.\s+", "", m.group()).split() if not w.endswith(".")])
        if _name_ok(words):
            names.append((m.start(), m.end(), words[0], words[-1]))
    titles = [(m.start(), m.end(), re.sub(r"\s+", " ", m.group().lower()), True) for m in _TITLE_WORDS.finditer(text)]
    titles += [(m.start(), m.end(), m.group().replace(".", ""), False) for m in _TITLE_ABBR.finditer(text)]
    out: list[PersonHit] = []
    seen: set[tuple[str, str]] = set()
    for s, e, first, last in sorted(names):
        near = []
        for ts, te, title, is_word in titles:
            if ts < e and te > s:
                continue
            gap = max(ts - e, s - te, 0)
            if gap <= _WINDOW:
                near.append((not is_word, gap, title))
        if near and (first, last) not in seen:
            seen.add((first, last))
            out.append(PersonHit(first, last, min(near)[2]))
    return out
