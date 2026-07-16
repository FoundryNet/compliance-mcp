from typing import Optional

import core
import identity


def register(mcp) -> None:
    @mcp.tool
    async def compliance_alerts(
        industry: str,
        severity: Optional[str] = None,
        agent_id: Optional[str] = None,
        payment_tx: Optional[str] = None,
    ) -> dict:
        """Monitor active compliance alerts for an industry — action_required and critical
        items from the Federal Register, openFDA, and CPSC, sorted by deadline urgency for
        ongoing compliance monitoring. The premium tool: "what do I need to worry about in
        pharma this week?"

        PAID: $0.01 per query after the daily free allowance (25/day). On a
        402, settle the returned payment challenge and re-call with the SAME args plus
        payment_tx=<reference>. An Authorization: Bearer fnet_ key bypasses it.

        Args:
            industry: e.g. "pharma", "finance", "food".
            severity: optional filter (else action_required + critical).
            agent_id: stable id for your agent (scopes the free-tier counter).
            payment_tx: payment transaction reference, when re-calling after a 402.
        """
        return await core.do_alerts(industry, severity,
                                    agent_key=identity.resolve_agent_key(agent_id),
                                    payment_tx=payment_tx, api_key=identity.bearer())
