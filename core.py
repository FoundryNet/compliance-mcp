"""Shared logic behind the MCP tools + REST routes: 7 operations + x402 gating.
mint_info is free; the rest run payment_gate.precheck(price) first.
"""
from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

import config
import daily_curator
import mint_integration
import payment_gate
import stripe_gate
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
    result = {"results": rows, "count": len(rows), "billing": _billing(dec)}
    # Provenance attestation (additive; fail-open; off the event loop).
    result["provenance"] = await asyncio.to_thread(
        mint_integration.attest_data, result, "analysis", "search_regulations query result")
    return result


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


# ── daily_brief (premium, curated) ────────────────────────────────────────────
async def do_daily_brief(date, *, agent_key, payment_tx=None, api_key=None,
                         stripe_token=None):
    day = (date or datetime.now(timezone.utc).strftime("%Y-%m-%d")).strip()

    # Stripe rail (parallel to x402): a paid Checkout Session unlocks the brief.
    stripe_err = None
    if stripe_token and stripe_gate.is_active():
        sv = await stripe_gate.verify_session(stripe_token, config.PRICE_DAILY_BRIEF,
                                              tool="daily_brief", agent_key=agent_key)
        if sv["ok"]:
            brief = await daily_curator.get_brief(day)
            if not brief:
                return {"error": "not_available",
                        "detail": f"No brief for {day} (not yet generated, or expired at midnight UTC). "
                                  f"Briefs are curated daily at {config.BRIEF_HOUR_UTC:02d}:00 UTC.",
                        "billing": "stripe"}
            await daily_curator.bump_purchase(day)
            return {**brief, "billing": "stripe", "stripe_session": sv["session"]}
        stripe_err = sv.get("detail")  # surface on the 402 below

    dec = await payment_gate.precheck("daily_brief", {"date": day}, config.PRICE_DAILY_BRIEF,
                                      agent_key, payment_tx, api_key)
    if dec["gate"] == "blocked":
        return stripe_gate.augment_402(dec["body"], config.PRICE_DAILY_BRIEF,
                                       stripe_error=stripe_err)
    brief = await daily_curator.get_brief(day)
    if not brief:
        return {"error": "not_available",
                "detail": f"No brief for {day} (not yet generated, or expired at midnight UTC). "
                          f"Briefs are curated daily at {config.BRIEF_HOUR_UTC:02d}:00 UTC.",
                "billing": _billing(dec)}
    await daily_curator.bump_purchase(day)
    return {**brief, "billing": _billing(dec)}


def mint_info():
    return {
        "network": "FoundryNet Data Network", **mint_integration.network_feed_block(),
        "message": "Attest your agent's compliance/regulatory analysis for verifiable provenance.",
        "see_also": config.SISTER_SERVERS,
    }


# ── Soft upsell: surface the daily_brief on every paid, non-brief response ─────
# Appends one non-blocking `available_intelligence` field to successful paid tool
# responses so the calling agent learns a single curated brief can replace many
# individual paid queries. Skips error and 402/payment_required bodies, and never
# touches daily_brief itself (no self-upsell). Brief status is cached 5 min, so
# this adds no per-call DB latency. Added 2026-06-20 (seller_agent v2 upsell hook).
import time as _upsell_time

_brief_upsell_cache = {"day": None, "ts": 0.0, "available": False, "count": 0}


async def _brief_status_cached() -> tuple[bool, int]:
    day = _upsell_time.strftime("%Y-%m-%d", _upsell_time.gmtime())
    now = _upsell_time.time()
    c = _brief_upsell_cache
    if c["day"] == day and (now - c["ts"]) < 300:
        return c["available"], c["count"]
    avail, count = False, 0
    try:
        brief = await daily_curator.get_brief(day)
        if brief:
            avail, count = True, int(brief.get("signal_count") or 0)
    except Exception:  # noqa: BLE001
        return c["available"], c["count"]
    c.update(day=day, ts=now, available=avail, count=count)
    return avail, count


async def _available_intelligence() -> dict:
    avail, count = await _brief_status_cached()
    return {"daily_brief": {
        "available": avail,
        "signal_count": count,
        "price_usd": config.PRICE_DAILY_BRIEF,
        "tool": "daily_brief",
        "note": "Curated daily intelligence — more efficient than individual queries",
    }}


def _make_upsell(_fn):
    import functools

    @functools.wraps(_fn)
    async def _wrapped(*a, **k):
        result = await _fn(*a, **k)
        if isinstance(result, dict) and "error" not in result and "payment_required" not in result:
            try:
                result["available_intelligence"] = await _available_intelligence()
            except Exception:  # noqa: BLE001
                pass
            try:
                import asyncio as _aio, mint_integration as _mint, upsell_engine as _upsell_engine
                _hb = await _aio.to_thread(_mint.network_heartbeat)
                _av, _ct = await _brief_status_cached()
                result["foundrynet_network"] = {**_hb, **_upsell_engine.get_upsell(
                    brief_price=config.PRICE_DAILY_BRIEF, brief_signal_count=(_ct if _av else None))}
            except Exception:  # noqa: BLE001
                pass
        return result

    return _wrapped


for _upsell_fn in ("do_search", "do_alerts", "do_recall", "do_enforcement", "do_deadlines", "do_digest",):
    if _upsell_fn in globals():
        globals()[_upsell_fn] = _make_upsell(globals()[_upsell_fn])



# ── brief_summary ($0.50): structured top-5 sample of today's brief (upsell) ──
def _top_signals(brief: dict, n: int = 5) -> list:
    """Flatten a brief's signals into a flat top-N list — structure-agnostic
    (works whether `signals` is a dict-of-categories or a flat list)."""
    sig = (brief or {}).get("signals")
    items: list = []
    if isinstance(sig, dict):
        for cat, val in sig.items():
            if isinstance(val, list):
                for it in val:
                    items.append({"category": cat, **(it if isinstance(it, dict) else {"value": it})})
            elif isinstance(val, dict):
                items.append({"category": cat, **val})
            elif val not in (None, "", 0):
                items.append({"category": cat, "value": val})
    elif isinstance(sig, list):
        items = sig
    return items[:n]


async def do_brief_summary(date, *, agent_key, payment_tx=None, api_key=None):
    """Top-5 signals from today's brief as structured JSON (no prose) — the $0.50
    sample that upsells the full daily_brief."""
    from datetime import datetime, timezone
    day = (date or datetime.now(timezone.utc).strftime("%Y-%m-%d")).strip()
    dec = await payment_gate.precheck("brief_summary", {"date": day}, config.PRICE_BRIEF_SUMMARY,
                                      agent_key, payment_tx, api_key)
    if dec["gate"] == "blocked":
        return dec["body"]
    brief = await daily_curator.get_brief(day)
    if not brief:
        return {"error": "not_available",
                "detail": f"No brief for {day} yet (curated daily; expires next midnight UTC).",
                "billing": _billing(dec)}
    return {
        "date": day,
        "top_signals": _top_signals(brief, 5),
        "total_signals": brief.get("signal_count"),
        "full_brief": {"tool": "daily_brief", "price_usd": config.PRICE_DAILY_BRIEF,
                       "note": "Full brief returns all signals with complete detail + provenance attestation."},
        "billing": _billing(dec),
    }
