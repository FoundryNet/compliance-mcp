from typing import Optional

import core
import identity


def register(mcp) -> None:
    @mcp.tool
    async def daily_brief(
        date: Optional[str] = None,
        agent_id: Optional[str] = None,
        payment_tx: Optional[str] = None,
    ) -> dict:
        """Get the curated daily compliance brief — the day's most significant regulatory
        developments in one package: new final rules (Federal Register), open comment
        deadlines closing within 14 days, fresh recalls (openFDA & CPSC), and enforcement
        actions above $50K. Each brief carries a MINT provenance
        attestation so a buyer can verify it was produced by this server, unaltered.

        PAID: $10 USDC per brief. Defaults to today (UTC); a brief expires at the
        next midnight UTC. On a 402, pay the returned Solana memo and re-call with
        the SAME args plus payment_tx=<signature>. An Authorization: Bearer fnet_
        key bypasses payment.

        Args:
            date: brief date YYYY-MM-DD (default today, UTC).
            agent_id: stable id for your agent (scopes the free-tier counter).
            payment_tx: Solana tx signature, when re-calling after a 402.
        """
        return await core.do_daily_brief(date, agent_key=identity.resolve_agent_key(agent_id),
                                         payment_tx=payment_tx, api_key=identity.bearer())
