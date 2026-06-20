"""Daily curated brief — compliance.

Runs once a day at BRIEF_HOUR_UTC (05:00 UTC) as an in-process background task
(same shape as the aggregation loop). It queries the last 24h of regulatory
updates, packages the most significant items (new final rules, near-term comment
deadlines, recalls, and large enforcement actions), attests the package through
MINT for verifiable provenance, and upserts it into the `daily_briefs` table. The
paid `daily_brief` tool just reads that row back.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import config
import mint_integration
import supa

logger = logging.getLogger("comp.curator")

SERVER = config.SERVER_SLUG
PRICE = config.PRICE_DAILY_BRIEF


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _expires_at(date_str: str) -> str:
    d = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return (d + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")


def related_briefs(exclude: str) -> list:
    return [{"server": s, "price": p, "tool": "daily_brief"}
            for s, p in config.NETWORK_BRIEFS.items() if s != exclude]


_FIELDS = ("source,title,summary,full_text_url,document_number,agency,jurisdiction,"
           "industry_tags,regulation_type,effective_date,comment_deadline,severity,"
           "penalty_amount,published_date,created_at")


async def _curate_signals(since_iso: str) -> tuple[dict, int]:
    """Build the compliance brief body from the last 24h. Returns (signals, count)."""
    today = _today()
    deadline_to = (datetime.now(timezone.utc) + timedelta(days=14)).strftime("%Y-%m-%d")

    # New final rules (Federal Register) in the last 24h.
    fr_rows = await supa.select("regulatory_updates", {
        "select": _FIELDS, "regulation_type": "eq.final_rule",
        "created_at": f"gte.{since_iso}",
        "order": "published_date.desc.nullslast", "limit": "25"})
    new_final_rules = [{"title": r.get("title"), "agency": r.get("agency"),
                        "document_number": r.get("document_number"),
                        "effective_date": r.get("effective_date"),
                        "url": r.get("full_text_url")} for r in fr_rows]

    # Open comment periods with deadlines in the next 14 days.
    dl_rows = await supa.select("regulatory_updates", {
        "select": _FIELDS,
        "and": f"(comment_deadline.gte.{today},comment_deadline.lte.{deadline_to})",
        "order": "comment_deadline.asc", "limit": "25"})
    comment_deadlines = [{"title": r.get("title"), "agency": r.get("agency"),
                          "comment_deadline": r.get("comment_deadline"),
                          "document_number": r.get("document_number"),
                          "url": r.get("full_text_url")} for r in dl_rows]

    # Recalls (openFDA / CPSC) in the last 24h.
    rc_rows = await supa.select("regulatory_updates", {
        "select": _FIELDS, "regulation_type": "eq.recall",
        "created_at": f"gte.{since_iso}",
        "order": "published_date.desc.nullslast", "limit": "25"})
    recalls = [{"title": r.get("title"), "source": r.get("source"),
                "agency": r.get("agency"), "severity": r.get("severity"),
                "url": r.get("full_text_url")} for r in rc_rows]

    # Enforcement actions above $50K.
    enf_rows = await supa.select("regulatory_updates", {
        "select": _FIELDS, "regulation_type": "eq.enforcement",
        "penalty_amount": "gte.50000",
        "order": "penalty_amount.desc.nullslast", "limit": "25"})
    enforcement_actions = [{"title": r.get("title"), "agency": r.get("agency"),
                            "penalty_amount": r.get("penalty_amount"),
                            "document_number": r.get("document_number"),
                            "url": r.get("full_text_url")} for r in enf_rows]

    signals = {
        "new_final_rules": new_final_rules,
        "comment_deadlines": comment_deadlines,
        "recalls": recalls,
        "enforcement_actions": enforcement_actions,
    }
    count = (len(new_final_rules) + len(comment_deadlines)
             + len(recalls) + len(enforcement_actions))
    return signals, count


async def run_curation(date_str: str | None = None) -> dict:
    """Generate, attest, and store today's brief. Idempotent per date (upsert)."""
    date_str = date_str or _today()
    since_iso = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S")
    signals, count = await _curate_signals(since_iso)

    brief = {
        "brief_date": date_str, "server": SERVER, "signal_count": count,
        "signals": signals, "expires_at": _expires_at(date_str),
        "related_briefs": related_briefs(SERVER),
    }
    # Attest for provenance (sync httpx → run off the event loop; fail-open).
    attestation = await asyncio.to_thread(
        mint_integration.attest_data, brief, "analysis",
        f"Daily {SERVER} brief: {count} signals")
    brief["provenance"] = attestation

    row = {
        "brief_date": date_str, "brief_data": brief, "signal_count": count,
        "attestation_hash": attestation.get("attestation_hash"),
        "expires_at": _expires_at(date_str),
    }
    res = await supa.upsert_table("daily_briefs", [row], "brief_date")
    if isinstance(res, dict) and res.get("error"):
        logger.warning(f"daily brief upsert failed: {str(res)[:200]}")
    else:
        logger.info(f"daily brief stored: {date_str} ({count} signals, "
                    f"attested={attestation.get('mint_verified')})")
    return brief


async def get_brief(date_str: str | None = None) -> dict | None:
    """Read a stored brief; None if missing or expired."""
    date_str = date_str or _today()
    rows = await supa.select("daily_briefs",
                             {"select": "*", "brief_date": f"eq.{date_str}", "limit": "1"})
    if not rows:
        return None
    row = rows[0]
    exp = row.get("expires_at")
    if exp:
        try:
            if datetime.now(timezone.utc) >= datetime.fromisoformat(exp.replace("Z", "+00:00")):
                return None
        except Exception:  # noqa: BLE001
            pass
    return row.get("brief_data")


async def bump_purchase(date_str: str) -> None:
    """Best-effort purchase counter via RPC (no-op if the function is absent)."""
    try:
        await supa.rpc("increment_brief_purchase", {"p_brief_date": date_str})
    except Exception:  # noqa: BLE001
        pass


async def curator_loop() -> None:
    """Sleep until BRIEF_HOUR_UTC each day, then curate. Cancellable."""
    while True:
        now = datetime.now(timezone.utc)
        secs = now.hour * 3600 + now.minute * 60 + now.second
        wait = (config.BRIEF_HOUR_UTC * 3600 - secs) % 86400 or 86400
        try:
            await asyncio.sleep(wait)
            if supa.configured():
                await run_curation()
        except asyncio.CancelledError:
            break
        except Exception as e:  # noqa: BLE001
            logger.warning(f"curator loop error: {e}")
            await asyncio.sleep(3600)
