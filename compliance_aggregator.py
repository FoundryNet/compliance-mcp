#!/usr/bin/env python3
"""compliance_aggregator — every 12h. Fetches new regulatory entries from Federal
Register + openFDA + CPSC since the lookback window, classifies industry +
severity, dedups, and upserts into Supabase regulatory_updates.

The MCP server runs run_aggregation() in-process twice daily; manual entry point:
  python compliance_aggregator.py          # default lookback
  python compliance_aggregator.py 7        # last 7 days (backfill)
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone

import compliance_sources as src
import config
import supa

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("comp.agg")


async def run_aggregation(lookback_days: int | None = None) -> dict:
    days = lookback_days or config.LOOKBACK_DAYS
    date_from = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    log.info(f"aggregating regulatory updates since {date_from}")

    results = await asyncio.gather(
        src.fetch_federal_register(date_from),
        src.fetch_fda(date_from),
        src.fetch_cpsc(date_from),
        return_exceptions=True,
    )
    rows = []
    for r in results:
        if isinstance(r, Exception):
            log.warning(f"source error: {r}")
        else:
            rows.extend(r)

    res = await supa.upsert(rows)
    out = {"fetched": len(rows), "written": res.get("written", 0)}
    log.info(f"done: {out}")
    return out


async def main() -> None:
    args = [a for a in sys.argv[1:] if a.strip()]
    days = int(args[0]) if args and args[0].isdigit() else None
    print(await run_aggregation(days))


if __name__ == "__main__":
    asyncio.run(main())
