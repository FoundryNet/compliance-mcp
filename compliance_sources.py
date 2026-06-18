"""Free, keyless regulatory sources + classification.

Live sources: Federal Register (rules/proposed/notices/presidential), openFDA
enforcement (food/drug/device recalls), CPSC (consumer product recalls). Each
record is classified by industry (keyword taxonomy) and assigned a severity.
Enforcement-with-penalty rows are derived from Federal Register notices (penalty
parsed from text). EPA ECHO / OSHA / SEC are documented future sources (their
public endpoints need multi-step queries or scraping).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import config
from http_util import request_json

logger = logging.getLogger("comp.src")

_UA = {"User-Agent": config.SOURCE_USER_AGENT, "Accept": "application/json"}

# ── industry taxonomy ─────────────────────────────────────────────────────────
TAXONOMY = {
    "healthcare": ["hospital", "health care", "healthcare", "medicare", "medicaid", "clinical", "patient", "provider", "medical device", "physician"],
    "pharma": ["drug", "pharmaceutical", "biologic", "clinical trial", "prescription", "compounding", "gmp", "vaccine", "active ingredient"],
    "finance": ["securities", "bank", "investment", "financial", "lending", "credit union", "broker", "fintech", "insurance", "mortgage", "consumer financial"],
    "manufacturing": ["manufacturing", "factory", "industrial", "machinery", "equipment", "fabrication"],
    "food": ["food", "beverage", "allergen", "contamination", "listeria", "salmonella", "e. coli", "dietary supplement", "produce", "meat", "poultry"],
    "consumer_products": ["consumer product", "toy", "appliance", "children's product", "household", "furniture", "cosmetic"],
    "energy": ["energy", "oil", "natural gas", "petroleum", "electric", "utility", "nuclear", "renewable", "pipeline", "emissions"],
    "technology": ["technology", "software", "data privacy", "cybersecurity", "telecommunications", "semiconductor", "artificial intelligence", "broadband"],
    "construction": ["construction", "building code", "contractor", "workplace safety", "scaffolding"],
    "transportation": ["transportation", "aviation", "airline", "railroad", "motor vehicle", "trucking", "maritime", "aircraft", "highway"],
    "agriculture": ["agriculture", "farm", "crop", "livestock", "pesticide", "grain", "irrigation"],
    "defense": ["defense", "military", "weapon", "national security", "munitions", "arms export"],
}


def classify_industries(text: str) -> list:
    t = (text or "").lower()
    tags = [ind for ind, kws in TAXONOMY.items() if any(k in t for k in kws)]
    return tags or ["general"]


_INJURY = ("death", "died", "fatal", "injur", "laceration", "burn", "fire hazard",
           "choking", "amputation", "hospitaliz", "serious adverse", "life-threatening")
_PENALTY_RE = re.compile(r"\$\s?([\d,]+(?:\.\d+)?)\s*(billion|million|thousand)?", re.I)
_ENFORCE_KW = ("civil penalty", "settlement", "consent decree", "enforcement action",
               "fine", "penalty", "violation", "cease and desist", "disgorgement")


def parse_penalty(text: str):
    if not text:
        return None
    m = _PENALTY_RE.search(text)
    if not m:
        return None
    try:
        n = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    mult = {"billion": 1e9, "million": 1e6, "thousand": 1e3}.get((m.group(2) or "").lower(), 1)
    return n * mult


def _date(s):
    if not s:
        return None
    return str(s)[:10]


def _within_days(date_str, days):
    try:
        d = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
        return 0 <= (d - datetime.now(timezone.utc)).days <= days
    except Exception:  # noqa: BLE001
        return False


# ── Federal Register ──────────────────────────────────────────────────────────
_FR_TYPE = {"Rule": "final_rule", "Proposed Rule": "proposed_rule",
            "Notice": "notice", "Presidential Document": "guidance"}


async def fetch_federal_register(date_from: str, max_pages=5) -> list:
    rows = []
    for page in range(1, max_pages + 1):
        # httpx encodes repeated fields[] from the param tuple list in _fr_params.
        r = await request_json("GET", config.FEDERAL_REGISTER, headers=_UA,
                               params=_fr_params(date_from, page), timeout=config.REQUEST_TIMEOUT)
        if not isinstance(r, dict) or "results" not in r:
            break
        for doc in r["results"]:
            rows.append(_map_fr(doc))
        if page >= (r.get("total_pages") or 1):
            break
    logger.info(f"federal_register: {len(rows)} docs since {date_from}")
    return [x for x in rows if x]


def _fr_params(date_from, page):
    # httpx encodes list values as repeated keys.
    return [
        ("conditions[publication_date][gte]", date_from),
        ("per_page", "100"), ("page", str(page)), ("order", "newest"),
        ("fields[]", "title"), ("fields[]", "abstract"), ("fields[]", "document_number"),
        ("fields[]", "html_url"), ("fields[]", "type"), ("fields[]", "publication_date"),
        ("fields[]", "effective_on"), ("fields[]", "comments_close_on"),
        ("fields[]", "agencies"), ("fields[]", "action"),
    ]


def _map_fr(doc: dict) -> dict:
    title = doc.get("title") or ""
    abstract = doc.get("abstract") or ""
    text = f"{title} {abstract} {doc.get('action') or ''}"
    agencies = doc.get("agencies") or []
    agency = (agencies[0].get("name") if agencies and isinstance(agencies[0], dict) else None)
    rtype = _FR_TYPE.get(doc.get("type"), "notice")
    eff = _date(doc.get("effective_on"))
    cdl = _date(doc.get("comments_close_on"))
    penalty = None
    # Enforcement-flavored notices → reclassify + parse penalty.
    if rtype == "notice" and any(k in text.lower() for k in _ENFORCE_KW):
        p = parse_penalty(text)
        if p:
            rtype = "enforcement"
            penalty = p
    # severity
    low = text.lower()
    if "emergency" in low or "immediate" in low and rtype == "final_rule":
        sev = "critical"
    elif rtype == "final_rule" and eff and _within_days(eff, 90):
        sev = "action_required"
    elif rtype == "enforcement" and penalty and penalty > 100_000:
        sev = "action_required"
    elif rtype == "proposed_rule" and cdl:
        sev = "warning"
    else:
        sev = "info"
    return {
        "source": "federal_register", "title": title[:500], "summary": abstract[:500],
        "full_text_url": doc.get("html_url"), "document_number": doc.get("document_number"),
        "agency": agency, "jurisdiction": "federal",
        "industry_tags": classify_industries(text), "regulation_type": rtype,
        "effective_date": eff, "comment_deadline": cdl, "severity": sev,
        "penalty_amount": penalty, "published_date": _date(doc.get("publication_date")),
    }


# ── openFDA enforcement (recalls) ─────────────────────────────────────────────
async def fetch_fda(date_from: str) -> list:
    rows = []
    df = date_from.replace("-", "")
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    for cat in ("food", "drug", "device"):
        url = f"{config.OPENFDA}/{cat}/enforcement.json"
        params = {"search": f"report_date:[{df} TO {today}]", "limit": "100"}
        r = await request_json("GET", url, headers=_UA, params=params, timeout=config.REQUEST_TIMEOUT)
        results = r.get("results") if isinstance(r, dict) else None
        if not results:
            continue
        for rec in results:
            rows.append(_map_fda(rec, cat))
    logger.info(f"openFDA: {len(rows)} enforcement/recall records since {date_from}")
    return [x for x in rows if x]


def _map_fda(rec: dict, cat: str) -> dict:
    desc = rec.get("product_description") or ""
    reason = rec.get("reason_for_recall") or ""
    klass = rec.get("classification") or ""
    text = f"{desc} {reason}"
    if klass.lower().startswith("class i") or any(k in text.lower() for k in _INJURY):
        sev = "critical"
    elif klass.lower().startswith("class ii"):
        sev = "warning"
    else:
        sev = "info"
    base_ind = {"food": "food", "drug": "pharma", "device": "healthcare"}[cat]
    inds = list({base_ind, *classify_industries(text)})
    num = rec.get("recall_number") or rec.get("event_id")
    return {
        "source": "fda", "title": (desc[:200] or reason[:200] or "FDA recall"),
        "summary": reason[:500],
        "full_text_url": f"{config.OPENFDA}/{cat}/enforcement.json?search=recall_number:{num}",
        "document_number": str(num) if num else None,
        "agency": rec.get("recalling_firm"), "jurisdiction": "federal",
        "industry_tags": inds, "regulation_type": "recall",
        "severity": sev, "affected_products": [desc] if desc else None,
        "published_date": _date_fda(rec.get("report_date")),
    }


def _date_fda(s):
    if s and len(s) == 8:
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return _date(s)


# ── CPSC recalls ──────────────────────────────────────────────────────────────
async def fetch_cpsc(date_from: str) -> list:
    params = {"format": "json", "RecallDateStart": date_from}
    r = await request_json("GET", config.CPSC, headers=_UA, params=params, timeout=config.REQUEST_TIMEOUT)
    if not isinstance(r, list):
        return []
    rows = [_map_cpsc(rec) for rec in r]
    logger.info(f"CPSC: {len(rows)} recalls since {date_from}")
    return [x for x in rows if x]


def _map_cpsc(rec: dict) -> dict:
    title = rec.get("Title") or ""
    desc = rec.get("Description") or ""
    hazards = " ".join(h.get("Name", "") for h in (rec.get("Hazards") or []))
    injuries = " ".join(i.get("Name", "") for i in (rec.get("Injuries") or []))
    text = f"{title} {desc} {hazards} {injuries}"
    sev = "critical" if (rec.get("Injuries") or any(k in text.lower() for k in _INJURY)) else "warning"
    products = [p.get("Name") for p in (rec.get("Products") or []) if p.get("Name")]
    manus = [m.get("Name") for m in (rec.get("Manufacturers") or []) if m.get("Name")]
    inds = list({"consumer_products", *classify_industries(text)})
    return {
        "source": "cpsc", "title": title[:500], "summary": desc[:500],
        "full_text_url": rec.get("URL"),
        "document_number": str(rec.get("RecallNumber") or rec.get("RecallID")),
        "agency": (manus[0] if manus else "CPSC"), "jurisdiction": "federal",
        "industry_tags": inds, "regulation_type": "recall", "severity": sev,
        "affected_products": products or None, "published_date": _date(rec.get("RecallDate")),
    }
