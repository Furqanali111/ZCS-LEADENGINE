"""Pure website verification and contact extraction. No I/O, never raises on any input."""

import ipaddress
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
BAD_EMAIL_ENDINGS = (".png", ".jpg", ".gif", ".svg", ".webp", ".pdf")
NAME_SUFFIXES = {"pllc", "llc", "inc", "pc", "dds"}
SKIP_TAGS = {"script", "style", "noscript", "template", "head"}


def registrable_domain(host: str) -> str:
    # shortcut: last two labels, wrong for co.uk style suffixes, fine for U.S. practices
    h = (host or "").strip().lower().rstrip(".").split(":")[0]
    if h.startswith("www."):
        h = h[4:]
    return ".".join(h.split(".")[-2:])


def blocked_host(host: str) -> bool:
    d = registrable_domain(host)
    return d in BLOCKED_DOMAINS or d.endswith(".gov")


def is_public_host(host: str) -> bool:
    # shortcut: names that resolve to private IPs are not caught, add resolution checks if this ever runs on a server
    h = (host or "").strip().lower().rstrip(".")
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        return "." in h and h != "localhost" and not h.endswith((".localhost", ".local", ".internal"))
    ip = getattr(ip, "ipv4_mapped", None) or ip
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved
                or ip.is_unspecified)


def candidate_roots(urls: list[str], limit: int = 3) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if not isinstance(u, str):
            continue
        try:
            parts = urlsplit(u.strip())
            host = (parts.hostname or "").lower()
        except ValueError:
            continue
        if parts.scheme not in ("http", "https") or not host or blocked_host(host) or not is_public_host(host):
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
    if not isinstance(raw, str):
        return None
    d = re.sub(r"\D", "", raw)
    if len(d) == 11 and d[0] == "1":
        d = d[1:]
    return d if len(d) == 10 else None


def _words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", s.lower().replace(".", "").replace("'", ""))


def verify_website(text: str, *, phones: list[str], name: str, city: str | None) -> str | None:
    text = (text if isinstance(text, str) else "")[:MAX_CHARS]
    name = name if isinstance(name, str) else ""
    city = city if isinstance(city, str) else ""
    wanted = {p for p in map(_phone10, phones or []) if p}
    if wanted and any("".join(m.groups()) in wanted for m in _PHONE.finditer(text)):
        return "phone"
    name_words = [w for w in _words(name) if len(w) >= 3 and w not in NAME_SUFFIXES]
    city_words = _words(city)
    if not name_words or not city_words:
        return None
    have = set(_words(text))
    return "name_city" if all(w in have for w in name_words + city_words) else None


@dataclass
class EmailHit:
    email: str


EMAIL_SCAN_CHARS = 200_000
_LOCAL_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._%+-")
_DOMAIN = re.compile(r"[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+")


def _find_emails(s: str) -> list[str]:
    """Candidates around each '@', local part at most 64 chars back, domain at most 255 forward: linear in len(s)."""
    out, at = [], s.find("@")
    while at != -1:
        lo = at
        while lo > 0 and at - lo < 64 and s[lo - 1] in _LOCAL_CHARS:
            lo -= 1
        m = _DOMAIN.match(s, at + 1, at + 256)
        if lo < at and m:
            out.append(f"{s[lo:at]}@{m.group()}")
        at = s.find("@", at + 1)
    return out


# Strict shape: junk before the local part or glued digits make the candidate wrong, so it is rejected, not repaired.
_EMAIL_OK = re.compile(r"[a-z0-9](?:[a-z0-9._%+\-]*[a-z0-9])?@(?:[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?\.)+[a-z]{2,}")
_GLUED_DIGITS = re.compile(r"\d{7,}[a-z]")
_MAILTO = re.compile(r"mailto:([^\"'<>\s]*)", re.I)


def extract_emails(html: str, text: str, *, site_domain: str, phone_verified: bool) -> list[EmailHit]:
    html, text = (html or "")[:EMAIL_SCAN_CHARS], (text or "")[:EMAIL_SCAN_CHARS]
    found = [m for h in _MAILTO.findall(html) for m in _find_emails(h.split("?")[0])]
    found += _find_emails(text)
    out: list[EmailHit] = []
    seen: set[str] = set()
    for raw in found:
        email = raw.lower()
        local, _, domain = email.partition("@")
        if not _EMAIL_OK.fullmatch(email) or _GLUED_DIGITS.match(local):
            continue
        if email in seen or email.endswith(BAD_EMAIL_ENDINGS):
            continue
        if not (phone_verified or registrable_domain(domain) == site_domain):
            continue
        seen.add(email)
        out.append(EmailHit(email))
    return out


@dataclass
class PersonHit:
    first_name: str
    last_name: str
    title: str


_W = r"[A-Z][a-z]+(?:[-'][A-Z][a-z]+)*"
_RUN = re.compile(rf"(?:(?:Dr|Mr|Ms|Mrs)\.\s+)?{_W}(?:\s+(?:{_W}|[A-Z]\.))*")
_CRED = r"(?:M\.?D\.?|D\.?O\.?|N\.?P\.?)"  # PA is excluded: "P.A." after a name is a business suffix
_LAST_FIRST = re.compile(rf"\b({_W}), ({_W})(?: [A-Z]\.)?,\s*(?={_CRED}(?![A-Za-z]))")
_CRED_AFTER = re.compile(rf"[\s,]*({_CRED})(?![A-Za-z])")
_BUSINESS_AFTER = re.compile(r"[\s,]*(?:P\.?A\.?|P\.?C\.?|PLLC|LLC|Inc\.?)(?![A-Za-z])")
_TITLE_WORDS = re.compile(
    r"(?i:\b(practice manager|office manager|billing manager|medical director|administrator|owner|director)\b)|\bCEO\b"
)
_SEP = re.compile(r"[\s,:;|\-]{0,4}")  # no period: a sentence end breaks the link
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


def _name_ok(words: list[str]) -> bool:
    return 2 <= len(words) <= 3 and not any(w.lower() in _STOP for w in words)


def _name_candidates(text: str) -> list[tuple[int, int, str, str]]:
    """(start, end, first, last) of each plausible person name, spans exclude prefixes and edge heading words."""
    out = []
    for m in _LAST_FIRST.finditer(text):
        if _name_ok([m.group(1), m.group(2)]):
            out.append((m.start(), m.end(), m.group(2), m.group(1)))
    for m in _RUN.finditer(text):
        toks = [(t.start() + m.start(), t.end() + m.start(), t.group()) for t in re.finditer(r"\S+", m.group())]
        toks = [t for t in toks if not t[2].endswith(".")]
        while toks and toks[0][2].lower() in _STOP:
            toks.pop(0)
        while toks and toks[-1][2].lower() in _STOP:
            toks.pop()
        if _name_ok([t[2] for t in toks]):
            out.append((toks[0][0], toks[-1][1], toks[0][2], toks[-1][2]))
    return out


def extract_people(text: str) -> list[PersonHit]:
    text = (text if isinstance(text, str) else "")[:MAX_CHARS]
    titles = [(m.start(), m.end(), re.sub(r"\s+", " ", m.group().lower())) for m in _TITLE_WORDS.finditer(text)]
    claimed: set[int] = set()
    out: list[PersonHit] = []
    seen: set[tuple[str, str]] = set()
    for s, e, first, last in sorted(_name_candidates(text)):
        if _BUSINESS_AFTER.match(text, e) or (first, last) in seen:
            continue
        cred = _CRED_AFTER.match(text, e)
        after = cred.end() if cred else e
        title = None
        for ts, te, t in titles:  # a full-word title must touch the name, after it (past a credential) or before it
            if ts not in claimed and (
                (ts >= after and _SEP.fullmatch(text, after, ts)) or (te <= s and _SEP.fullmatch(text, te, s))
            ):
                claimed.add(ts)
                title = t
                break
        if title is None and cred:
            title = cred.group(1).replace(".", "")
        if title:
            seen.add((first, last))
            out.append(PersonHit(first, last, title))
    return out
