"""Enrich leads that are already saved: python -m app.enrich_existing --limit 10 [--state TX] [--priority critical]

Picks the best-scored leads not enriched yet, links them to a new search job (it shows in the Searches list)
and runs the normal enrichment pass on them. Uses your search API key, one query per lead.
"""
import argparse
from collections import Counter

from sqlalchemy import select

from app.models import Organization, SearchJob, SearchJobLead
from app.services.search import run_job


def enrich_existing(session_factory, *, limit: int, state: str | None = None, priority: str | None = None) -> SearchJob | None:
    with session_factory() as session:
        stmt = select(Organization).where(Organization.enrichment_status.in_(("not_run", "failed")), Organization.website.is_(None))
        if state:
            stmt = stmt.where(Organization.state == state.upper())
        if priority:
            stmt = stmt.where(Organization.priority == priority)
        orgs = session.scalars(stmt.order_by(Organization.fit_score.desc().nulls_last(), Organization.id).limit(limit)).all()
        if not orgs:
            return None
        job = SearchJob(specialty="Enrich existing leads", state=Counter(o.state for o in orgs).most_common(1)[0][0],
                        target_count=len(orgs), include_practices=False, include_solo=False,
                        sources=["npi_registry"], enrich=True)
        session.add(job)
        session.flush()
        session.add_all(SearchJobLead(search_job_id=job.id, organization_id=o.id, was_new=False) for o in orgs)
        session.commit()
        job_id = job.id
    run_job(session_factory, job_id)
    with session_factory() as session:
        return session.get(SearchJob, job_id)


if __name__ == "__main__":
    from app.db import SessionLocal

    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--state")
    ap.add_argument("--priority", choices=["critical", "high", "medium", "low"])
    a = ap.parse_args()
    done = enrich_existing(SessionLocal, limit=a.limit, state=a.state, priority=a.priority)
    print("nothing to enrich" if done is None else f"job {done.id}: {done.status} {done.counters} {done.error or ''}")
