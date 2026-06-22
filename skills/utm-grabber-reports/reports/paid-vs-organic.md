# Paid vs Organic

## Triggers

- `/paid-vs-organic`
- `paid vs organic`
- `paid or organic`
- `organic vs paid`

## Purpose

The fundamental split. Compares paid and organic traffic on volume, quality, cost (if known), and trajectory. Answers "which channel category should I invest more in next quarter?"

## Before you build

1. Read `references/design-contract.md` — the two-tone house style, italic-accent rule, forbidden patterns.
2. Read `scripts/template-schema.md` — section type reference.
3. Read `references/rendering-pipeline.md` — MCP strategy and tool-call budgets.

The final deliverable renders via `templates/report-shell.html` (HTML default), with `scripts/build_pdf.py`, `scripts/build_pptx.py`, or `scripts/build_csv.py` available as alternative output formats offered after the HTML.

## Data needs

- Single period: last 90 days for stability
- Classify entries: paid = medium in {cpc, paid social, display, video ads}; organic = everything else
- Compute per-category: volume, daily avg, hygiene, top sources, trend direction

**Prior period required:** no

This report uses a single-period pull only. Do NOT run a second `get_entries` call — see `references/rendering-pipeline.md` on skipping the prior-period pull for non-delta reports.

## Section order

The report emits these sections, in this order:

**title-block**
: Kicker: "Paid vs Organic · Last 90 days". Title: `"The *fundamental* split."` Meta: paid count, organic count, period.

**chart-insight**
: Doughnut: paid vs organic share. Insight card names the healthier mix.

**stat-strip**
: 4 stats: paid leads, paid avg/day, organic leads, organic avg/day. (Pair them visually.)

**chart**
: Line chart: daily paid vs daily organic (two lines). See trajectories diverge or converge.

**ranked-list**
: Top 5 in each category, side by side (or a split table).

**insight-card**
: Kicker "Trajectory". Title: which category is gaining momentum (`"*Organic* is growing 3× faster than paid."`) Body: what this predicts for 90-day budget.

**recommendations**
: 3 actions: quarterly budget reallocation, content investment ratio, paid campaign freshness cadence.

**closing**
: Title: `"Invest where the *curve* bends up."`


## Voice guidance

Portfolio-manager tone. Both categories matter — this isn't an either/or. Frame recommendations as allocation, not replacement.

## What never changes

- Report uses the shared two-tone card language across every container.
- Every title has at most ONE `*word*` italic accent, rendered as italic brand-primary.
- Never invent new section types per report — stick to the 10 in `template-schema.md`.
- After delivering the HTML, offer PDF / PPTX / CSV as a one-line follow-up (see `SKILL.md` Rule 2).
