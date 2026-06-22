# Lead Quality Scorer

## Triggers

- `/score-leads`
- `score leads`
- `lead quality`
- `best leads`
- `prioritize leads`

## Purpose

Ranks all leads in the period by declared intent and context signals (ad spend bracket, CRM, timeframe, company size, source quality). Answers "which leads should sales work first?"

## Before you build

1. Read `references/design-contract.md` — the two-tone house style, italic-accent rule, forbidden patterns.
2. Read `scripts/template-schema.md` — section type reference.
3. Read `references/rendering-pipeline.md` — MCP strategy and tool-call budgets.

The final deliverable renders via `templates/report-shell.html` (HTML default), with `scripts/build_pdf.py`, `scripts/build_pptx.py`, or `scripts/build_csv.py` available as alternative output formats offered after the HTML.

## Data needs

- Single period: last 30 days of entries
- Score inputs: declared monthly ad spend, CRM platform (high-value vs low), timeframe urgency, source tier (enterprise vs broad)
- Each lead gets a score 0-100 with component breakdown

**Prior period required:** no

This report uses a single-period pull only. Do NOT run a second `get_entries` call — see `references/rendering-pipeline.md` on skipping the prior-period pull for non-delta reports.

## Section order

The report emits these sections, in this order:

**title-block**
: Kicker: "Lead Quality Scorer · [date range]". Title: `"Your *top* leads to work first."` Meta: total scored, threshold, period.

**hero-number**
: Kicker "High-priority leads". Value: count of leads scoring >=70. Label: "scored in the top tier by declared spend, CRM, and urgency."

**stat-strip**
: 4 stats: leads scored, top-tier count, avg score, top source for high-tier.

**ranked-list**
: Top 10 leads with columns: rank, email (truncated), company, declared spend, CRM, score, source. Use a `mono-number` column for score.

**insight-card**
: Kicker "Pattern in your top tier". Title surfacing a common attribute (e.g., `"*Google search* drove 8 of your top 10."`)

**recommendations**
: 3 actions: work the top 10 this week, build an automation for mid-tier, score inputs to tighten (if any fields were missing).

**closing**
: Title: `"Work the *top* third first."` Body: offer CSV export for hand-off to sales.


## Voice guidance

Sales-ready, not analytical. Each lead is a human ready to be contacted. Privacy: truncate emails shown inline.

## What never changes

- Report uses the shared two-tone card language across every container.
- Every title has at most ONE `*word*` italic accent, rendered as italic brand-primary.
- Never invent new section types per report — stick to the 10 in `template-schema.md`.
- After delivering the HTML, offer PDF / PPTX / CSV as a one-line follow-up (see `SKILL.md` Rule 2).
