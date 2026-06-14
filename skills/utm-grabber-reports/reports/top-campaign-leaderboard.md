# Top Campaign Leaderboard

## Triggers

- `/campaigns`
- `top campaigns`
- `campaign leaderboard`
- `best campaigns`

## Purpose

Ranks campaigns by lead volume for the period. The "who won" report for paid marketing teams. Answers "which campaigns worked and which are sleeping?"

## Before you build

1. Read `references/design-contract.md` — the two-tone house style, italic-accent rule, forbidden patterns.
2. Read `scripts/template-schema.md` — section type reference.
3. Read `references/rendering-pipeline.md` — MCP strategy and tool-call budgets.

The final deliverable renders via `templates/report-shell.html` (HTML default), with `scripts/build_pdf.py`, `scripts/build_pptx.py`, or `scripts/build_csv.py` available as alternative output formats offered after the HTML.

## Data needs

- Single period: last 30 days
- Aggregation: `compute_campaign_leaderboard(top_n=10)`
- Compute trend state per campaign (rising/steady/cooling/cold) using sub-period slicing

**Prior period required:** no

This report uses a single-period pull only. Do NOT run a second `get_entries` call — see `references/rendering-pipeline.md` on skipping the prior-period pull for non-delta reports.

## Section order

The report emits these sections, in this order:

**title-block**
: Kicker: "Top Campaign Leaderboard · [date range]". Title: `"Your *winners* this period."` Meta: total campaigns, leads, period.

**stat-strip**
: 3 stats: campaigns active, top campaign leads, top 3 share of total.

**chart**
: Horizontal bar of top 10 campaigns.

**ranked-list**
: Top 10 with columns: rank, campaign name, source·medium, leads, trend. Use trend-state coloring.

**insight-card**
: Kicker "Who's carrying the weight". Title: `"Your top *3* campaigns drove X% of leads."`

**recommendations**
: 3 actions: double down on top, audit cold campaigns for creative fatigue, test one new campaign in the winning channel.

**closing**
: Title: `"Feed the *winners*."`


## Voice guidance

Competitive energy. Name winners and under-performers directly. Trend states are doing the work of tone.

## What never changes

- Report uses the shared two-tone card language across every container.
- Every title has at most ONE `*word*` italic accent, rendered as italic brand-primary.
- Never invent new section types per report — stick to the 10 in `template-schema.md`.
- After delivering the HTML, offer PDF / PPTX / CSV as a one-line follow-up (see `SKILL.md` Rule 2).
