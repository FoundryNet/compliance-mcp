from typing import Optional

import core
import identity


def register(mcp) -> None:
    @mcp.tool
    async def daily_digest(
        industry: Optional[str] = None,
        jurisdiction: Optional[str] = None,
        agent_id: Optional[str] = None,
        payment_tx: Optional[str] = None,
    ) -> dict:
        """Monitor a structured daily regulatory digest — new rules, recalls, enforcement,
        and comment deadlines from the Federal Register, openFDA, and CPSC over the last
        ~2 days, organized by severity and type for compliance monitoring.

        PAID: $0.02 USDC per query after the daily free allowance (25/day). On a
        402, pay the returned Solana memo and re-call with the SAME args plus
        payment_tx=<signature>. An Authorization: Bearer fnet_ key bypasses it.

        Args:
            industry: optional industry filter.
            jurisdiction: federal | state | eu.
            agent_id: stable id for your agent (scopes the free-tier counter).
            payment_tx: Solana tx signature, when re-calling after a 402.
        """
        return await core.do_digest(industry, jurisdiction,
                                    agent_key=identity.resolve_agent_key(agent_id),
                                    payment_tx=payment_tx, api_key=identity.bearer())
