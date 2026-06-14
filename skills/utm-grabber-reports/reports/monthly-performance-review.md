# Monthly Performance Review

## Triggers

- `/monthly`
- `monthly review`
- `monthly report`
- `last 30 days`
- `this month`

## Purpose

The default executive summary. Answers "how did my marketing perform in the last 30 days, and how does that compare to the previous 30?" This is the highest-run report in the catalog — keep it broad, keep it actionable.

## Before you build

1. Read `references/design-contract.md` — the two-tone house style, italic-accent rule, forbidden patterns.
2. Read `scripts/template-schema.md` — section type reference.
3. Read `references/rendering-pipeline.md` — MCP strategy and tool-call budgets.

The final deliverable renders via `templates/report-shell.html` (HTML default), with `scripts/build_pdf.py`, `scripts/build_pptx.py`, or `scripts/build_csv.py` available as alternative output formats offered after the HTML.

## Data needs

- Current period: last 30 days of entries via `get_entries`
- Prior period: days 31-60 prior via a second `get_entries` (needed for deltas)
- Aggregations: `compute_channel_mix`, `compute_source_leaderboard(top_n=6)`, `compute_daily_volume`, `compute_hygiene_counts`, `compute_campaign_leaderboard(top_n=6)`

**Prior period required:** yes

Pull entries for the prior equivalent period (days N+1 to 2N back, where N is the current period length) via a second `get_entries` call. Compute deltas for stat-strip cards. Use `compute_percentage_point_delta` for % metrics.

## Section order

The report emits these sections, in this order:

**title-block**
: Kicker: "Monthly Performance Review · [date range]". Title: `"Your *attribution* picture."` or similar. Meta bits: domain, form plugin, submission count, "30 days".

**stat-strip**
: 4 stats: total leads (with delta vs prior), leads per day (with delta), paid traffic % (with delta), UTM coverage % (with delta).

**insight-card**
: Kicker "Headline". Title that names the biggest story: `"Paid search drove *51%* of your 490 leads."` Body: 1-2 paragraphs naming the top source and the biggest attribution gap.

**section-header**
: Number "01". Kicker "Channel Mix". Title: `"Where *leads* come from."`

**chart-insight**
: Doughnut of channel mix. Insight card names the dominant channel and the mix health.

**section-header**
: Number "02". Kicker "Sources". Title: `"Top UTM *sources*."`

**chart-insight**
: Horizontal bar of top 6 sources. Insight card names concentration risk or diversification health.

**section-header**
: Number "03". Kicker "Volume". Title: `"Daily *rhythm* of leads."`

**chart**
: Area chart of daily lead count. Caption names peak and trough days.

**section-header**
: Number "04". Kicker "Recommendations". Title: `"What to do *next*."`

**recommendations**
: 4 actions: fix hygiene gaps, double down on top source, run weekly anomaly check, score leads before next sales week. Italic accent on the key noun in each title.

**closing**
: Title: `"That's *your* month."` Body: one sentence offering follow-up reports.


## Voice guidance

Executive-ready. No jargon. Every recommendation tied to a specific number from the data. Deltas always framed as "vs prior 30 days".

## What never changes

- Report uses the shared two-tone card language across every container.
- Every title has at most ONE `*word*` italic accent, rendered as italic brand-primary.
- Never invent new section types per report — stick to the 10 in `template-schema.md`.
- After delivering the HTML, offer PDF / PPTX / CSV as a one-line follow-up (see `SKILL.md` Rule 2).
