"""Recompute every lead's fit score from its stored raw source record: python -m app.rescore"""
from sqlalchemy import select

from app.models import Organization, SourceRecord
from app.services.leads import save_score
from app.services.scoring import load_config, score
from app.sources.npi_registry import normalize

BATCH = 200


def rescore_all(session_factory, config_path: str | None = None) -> int:
    config = load_config(config_path)
    done = skipped = 0
    with session_factory() as session:
        ids = list(session.scalars(select(Organization.id).order_by(Organization.id)))
        for i in range(0, len(ids), BATCH):
            for org in session.scalars(select(Organization).where(Organization.id.in_(ids[i:i + BATCH]))):
                rec = session.scalars(select(SourceRecord).where(SourceRecord.organization_id == org.id)
                                      .order_by(SourceRecord.collected_at.desc()).limit(1)).first()
                if rec is None:
                    skipped += 1
                    continue
                save_score(session, org, score(normalize(rec.raw), config))
                done += 1
            session.commit()
    if skipped:
        print(f"skipped {skipped} organization(s) without a source record")
    return done


if __name__ == "__main__":
    from app.db import SessionLocal

    print(f"rescored {rescore_all(SessionLocal)} leads")
