"""Versioned fit score. Pure: no database, no settings."""
import json
from dataclasses import dataclass
from pathlib import Path

from app.sources.npi_registry import NormalizedLead, digits


@dataclass
class ScoreResult:
    total: int
    priority: str
    components: dict[str, dict]
    config_version: str


def load_config(path: str | None = None) -> dict:
    p = Path(path) if path else Path(__file__).resolve().parents[2] / "scoring_config.json"
    return json.loads(p.read_text(encoding="utf-8"))


def priority_for(total: int, config: dict) -> str:
    t = config["priority_thresholds"]
    return "critical" if total >= t["critical"] else "high" if total >= t["high"] else "medium" if total >= t["medium"] else "low"


def score(lead: NormalizedLead, config: dict, *, staff_with_title: bool = False, email_found: bool = False) -> ScoreResult:
    pts, mx = config["points"], config["max"]
    code = lead.primary_taxonomy_code
    hospital = lead.organization_type == "hospital" or bool(code and code.startswith(config["hospital_prefix"]))
    core = code in config["core_taxonomy_codes"]
    sub = bool(code) and not core and code.startswith(tuple(config["subspecialty_prefixes"]))
    solo = lead.organization_type == "solo_provider"
    c = lead.contact or {}

    def comp(key: str, points: int, reason: str) -> dict:
        return {"points": points, "max": mx[key], "reason": reason}

    if not code:
        spec = comp("specialty", 0, "no primary taxonomy")
        svc = comp("service_fit", 0, "no primary taxonomy")
    elif core:
        spec = comp("specialty", pts["specialty"]["core"], f"core primary care taxonomy {code}")
        svc = comp("service_fit", pts["service_fit"]["core"], "core specialty fits care management and billing services")
    elif sub:
        spec = comp("specialty", pts["specialty"]["subspecialty"], f"internal medicine or family medicine subspecialty {code}")
        svc = comp("service_fit", pts["service_fit"]["hospital" if hospital else "other"], "subspecialty, partial service fit")
    else:
        spec = comp("specialty", pts["specialty"]["other"], f"non-core taxonomy {code}")
        svc = comp("service_fit", pts["service_fit"]["hospital" if hospital else "other"],
                   "hospital taxonomy, lower service fit" if hospital else "non-core taxonomy, partial service fit")

    kind = "hospital" if hospital else lead.organization_type
    ind_reason = {"practice": "organization record, size unknown from this source",
                  "solo_provider": "self-reported sole proprietor",
                  "subpart": f"subpart of {lead.parent_organization_name or 'a larger organization'}",
                  "hospital": "hospital or health system"}[kind]
    ind = comp("independence", pts["independence"][kind], ind_reason)

    contact = comp("contactability", pts["contactability"]["phone"] if lead.phone else 0,
                   "practice phone present" if lead.phone else "no practice phone")

    dp = pts["decision_maker"]
    named = bool(c.get("first_name") or c.get("last_name"))
    direct = bool(c.get("phone")) and digits(c["phone"]) != digits(lead.phone)  # the office line reaches a receptionist, not the decision-maker
    if solo:
        dm = comp("decision_maker", dp["solo_provider"], "solo doctor is their own decision-maker")
    elif staff_with_title and not (named and c.get("title")):
        who, reach = "named staff member with title found on practice website", email_found
        dm = comp("decision_maker", dp["staff_with_title"] + dp["reachable"] * reach,
                  who + (", email found" if reach else ", no direct way to reach them yet"))
    elif named and c.get("title"):
        reach = direct or email_found
        how = "direct phone" if direct else "email found"
        dm = comp("decision_maker", dp["name_and_title"] + dp["reachable"] * reach,
                  "authorized official with name and title, " + (how if reach else "only the office line to reach them"))
    elif named:
        dm = comp("decision_maker", dp["name_only"], "authorized official with name only")
    else:
        dm = comp("decision_maker", 0, "no decision-maker identified")

    if lead.practice_location_count >= 1:
        ml = comp("multi_location", pts["multi_location"]["multiple"],
                  f"{lead.practice_location_count} extra practice location(s) listed")
    else:
        ml = comp("multi_location", 0, "provider count not available from this source")

    components = {"specialty": spec, "independence": ind, "service_fit": svc,
                  "contactability": contact, "decision_maker": dm, "multi_location": ml}
    total = sum(v["points"] for v in components.values())
    return ScoreResult(total, priority_for(total, config), components, config["version"])
