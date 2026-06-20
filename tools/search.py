from typing import Optional

import core
import identity


def register(mcp) -> None:
    @mcp.tool
    async def search_regulations(
        industry: Optional[str] = None,
        agency: Optional[str] = None,
        regulation_type: Optional[str] = None,
        keyword: Optional[str] = None,
        severity: Optional[str] = None,
        days_back: Optional[int] = None,
        limit: int = 50,
        agent_id: Optional[str] = None,
        payment_tx: Optional[str] = None,
    ) -> dict:
        """Search regulatory updates and final rules from the Federal Register, openFDA,
        and CPSC by industry, agency, type, keyword, or severity — regulatory compliance
        and compliance monitoring intelligence, newest first.

        PAID: $0.01 USDC per query after a daily free allowance (25/day). On a 402,
        pay the returned Solana memo and re-call with the SAME args plus
        payment_tx=<signature>. agent_id scopes your allowance; an Authorization:
        Bearer fnet_ key bypasses it.

        Args:
            industry: one of healthcare, pharma, finance, manufacturing, food,
                consumer_products, energy, technology, construction, transportation,
                agriculture, defense.
            agency: issuing agency, partial match.
            regulation_type: final_rule|proposed_rule|notice|recall|enforcement|guidance|alert.
            keyword: free-text over title + summary.
            severity: info|warning|action_required|critical.
            days_back: only entries published in the last N days.
            limit: max rows (1-200, default 50).
            agent_id: stable id for your agent (scopes the free-tier counter).
            payment_tx: Solana tx signature, when re-calling after a 402.
        """
        filters = {"industry": industry, "agency": agency, "regulation_type": regulation_type,
                   "keyword": keyword, "severity": severity, "days_back": days_back, "limit": limit}
        return await core.do_search(filters, agent_key=identity.resolve_agent_key(agent_id),
                                    payment_tx=payment_tx, api_key=identity.bearer())
