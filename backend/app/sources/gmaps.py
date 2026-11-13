"""Google Maps listing lookup in a headless browser. Owner-accepted risk, see docs/data-sources.md.

Reads only the public place page: name, address, phone, weekly hours. A CAPTCHA, consent wall or unusual-traffic page
raises MapsBlocked and the caller stops. Nothing here tries to get past one.
"""
import re
import time
from dataclasses import dataclass, field

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
HOURS_ROW = re.compile(rf"^({'|'.join(DAYS)})\s*(.+)$")
LABELS_JS = "e => e.map(x => x.getAttribute('aria-label'))"
ROWS_JS = "e => e.map(x => x.innerText.replace(/\\s+/g, ' ').trim())"
SETTLE_SECONDS = 9  # the place panel renders a few seconds after the page loads


class MapsBlocked(Exception):
    """Google asked for a CAPTCHA or consent, or reported unusual traffic."""


@dataclass
class Listing:
    name: str
    address: str | None
    phone: str | None
    hours: list[dict] = field(default_factory=list)
    url: str | None = None


def clean_phone(label: str | None) -> str | None:
    """'Phone: +1 941-766-4122 ' -> '941-766-4122'."""
    d = re.sub(r"\D", "", (label or "").replace("Phone:", ""))
    d = d[1:] if len(d) == 11 and d[0] == "1" else d
    return f"{d[:3]}-{d[3:6]}-{d[6:]}" if len(d) == 10 else None


def parse_hours(rows: list[str]) -> list[dict]:
    """Rows like 'Friday8 AM–5 PM' or 'SaturdayClosed' to [{'day', 'hours'}]. Other tables on the page (ratings) are ignored."""
    out = []
    for r in rows:
        m = HOURS_ROW.match(r.replace("", "").strip())
        if m:
            out.append({"day": m[1], "hours": m[2].strip()})
    return sorted(out, key=lambda d: DAYS.index(d["day"]))


def read_listing(page) -> Listing | None:
    """None unless the page is one place with a name (a list of results or a bare address is not a match)."""
    if not page.locator('[data-item-id="address"], [data-item-id^="phone"]').count():
        return None
    names = [n for n in page.locator("h1").all_inner_texts() if n.strip() and n.strip() != "Results"]
    if not names:
        return None
    address = page.locator('[data-item-id="address"]').evaluate_all(LABELS_JS)
    phone = page.locator('[data-item-id^="phone"]').evaluate_all(LABELS_JS)
    return Listing(name=names[0].strip(), address=re.sub(r"^Address:\s*", "", address[0]).strip() if address else None,
                   phone=clean_phone(phone[0]) if phone else None, hours=parse_hours(page.locator("tr").evaluate_all(ROWS_JS)), url=page.url)


def _check_blocked(page) -> None:
    if "/sorry/" in page.url or "consent.google" in page.url or "unusual traffic" in page.content().lower():
        raise MapsBlocked("Google Maps asked for a CAPTCHA or consent. Stopped, nothing was bypassed. Try again later.")


class MapsBrowser:
    """One headless Chromium reused across lookups: `with MapsBrowser() as b: b.get(url)`."""

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        return self

    def __exit__(self, *exc):
        self._browser.close()
        self._pw.stop()

    @staticmethod
    def _settle(page) -> None:
        deadline = time.monotonic() + SETTLE_SECONDS
        while time.monotonic() < deadline and not page.locator('[data-item-id^="phone"]').count():
            page.wait_for_timeout(500)

    def get(self, url: str) -> Listing | None:
        page = self._browser.new_context(locale="en-US", viewport={"width": 1400, "height": 900}).new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            self._settle(page)
            _check_blocked(page)
            if not page.locator('[data-item-id^="phone"]').count() and page.locator("a.hfpxzc").count():
                # a list of results (common with a legal name): open Maps' first result; the caller still checks its address
                page.locator("a.hfpxzc").first.click(force=True)
                self._settle(page)
                _check_blocked(page)
            return read_listing(page)
        finally:
            page.context.close()


def lookup_once(url: str) -> Listing | None:
    with MapsBrowser() as b:
        return b.get(url)
