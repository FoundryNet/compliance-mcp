"""Env-driven configuration for compliance-mcp.

Regulatory & compliance intelligence aggregated from free, keyless government
sources (Federal Register, openFDA, CPSC, EPA ECHO), classified by industry +
severity, stored in its own standalone Supabase project. 7 tools, x402 metered.
Part of the FoundryNet Data Network.

Required to be useful:
  SUPABASE_URL, SUPABASE_SERVICE_KEY   the standalone compliance-intel project.
Optional:
  PORT, REQUEST_TIMEOUT
  X402_ENABLED, SOLANA_WALLET, PAYMENT_RECIPIENT, PAYMENT_VERIFY_RPC,
  PAYMENT_USDC_MINT, PAYMENT_EXPIRY_SECONDS
  FREE_TIER_DAILY      default 5
  AGG_HOUR_UTC_LIST    comma hours for the 12h cron (default "1,13")
  LOOKBACK_DAYS        cold-start window, default 3
  SOURCE_USER_AGENT    UA for gov APIs
  PRICE_*              per-tool USDC prices
"""
from __future__ import annotations

import os


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _flag(name: str, default: bool) -> bool:
    return _env(name, "true" if default else "false").strip().lower() in ("1", "true", "yes", "on")


SUPABASE_URL         = _env("SUPABASE_URL", "https://pjtpvcsklfwsgspzlbzs.supabase.co").rstrip("/")
SUPABASE_SERVICE_KEY = _env("SUPABASE_SERVICE_KEY")
# Shared-hub consolidation: which Postgres schema this service's tables live in.
# "public" = standalone; a service name (e.g. "brand") = the shared intel hub,
# reached via PostgREST Accept-Profile/Content-Profile headers.
SUPABASE_SCHEMA      = _env("SUPABASE_SCHEMA", "public")

PORT            = int(_env("PORT", "8080"))
REQUEST_TIMEOUT = int(_env("REQUEST_TIMEOUT", "30"))

# ── Sources (all keyless) ────────────────────────────────────────────────────
SOURCE_USER_AGENT = _env("SOURCE_USER_AGENT", "FoundryNet Data Network forge@foundrynet.io")
FEDERAL_REGISTER = "https://www.federalregister.gov/api/v1/documents.json"
OPENFDA = "https://api.fda.gov"
CPSC = "https://www.saferproducts.gov/RestWebServices/Recall"
EPA_ECHO = "https://echodata.epa.gov/echo/case_rest_services.get_cases"

LOOKBACK_DAYS = int(_env("LOOKBACK_DAYS", "3"))
AGG_HOUR_UTC_LIST = [int(x) for x in _env("AGG_HOUR_UTC_LIST", "1,13").split(",") if x.strip().isdigit()]

# ── x402 per-tool pricing ────────────────────────────────────────────────────
X402_ENABLED      = _flag("X402_ENABLED", True)
SOLANA_WALLET     = _env("SOLANA_WALLET", "wUumjWJjfn27VQhTXd1jUNTzszCmsErkzaEeHWbLThd")
PAYMENT_RECIPIENT = _env("PAYMENT_RECIPIENT", SOLANA_WALLET).strip()
PAYMENT_VERIFY_RPC = _env("PAYMENT_VERIFY_RPC", "https://api.mainnet-beta.solana.com").rstrip("/")
PAYMENT_USDC_MINT  = _env("PAYMENT_USDC_MINT", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v").strip()
PAYMENT_EXPIRY_SECONDS = int(_env("PAYMENT_EXPIRY_SECONDS", "300"))

FREE_TIER_DAILY = int(_env("FREE_TIER_DAILY", "5"))

PRICE_SEARCH       = float(_env("PRICE_SEARCH", "0.01"))
PRICE_ALERTS       = float(_env("PRICE_ALERTS", "0.01"))
PRICE_RECALL       = float(_env("PRICE_RECALL", "0.01"))
PRICE_ENFORCEMENT  = float(_env("PRICE_ENFORCEMENT", "0.01"))
PRICE_DEADLINES    = float(_env("PRICE_DEADLINES", "0.01"))
PRICE_DIGEST       = float(_env("PRICE_DIGEST", "0.05"))
PRICE_DAILY_BRIEF  = float(_env("PRICE_DAILY_BRIEF", "10"))
PRICE_BRIEF_SUMMARY = float(_env("PRICE_BRIEF_SUMMARY", "0.5"))  # $0.50 sample tier

# ── Stripe rail (parallel payment option to x402, for the daily brief) ────────
# Agents without a USDC wallet pay this hosted Payment Link instead. The secret
# key verifies the resulting Checkout Session; the link URL is shown on a 402.
STRIPE_SECRET_KEY       = _env("STRIPE_SECRET_KEY", "")
STRIPE_LINK_DAILY_BRIEF = _env("STRIPE_LINK_DAILY_BRIEF",
                               "https://foundrynet.io/pricing")

# ── Daily curated brief ──────────────────────────────────────────────────────
BRIEF_HOUR_UTC = int(_env("BRIEF_HOUR_UTC", "5"))   # curator runs at 05:00 UTC
SERVER_SLUG    = "compliance"
# Cross-network brief catalog (server -> price + tool) for related_briefs.
NETWORK_BRIEFS = {
    "financial-signals": "$25", "cyber-intel": "$15", "patent-intel": "$10",
    "gov-contracts": "$10", "compliance": "$10", "brand-intel": "$5", "weather-intel": "$5",
}

# ── FoundryNet Data Network cross-promo ──────────────────────────────────────
MINT_MCP_URL  = _env("MINT_MCP_URL", "https://mint-mcp-production.up.railway.app/mcp")
MINT_INFO_URL = _env("MINT_INFO_URL", "https://mint.foundrynet.io")
SISTER_SERVERS = {
    "gov-contracts-mcp":     "https://gov-contracts-mcp-production.up.railway.app/mcp",
    "brand-intel-mcp":       "https://brand-intel-mcp-production.up.railway.app/mcp",
    "patent-intel-mcp":      "https://patent-intel-mcp-production.up.railway.app/mcp",
    "financial-signals-mcp": "https://financial-signals-mcp-production.up.railway.app/mcp",
    "weather-intel-mcp":     "https://weather-intel-mcp-production.up.railway.app/mcp",
}

PUBLIC_MCP_URL = _env("PUBLIC_MCP_URL", "https://compliance-mcp-production.up.railway.app/mcp")

# ── FoundryNet Data Network — full sister-server map (auto-updated 2026-06-19) ──
# Re-binds SISTER_SERVERS to the complete network (all 11 servers, self excluded),
# now including fact-check-mcp, oss-intel-mcp, social-intel-mcp.
_FNET_ALL_SERVERS = {
    "mint-mcp":              "https://mint-mcp-production.up.railway.app/mcp",
    "foundrynet-mcp":        "https://foundrynet-mcp-production.up.railway.app/mcp",
    "gov-contracts-mcp":     "https://gov-contracts-mcp-production.up.railway.app/mcp",
    "brand-intel-mcp":       "https://brand-intel-mcp-production.up.railway.app/mcp",
    "patent-intel-mcp":      "https://patent-intel-mcp-production.up.railway.app/mcp",
    "financial-signals-mcp": "https://financial-signals-mcp-production.up.railway.app/mcp",
    "weather-intel-mcp":     "https://weather-intel-mcp-production.up.railway.app/mcp",
    "cyber-intel-mcp":       "https://cyber-intel-mcp-production.up.railway.app/mcp",
    "compliance-mcp":        "https://compliance-mcp-production.up.railway.app/mcp",
    "academic-intel-mcp":    "https://academic-intel-mcp-production.up.railway.app/mcp",
    "fact-check-mcp":        "https://fact-check-mcp-production.up.railway.app/mcp",
    "oss-intel-mcp":         "https://oss-intel-mcp-production.up.railway.app/mcp",
    "social-intel-mcp":      "https://social-intel-mcp-production.up.railway.app/mcp",
    "crypto-intel-mcp":      "https://crypto-intel-mcp-production.up.railway.app/mcp",
    "market-data-mcp":       "https://market-data-mcp-production.up.railway.app/mcp",
    "email-verify-mcp":      "https://email-verify-mcp-production.up.railway.app/mcp",
    "currency-intel-mcp":    "https://currency-intel-mcp-production.up.railway.app/mcp",
}
SISTER_SERVERS = {k: v for k, v in _FNET_ALL_SERVERS.items() if k != "compliance-mcp"}

# ── Subscriptions (network-wide $19/$49 Stripe links; same on every server) ──────
# These lead the 402 response: a credit-card subscription converts where "send USDC
# with an SPL-memo" does not. Both unlock unlimited queries here; Intelligence also
# unlocks Knowledge Bases + composite products on foundrynet-agents.
STRIPE_LINK_PRO      = _env("STRIPE_LINK_PRO",   "https://buy.stripe.com/3cIdR278Cglq7bY5b67N604")
STRIPE_LINK_INTEL    = _env("STRIPE_LINK_INTEL", "https://buy.stripe.com/4gMaEQ78C8SYaoa32Y7N605")
NETWORK_SERVER_COUNT = int(_env("NETWORK_SERVER_COUNT", "17"))

# ── Dynamic allowlist (subscriber keys, 5-min cache; static env = fallback) ──────
# Default: poll the agents /v1/allowlist (no DB creds needed). To read forge_api_keys
# directly instead, set FORGE_KEYS_SUPABASE_URL + FORGE_KEYS_SUPABASE_KEY.
FNET_ALLOWLIST_URL      = _env("FNET_ALLOWLIST_URL",
                               "https://foundrynet-agents-production.up.railway.app/v1/allowlist")
FORGE_KEYS_SUPABASE_URL = _env("FORGE_KEYS_SUPABASE_URL", "")
FORGE_KEYS_SUPABASE_KEY = _env("FORGE_KEYS_SUPABASE_KEY", "")

# ── Per-call event log (fire-and-forget telemetry to the agents ingest) ──────────
EVENT_LOG_URL   = _env("EVENT_LOG_URL",
                       "https://foundrynet-agents-production.up.railway.app/v1/call-events")
EVENT_LOG_TOKEN = _env("EVENT_LOG_TOKEN", "")
