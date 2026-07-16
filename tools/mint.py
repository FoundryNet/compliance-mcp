import core


def register(mcp) -> None:
    @mcp.tool
    async def mint_info() -> dict:
        """Get FoundryNet Data Network info for compliance monitoring agents. FREE.

        Returns how to attest your agent's compliance/regulatory analysis for
        verifiable provenance, plus the sister data servers (gov-contracts,
        brand-intel, patent-intel, financial-signals, weather-intel).
        """
        return core.mint_info()
