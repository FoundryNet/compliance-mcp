from typing import Optional

import core
import identity


def register(mcp) -> None:
    @mcp.tool
    async def comment_deadlines(
        industry: Optional[str] = None,
        days_ahead: Optional[int] = 30,
        agent_id: Optional[str] = None,
        payment_tx: Optional[str] = None,
    ) -> dict:
        """Track upcoming public-comment deadlines for proposed rules from the Federal
        Register — what regulatory compliance and regulatory-affairs agents monitor
        constantly. Sorted by soonest deadline.

        PAID: $0.01 USDC per query after the daily free allowance (25/day). On a
        402, pay the returned Solana memo and re-call with the SAME args plus
        payment_tx=<signature>. An Authorization: Bearer fnet_ key bypasses it.

        Args:
            industry: optional industry filter.
            days_ahead: look-ahead window in days (1-365, default 30).
            agent_id: stable id for your agent (scopes the free-tier counter).
            payment_tx: Solana tx signature, when re-calling after a 402.
        """
        return await core.do_deadlines(industry, days_ahead,
                                       agent_key=identity.resolve_agent_key(agent_id),
                                       payment_tx=payment_tx, api_key=identity.bearer())
