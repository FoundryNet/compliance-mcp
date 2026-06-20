from typing import Optional

import core
import identity


def register(mcp) -> None:
    @mcp.tool
    async def enforcement_actions(
        agency: Optional[str] = None,
        company: Optional[str] = None,
        industry: Optional[str] = None,
        min_penalty: Optional[float] = None,
        agent_id: Optional[str] = None,
        payment_tx: Optional[str] = None,
    ) -> dict:
        """Track regulatory enforcement actions (incl. OSHA citations and SEC enforcement)
        from the Federal Register, with parsed penalty amounts and context, filterable by
        agency, company, industry, or minimum penalty.

        PAID: $0.01 USDC per query after the daily free allowance (25/day). On a
        402, pay the returned Solana memo and re-call with the SAME args plus
        payment_tx=<signature>. An Authorization: Bearer fnet_ key bypasses it.

        Args:
            agency: enforcing agency, partial match.
            company: company name, partial match.
            industry: industry tag filter.
            min_penalty: minimum penalty amount (USD).
            agent_id: stable id for your agent (scopes the free-tier counter).
            payment_tx: Solana tx signature, when re-calling after a 402.
        """
        return await core.do_enforcement(agency, company, industry, min_penalty,
                                         agent_key=identity.resolve_agent_key(agent_id),
                                         payment_tx=payment_tx, api_key=identity.bearer())
