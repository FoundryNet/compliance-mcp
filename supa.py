"""Supabase PostgREST client for compliance-mcp (standalone project)."""
from __future__ import annotations

import logging
from typing import Optional

import config
from http_util import request_json

logger = logging.getLogger("comp.supa")


def configured() -> bool:
    return bool(config.SUPABASE_URL and config.SUPABASE_SERVICE_KEY)


def _headers(extra: Optional[dict] = None) -> dict:
    h = {"apikey": config.SUPABASE_SERVICE_KEY,
         "Authorization": f"Bearer {config.SUPABASE_SERVICE_KEY}",
         "Content-Type": "application/json", "Accept": "application/json"}
    if extra:
        h.update(extra)
    return h


def _url(path: str) -> str:
    return f"{config.SUPABASE_URL}/rest/v1/{path}"


async def select(table: str, params: dict) -> list:
    if not configured():
        return []
    r = await request_json("GET", _url(table), headers=_headers(), params=params,
                           timeout=config.REQUEST_TIMEOUT)
    return r if isinstance(r, list) else []


async def rpc(fn: str, body: dict):
    if not configured():
        return None
    return await request_json("POST", _url(f"rpc/{fn}"), headers=_headers(), body=body,
                              timeout=config.REQUEST_TIMEOUT)


async def upsert(rows: list) -> dict:
    if not configured() or not rows:
        return {"data": []}
    # dedup on (source, document_number) + union keys for PostgREST bulk insert
    seen, deduped = set(), []
    for r in rows:
        k = (r.get("source"), r.get("document_number"))
        if k in seen or not r.get("document_number"):
            continue
        seen.add(k)
        deduped.append(r)
    allkeys = set()
    for r in deduped:
        allkeys.update(r.keys())
    deduped = [{k: r.get(k) for k in allkeys} for r in deduped]
    written = 0
    for i in range(0, len(deduped), 500):
        r = await request_json("POST", _url("regulatory_updates"),
                               headers=_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
                               params={"on_conflict": "source,document_number"},
                               body=deduped[i:i + 500], timeout=max(config.REQUEST_TIMEOUT, 60))
        if isinstance(r, dict) and r.get("error"):
            logger.warning(f"upsert chunk {i}: {str(r)[:200]}")
        else:
            written += len(deduped[i:i + 500])
    return {"written": written}


async def upsert_table(table: str, rows: list, on_conflict: str) -> dict:
    """Generic merge-duplicates upsert for an arbitrary table (e.g. daily_briefs)."""
    if not configured() or not rows:
        return {"data": []}
    r = await request_json("POST", _url(table),
                           headers=_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
                           params={"on_conflict": on_conflict},
                           body=rows, timeout=max(config.REQUEST_TIMEOUT, 60))
    if isinstance(r, dict) and r.get("error"):
        return r
    return {"data": rows}


_FIELDS = ("id,source,title,summary,full_text_url,document_number,agency,sub_agency,"
           "jurisdiction,industry_tags,regulation_type,effective_date,comment_deadline,"
           "severity,penalty_amount,affected_products,published_date,created_at")


def _apply_common(p: dict, industry=None, agency=None, regulation_type=None,
                  keyword=None, severity=None, source=None):
    if industry:
        p["industry_tags"] = f'cs.["{industry}"]'
    if agency:
        p["agency"] = f"ilike.*{agency}*"
    if regulation_type:
        p["regulation_type"] = f"eq.{regulation_type}"
    if severity:
        p["severity"] = f"eq.{severity}"
    if source:
        p["source"] = f"eq.{source}"
    if keyword:
        kw = keyword.replace("*", "").replace(",", " ")
        p["or"] = f"(title.ilike.*{kw}*,summary.ilike.*{kw}*)"


async def search(*, industry=None, agency=None, regulation_type=None, keyword=None,
                 severity=None, days_from=None, limit=50) -> list:
    p = {"select": _FIELDS, "order": "published_date.desc.nullslast",
         "limit": str(min(max(int(limit or 50), 1), 200))}
    _apply_common(p, industry, agency, regulation_type, keyword, severity)
    if days_from:
        p["published_date"] = f"gte.{days_from}"
    return await select("regulatory_updates", p)


async def alerts(industry, severity=None, limit=100) -> list:
    p = {"select": _FIELDS, "limit": str(limit),
         "order": "comment_deadline.asc.nullslast"}
    if severity:
        p["severity"] = f"eq.{severity}"
    else:
        p["severity"] = "in.(action_required,critical)"
    if industry:
        p["industry_tags"] = f'cs.["{industry}"]'
    return await select("regulatory_updates", p)


async def recalls(*, product=None, company=None, category=None, days_from=None, limit=100) -> list:
    p = {"select": _FIELDS, "regulation_type": "eq.recall",
         "order": "published_date.desc.nullslast", "limit": str(limit)}
    if company:
        p["agency"] = f"ilike.*{company}*"  # firm stored in agency for recalls
    if product or category:
        kw = (product or category).replace("*", "")
        p["or"] = f"(title.ilike.*{kw}*,summary.ilike.*{kw}*)"
    if days_from:
        p["published_date"] = f"gte.{days_from}"
    return await select("regulatory_updates", p)


async def enforcement(*, agency=None, company=None, industry=None, min_penalty=None, limit=100) -> list:
    p = {"select": _FIELDS, "regulation_type": "eq.enforcement",
         "order": "penalty_amount.desc.nullslast", "limit": str(limit)}
    if agency:
        p["agency"] = f"ilike.*{agency}*"
    if industry:
        p["industry_tags"] = f'cs.["{industry}"]'
    if min_penalty is not None:
        p["penalty_amount"] = f"gte.{min_penalty}"
    if company:
        p["or"] = f"(title.ilike.*{company}*,summary.ilike.*{company}*)"
    return await select("regulatory_updates", p)


async def deadlines(*, industry=None, date_to=None, limit=100) -> list:
    p = {"select": _FIELDS, "comment_deadline": f"gte.{_today()}",
         "order": "comment_deadline.asc", "limit": str(limit)}
    if date_to:
        p["and"] = f"(comment_deadline.gte.{_today()},comment_deadline.lte.{date_to})"
        p.pop("comment_deadline", None)
    if industry:
        p["industry_tags"] = f'cs.["{industry}"]'
    return await select("regulatory_updates", p)


async def digest_rows(*, industry=None, jurisdiction=None, days_from=None, limit=200) -> list:
    p = {"select": _FIELDS, "order": "published_date.desc.nullslast", "limit": str(limit)}
    if industry:
        p["industry_tags"] = f'cs.["{industry}"]'
    if jurisdiction:
        p["jurisdiction"] = f"eq.{jurisdiction}"
    if days_from:
        p["published_date"] = f"gte.{days_from}"
    return await select("regulatory_updates", p)


def _today() -> str:
    import time
    return time.strftime("%Y-%m-%d", time.gmtime())


# ── free-tier + payments ──────────────────────────────────────────────────────
async def claim_free_query(agent_key: str, day: str, cap: int) -> Optional[dict]:
    r = await rpc("comp_claim_free_query", {"p_agent_key": agent_key, "p_day": day, "p_cap": cap})
    if isinstance(r, dict) and "allowed" in r:
        return r
    if isinstance(r, list) and r and isinstance(r[0], dict):
        return r[0]
    return None


async def payment_tx_used(tx_signature: str) -> bool:
    rows = await select("comp_payments", {"tx_signature": f"eq.{tx_signature}",
                                          "select": "tx_signature", "limit": "1"})
    return bool(rows)


async def insert_payment(row: dict) -> dict:
    if not configured():
        return {"error": "not_configured"}
    r = await request_json("POST", _url("comp_payments"),
                           headers=_headers({"Prefer": "return=minimal"}),
                           body=row, timeout=config.REQUEST_TIMEOUT)
    if isinstance(r, dict) and r.get("error"):
        return r
    return {"data": [row]}
