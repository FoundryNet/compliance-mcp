from typing import Optional

import core
import identity


def register(mcp) -> None:
    @mcp.tool
    async def recall_check(
        product: Optional[str] = None,
        company: Optional[str] = None,
        category: Optional[str] = None,
        days_back: Optional[int] = None,
        agent_id: Optional[str] = None,
        payment_tx: Optional[str] = None,
    ) -> dict:
        """Product recalls from FDA (food/drug/device) and CPSC (consumer products),
        with affected products and severity (Class I / injuries → critical).

        PAID: $0.01 USDC per query after the daily free allowance (25/day). On a
        402, pay the returned Solana memo and re-call with the SAME args plus
        payment_tx=<signature>. An Authorization: Bearer fnet_ key bypasses it.

        Args:
            product: product name/keyword.
            company: recalling firm / manufacturer, partial match.
            category: category keyword (food, toy, drug, etc.).
            days_back: only recalls in the last N days.
            agent_id: stable id for your agent (scopes the free-tier counter).
            payment_tx: Solana tx signature, when re-calling after a 402.
        """
        return await core.do_recall(product, company, category, days_back,
                                    agent_key=identity.resolve_agent_key(agent_id),
                                    payment_tx=payment_tx, api_key=identity.bearer())
