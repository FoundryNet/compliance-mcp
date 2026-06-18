"""Shared logic behind the MCP tools + REST routes: 7 operations + x402 gating.
mint_info is free; the rest run payment_gate.precheck(price) first.
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

import config
import payment_gate
import supa

logger = logging.getLogger("comp.core")


def _days_ago(n):
    return (datetime.now(timezone.utc) - timedelta(days=int(n))).strftime("%Y-%m-%d")


def _days_ahead(n):
    return (datetime.now(timezone.utc) + timedelta(days=int(n))).strftime("%Y-%m-%d")


def _billing(d):
    g = d.get("gate")
    if g == "free":
        cap, cnt = d.get("cap"), d.get("count")
        return {"tier": "free", "used_today": cnt, "daily_free": cap,
                "remaining_today": (cap - cnt) if (cap is not None and cnt is not None) else None}
    if g == "paid":
        return {"tier": "paid", "charged_usdc": d.get("amount_usdc")}
    if g == "api_key":
        return {"tier": "api_key", "note": "billed to your Forge account"}
    return {"tier": "free", "note": "gating inert"}


async def do_search(filters, *, agent_key, payment_tx=None, api_key=None):
    params = {k: v for k, v in (filters or {}).items() if v not in (None, "")}
    dec = await payment_gate.precheck("search_regulations", params, config.PRICE_SEARCH,
                                      agent_key, payment_tx, api_key)
    if dec["gate"] == "blocked":
        return dec["body"]
    days_back = params.pop("days_back", None)
    rows = await supa.search(days_from=_days_ago(days_back) if days_back else None, **params)
    return {"results": rows, "count": len(rows), "billing": _billing(dec)}


async def do_alerts(industry, severity, *, agent_key, payment_tx=None, api_key=None):
    if not industry:
        return {"error": "bad_request", "detail": "industry is required"}
    dec = await payment_gate.precheck("compliance_alerts", {"industry": industry, "severity": severity},
                                      config.PRICE_ALERTS, agent_key, payment_tx, api_key)
    if dec["gate"] == "blocked":
        return dec["body"]
    rows = await supa.alerts(industry, severity)
    return {"industry": industry, "count": len(rows),
            "alerts": rows, "note": "sorted by comment-deadline urgency; action_required + critical",
            "billing": _billing(dec)}


async def do_recall(product, company, category, days_back, *, agent_key, payment_tx=None, api_key=None):
    params = {k: v for k, v in {"product": product, "company": company, "category": category,
                                "days_back": days_back}.items() if v}
    dec = await payment_gate.precheck("recall_check", params, config.PRICE_RECALL,
                                      agent_key, payment_tx, api_key)
    if dec["gate"] == "blocked":
        return dec["body"]
    rows = await supa.recalls(product=product, company=company, category=category,
                              days_from=_days_ago(days_back) if days_back else None)
    return {"results": rows, "count": len(rows), "billing": _billing(dec)}


async def do_enforcement(agency, company, industry, min_penalty, *, agent_key, payment_tx=None, api_key=None):
    params = {k: v for k, v in {"agency": agency, "company": company, "industry": industry,
                                "min_penalty": min_penalty}.items() if v not in (None, "")}
    dec = await payment_gate.precheck("enforcement_actions", params, config.PRICE_ENFORCEMENT,
                                      agent_key, payment_tx, api_key)
    if dec["gate"] == "blocked":
        return dec["body"]
    rows = await supa.enforcement(agency=agency, company=company, industry=industry, min_penalty=min_penalty)
    return {"results": rows, "count": len(rows),
            "note": "enforcement notices w/ parsed penalties (Federal Register). SEC/EPA/OSHA penalty feeds are a planned source.",
            "billing": _billing(dec)}


async def do_deadlines(industry, days_ahead, *, agent_key, payment_tx=None, api_key=None):
    dec = await payment_gate.precheck("comment_deadlines", {"industry": industry, "days_ahead": days_ahead},
                                      config.PRICE_DEADLINES, agent_key, payment_tx, api_key)
    if dec["gate"] == "blocked":
        return dec["body"]
    days = min(max(int(days_ahead or 30), 1), 365)
    rows = await supa.deadlines(industry=industry, date_to=_days_ahead(days))
    return {"industry": industry, "window_days": days, "count": len(rows),
            "deadlines": [{"title": r.get("title"), "agency": r.get("agency"),
                           "comment_deadline": r.get("comment_deadline"),
                           "document_number": r.get("document_number"),
                           "url": r.get("full_text_url")} for r in rows],
            "billing": _billing(dec)}


async def do_digest(industry, jurisdiction, *, agent_key, payment_tx=None, api_key=None):
    params = {k: v for k, v in {"industry": industry, "jurisdiction": jurisdiction}.items() if v}
    dec = await payment_gate.precheck("daily_digest", params, config.PRICE_DIGEST,
                                      agent_key, payment_tx, api_key)
    if dec["gate"] == "blocked":
        return dec["body"]
    rows = await supa.digest_rows(industry=industry, jurisdiction=jurisdiction,
                                  days_from=_days_ago(2))
    by_sev, by_type = Counter(), Counter()
    for r in rows:
        by_sev[r.get("severity")] += 1
        by_type[r.get("regulation_type")] += 1
    buckets = {s: [] for s in ("critical", "action_required", "warning", "info")}
    for r in rows:
        buckets.setdefault(r.get("severity"), []).append({
            "title": r.get("title"), "source": r.get("source"), "agency": r.get("agency"),
            "regulation_type": r.get("regulation_type"), "url": r.get("full_text_url"),
            "comment_deadline": r.get("comment_deadline")})
    return {"date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "filters": {"industry": industry, "jurisdiction": jurisdiction},
            "total_new": len(rows), "by_severity": dict(by_sev), "by_type": dict(by_type),
            "by_severity_detail": {k: v[:25] for k, v in buckets.items() if v},
            "billing": _billing(dec)}


def mint_info():
    return {
        "network": "FoundryNet Data Network",
        "message": "Attest your agent's compliance/regulatory analysis with MINT Protocol for verifiable proof.",
        "mint_protocol": {"mcp_endpoint": config.MINT_MCP_URL, "info_url": config.MINT_INFO_URL,
                          "tools": ["mint_register", "mint_attest", "mint_verify",
                                    "mint_rate", "mint_recommend", "mint_discover"]},
        "see_also": config.SISTER_SERVERS,
    }
