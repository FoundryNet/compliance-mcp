-- Regulatory & Compliance Intelligence — schema for compliance_aggregator +
-- compliance-mcp. Standalone Supabase project. Idempotent.

create extension if not exists pg_trgm;

create table if not exists regulatory_updates (
  id                uuid primary key default gen_random_uuid(),
  source            text not null,      -- federal_register | fda | cpsc | osha | sec | epa
  title             text,
  summary           text,               -- first ~500 chars
  full_text_url     text,
  document_number   text,
  agency            text,
  sub_agency        text,
  jurisdiction      text,               -- federal | state | eu
  industry_tags     jsonb,              -- computed keyword match
  regulation_type   text,               -- final_rule|proposed_rule|notice|recall|enforcement|guidance|alert
  effective_date    date,
  comment_deadline  date,
  severity          text,               -- info | warning | action_required | critical
  penalty_amount    numeric,            -- enforcement only
  affected_products jsonb,              -- recalls only
  published_date    date,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  unique (source, document_number)
);

create index if not exists idx_reg_published on regulatory_updates (published_date desc nulls last);
create index if not exists idx_reg_source on regulatory_updates (source);
create index if not exists idx_reg_type on regulatory_updates (regulation_type);
create index if not exists idx_reg_severity on regulatory_updates (severity);
create index if not exists idx_reg_agency on regulatory_updates (agency);
create index if not exists idx_reg_comment on regulatory_updates (comment_deadline);
create index if not exists idx_reg_industry on regulatory_updates using gin (industry_tags);
create index if not exists idx_reg_title_trgm on regulatory_updates using gin (title gin_trgm_ops);

-- ── free-tier counter + payments ─────────────────────────────────────────────
create table if not exists comp_query_usage (
  agent_key text not null, day date not null,
  count integer not null default 0, updated_at timestamptz not null default now(),
  primary key (agent_key, day)
);
create or replace function comp_claim_free_query(p_agent_key text, p_day date, p_cap integer)
returns jsonb language plpgsql as $$
declare cur integer; ok boolean;
begin
  insert into comp_query_usage (agent_key, day, count, updated_at)
  values (p_agent_key, p_day, 0, now())
  on conflict (agent_key, day) do nothing;
  select count into cur from comp_query_usage
    where agent_key = p_agent_key and day = p_day for update;
  if cur < p_cap then
    update comp_query_usage set count = count + 1, updated_at = now()
      where agent_key = p_agent_key and day = p_day;
    ok := true; cur := cur + 1;
  else ok := false; end if;
  return jsonb_build_object('allowed', ok, 'count', cur, 'cap', p_cap);
end; $$;

create table if not exists comp_payments (
  tx_signature text primary key, intent text, agent_key text, tool text,
  amount_usdc numeric, payer_wallet text, recipient text, status text,
  block_time bigint, created_at timestamptz not null default now()
);
