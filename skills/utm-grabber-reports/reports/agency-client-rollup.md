# Agency Client Rollup

## Triggers

- `/rollup`
- `agency rollup`
- `all clients`
- `portfolio view`
- `all brands`

## Purpose

Aggregated view across ALL connected brand profiles. Answers "how is my agency's portfolio performing — who's up, who's down, where do I need to intervene?"

## Before you build

1. Read `references/design-contract.md` — the two-tone house style, italic-accent rule, forbidden patterns.
2. Read `scripts/template-schema.md` — section type reference.
3. Read `references/rendering-pipeline.md` — MCP strategy and tool-call budgets.

The final deliverable renders via `templates/report-shell.html` (HTML default), with `scripts/build_pdf.py`, `scripts/build_pptx.py`, or `scripts/build_csv.py` available as alternative output formats offered after the HTML.

## Data needs

- Requires multiple configured brand profiles (agency workflow)
- Single period: last 30 days for each brand
- Per-brand: total leads, channel mix, hygiene %, trend direction

**Prior period required:** no

This report uses a single-period pull only. Do NOT run a second `get_entries` call — see `references/rendering-pipeline.md` on skipping the prior-period pull for non-delta reports.

## Section order

The report emits these sections, in this order:

**title-block**
: Kicker: "Agency Portfolio · [date range]". Title: `"Your *portfolio* at a glance."` Meta: brands tracked, aggregate leads, period.

**stat-strip**
: 4 stats: brands tracked, portfolio total leads, brands up this period, brands needing attention.

**ranked-list**
: All brands with columns: rank, brand name, leads, avg/day, hygiene %, trend state. Sort by leads desc.

**chart**
: Horizontal bar: leads per brand for quick scan.

**insight-card**
: Kicker "Portfolio health". Title: `"*X* brands driving Y% of portfolio leads."` Body: concentration or diversification commentary.

**recommendations**
: 3 actions: which brand to prioritize next week, which to audit for hygiene, which is an upsell candidate based on momentum.

**closing**
: Title: `"Your *book*, top-down."` Body: offer a per-brand deep dive.


## Voice guidance

Agency-owner tone. Each brand is a client with money at stake. Recommendations are operational (who to call, which audit to run).

## What never changes

- Report uses the shared two-tone card language across every container.
- Every title has at most ONE `*word*` italic accent, rendered as italic brand-primary.
- Never invent new section types per report — stick to the 10 in `template-schema.md`.
- After delivering the HTML, offer PDF / PPTX / CSV as a one-line follow-up (see `SKILL.md` Rule 2).
