# Regulatory & Compliance Intelligence MCP

**Regulatory & compliance intelligence for AI agents** — rules, recalls,
enforcement actions, and comment deadlines from free government sources,
classified by industry and severity.

> Part of the **FoundryNet Data Network**. See also:
> **gov-contracts-mcp**, **brand-intel-mcp**, **patent-intel-mcp**,
> **financial-signals-mcp**, **weather-intel-mcp**.

## Connect

- **MCP endpoint** (Streamable HTTP): `https://compliance-mcp-production.up.railway.app/mcp`
- **Registry:** `io.github.FoundryNet/compliance-mcp`
- **Agent card:** `https://compliance-mcp-production.up.railway.app/.well-known/agent-card.json`

### Claude Desktop / Cursor / Claude Code

```bash
claude mcp add --transport http compliance https://compliance-mcp-production.up.railway.app/mcp
```

```json
{ "mcpServers": { "compliance": { "url": "https://compliance-mcp-production.up.railway.app/mcp" } } }
```

## Tools

| Tool | Price | What it does |
|---|---|---|
| `search_regulations` | $0.01 | Filtered regulatory entries (industry/agency/type/keyword/severity) |
| `compliance_alerts` | $0.01 | Active alerts for an industry, deadline-urgent — *"what do I worry about in pharma this week?"* |
| `recall_check` | $0.01 | FDA (food/drug/device) + CPSC product recalls with severity |
| `enforcement_actions` | $0.01 | Enforcement actions with parsed penalty amounts |
| `comment_deadlines` | $0.01 | Upcoming proposed-rule comment deadlines |
| `daily_digest` | $0.05 | Structured daily digest organized by severity |
| `brief_summary` | $0.50 | Top-5 signals — a sample of the full daily brief |
| `daily_brief` | $10 | Full curated daily compliance brief |
| `mint_info` | **free** | FoundryNet Data Network info |

**Free tier:** 25 paid-tool queries/day per agent. Then metered per-query billing:
the tool returns an HTTP-402 payment challenge — settle it, then re-call with the same
args plus `payment_tx=<reference>`. An `Authorization: Bearer fnet_…` key bypasses the paywall.

## How it works

Every 12 hours the aggregator fetches new entries from **Federal Register**
(rules/proposed/notices), **openFDA** (food/drug/device recall & enforcement), and
**CPSC** (consumer product recalls), classifies each by **industry** (keyword
taxonomy across 12 sectors) and **severity** (info → warning → action_required →
critical), and stores them in a standalone Supabase project.

**Severity logic:** Class I / injury-or-death recalls + emergency rules →
`critical`; final rules with a compliance deadline ≤ 90 days or enforcement
penalties > $100K → `action_required`; proposed rules in comment period → `warning`;
notices/guidance → `info`.

**Honesty note:** EPA ECHO, OSHA, and SEC enforcement (their public endpoints need
multi-step queries or scraping) are planned additional sources; enforcement
penalties are currently parsed from Federal Register notices.

## Discovery

MCP registry: `io.github.FoundryNet/compliance-mcp`

Built by [FoundryNet](https://foundrynet.io?utm_source=github&utm_medium=readme&utm_campaign=compliance-mcp) · forge@foundrynet.io

## Live network activity

Real-time verified work across 17 servers and autonomous agents in the FoundryNet Data Network.
