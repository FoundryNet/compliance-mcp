import core


def register(mcp) -> None:
    @mcp.tool
    async def mint_info() -> dict:
        """FoundryNet Data Network info + MINT Protocol details. FREE.

        Returns how to attest your agent's compliance/regulatory analysis with MINT
        Protocol for verifiable on-chain proof, the MINT MCP endpoint, and the
        sister data servers (gov-contracts, brand-intel, patent-intel,
        financial-signals, weather-intel).
        """
        return core.mint_info()
