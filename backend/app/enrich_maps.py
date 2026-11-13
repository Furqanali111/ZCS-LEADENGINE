"""Look up hospitals on Google Maps: python -m app.enrich_maps --limit 10 [--state TX]

Picks the best-scored hospitals not checked yet, one at a time, a few seconds apart. Stops at once if Google asks for a CAPTCHA.
"""
import argparse
import time

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Organization, SourceConfig
from app.services.maps import enrich_maps
from app.sources.gmaps import MapsBlocked, MapsBrowser

PAUSE_SECONDS = 4


def run(session_factory, *, limit: int, state: str | None = None, get=None, sleep=time.sleep) -> dict:
    counts = {"matched": 0, "no_match": 0, "failed": 0, "blocked": 0}
    with session_factory() as session:
        if session.scalar(select(SourceConfig.status).where(SourceConfig.key == "google_maps")) != "available":
            raise SystemExit("google_maps is not available in source_configs")
        stmt = (select(Organization).options(selectinload(Organization.locations))
                .where(Organization.organization_type == "hospital", Organization.maps_status.in_(("not_run", "failed"))))
        if state:
            stmt = stmt.where(Organization.state == state.upper())
        orgs = session.scalars(stmt.order_by(Organization.fit_score.desc().nulls_last(), Organization.id).limit(limit)).all()
        browser = None
        try:
            if get is None:
                browser = MapsBrowser().__enter__()
                get = browser.get
            for i, org in enumerate(orgs):
                if i:
                    sleep(PAUSE_SECONDS)
                try:
                    counts[enrich_maps(session, org, lookup=get)] += 1
                except MapsBlocked:
                    session.rollback()
                    counts["blocked"] += 1
                    break
                except Exception:  # noqa: BLE001 - one bad lookup must not stop the run; it stays retryable
                    session.rollback()
                    org.maps_status = "failed"
                    counts["failed"] += 1
                session.commit()
        finally:
            if browser:
                browser.__exit__(None, None, None)
    return counts


if __name__ == "__main__":
    from app.db import SessionLocal

    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--state")
    a = ap.parse_args()
    print(run(SessionLocal, limit=a.limit, state=a.state))
