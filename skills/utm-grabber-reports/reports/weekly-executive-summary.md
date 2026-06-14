# Weekly Executive Summary

## Triggers

- `/weekly`
- `weekly summary`
- `this week`
- `last 7 days`

## Purpose

The one-pager for a Monday-morning all-hands. Answers "what happened last week, what changed, what should we do this week?" Tighter and more scannable than the monthly.

## Before you build

1. Read `references/design-contract.md` — the two-tone house style, italic-accent rule, forbidden patterns.
2. Read `scripts/template-schema.md` — section type reference.
3. Read `references/rendering-pipeline.md` — MCP strategy and tool-call budgets.

The final deliverable renders via `templates/report-shell.html` (HTML default), with `scripts/build_pdf.py`, `scripts/build_pptx.py`, or `scripts/build_csv.py` available as alternative output formats offered after the HTML.

## Data needs

- Current period: last 7 days of entries
- Prior period: days 8-14 prior (for deltas)
- Aggregations: `compute_channel_mix`, `compute_source_leaderboard(top_n=5)`, `compute_daily_volume`, `compute_campaign_leaderboard(top_n=5)`

**Prior period required:** yes

Pull entries for the prior equivalent period (days N+1 to 2N back, where N is the current period length) via a second `get_entries` call. Compute deltas for stat-strip cards. Use `compute_percentage_point_delta` for % metrics.

## Section order

The report emits these sections, in this order:

**title-block**
: Kicker: "Weekly Executive Summary · [date range]". Title: `"Your *week* in attribution."` Meta: domain, form, count, "7 days".

**stat-strip**
: 3 stats: total leads (with delta), leads per day, top channel % (with delta).

**insight-card**
: Kicker "The week". Title naming the biggest swing (positive or negative). Body: what drove it.

**chart-insight**
: Doughnut of channel mix + insight card on the mix.

**ranked-list**
: Top 5 campaigns this week with trend indicators (steady/rising/cooling/cold).

**recommendations**
: 3 actions for this week only. Keep them executable within 5 days.

**closing**
: Title: `"See *you* Monday."` Body: one-line next-week pointer.


## Voice guidance

Monday-morning brisk. Lead with the biggest change. Recommendations must be executable this week, not strategic.

## What never changes

- Report uses the shared two-tone card language across every container.
- Every title has at most ONE `*word*` italic accent, rendered as italic brand-primary.
- Never invent new section types per report — stick to the 10 in `template-schema.md`.
- After delivering the HTML, offer PDF / PPTX / CSV as a one-line follow-up (see `SKILL.md` Rule 2).
