"""compliance-mcp tools — one per file.

  search_regulations   ($0.01)  filtered regulatory entries
  compliance_alerts    ($0.01)  active alerts by industry, deadline-urgent (premium)
  recall_check         ($0.01)  FDA/CPSC recalls
  enforcement_actions  ($0.01)  enforcement actions w/ penalties
  comment_deadlines    ($0.01)  upcoming proposed-rule comment deadlines
  daily_digest         ($0.02)  structured daily digest by severity
  daily_brief          ($10)    curated daily compliance brief (provenance-attested)
  mint_info            (free)   FoundryNet Data Network info
"""
from . import search as search_tool
from . import alerts as alerts_tool
from . import recall as recall_tool
from . import enforcement as enforcement_tool
from . import deadlines as deadlines_tool
from . import digest as digest_tool
from . import daily_brief as daily_brief_tool
from . import brief_summary as brief_summary_tool
from . import mint as mint_tool


def register_all(mcp) -> None:
    for m in (search_tool, alerts_tool, recall_tool, enforcement_tool, deadlines_tool,
              digest_tool, daily_brief_tool, brief_summary_tool, mint_tool):
        m.register(mcp)
