# Landing Page Performance

## Triggers

- `/landing-pages`
- `landing page performance`
- `best pages`
- `page performance`

## Purpose

Ranks landing pages by leads captured. Answers "which pages convert best from which traffic sources?"

## Before you build

1. Read `references/design-contract.md` — the two-tone house style, italic-accent rule, forbidden patterns.
2. Read `scripts/template-schema.md` — section type reference.
3. Read `references/rendering-pipeline.md` — MCP strategy and tool-call budgets.

The final deliverable renders via `templates/report-shell.html` (HTML default), with `scripts/build_pdf.py`, `scripts/build_pptx.py`, or `scripts/build_csv.py` available as alternative output formats offered after the HTML.

## Data needs

- Single period: last 30 days
- Aggregation: group entries by `Source URL` (or `handl_landing_page`)
- Secondary: for each top page, the source mix that lands there

**Prior period required:** no

This report uses a single-period pull only. Do NOT run a second `get_entries` call — see `references/rendering-pipeline.md` on skipping the prior-period pull for non-delta reports.

## Section order

The report emits these sections, in this order:

**title-block**
: Kicker: "Landing Page Performance · [date range]". Title: `"Where *leads* convert."` Meta: pages tracked, total leads, period.

**stat-strip**
: 3 stats: pages with leads, top page leads, top 3 share.

**ranked-list**
: Top 10 pages with columns: rank, page path, top source (mono), leads, conversion trend.

**chart-insight**
: Bar-stacked: top 5 pages × source mix. Insight card names the pattern (e.g., `"*Google Ads* funnels to /pricing but *organic* funnels to /blog."`)

**recommendations**
: 3 actions: replicate the best page's layout, fix the worst converter's CTA, add source-specific variants to the top page.

**closing**
: Title: `"Optimize the *top* three first."`


## Voice guidance

Page-level tactical. CTAs, headlines, form position matter here. Recommendations reference layout, not strategy.

## What never changes

- Report uses the shared two-tone card language across every container.
- Every title has at most ONE `*word*` italic accent, rendered as italic brand-primary.
- Never invent new section types per report — stick to the 10 in `template-schema.md`.
- After delivering the HTML, offer PDF / PPTX / CSV as a one-line follow-up (see `SKILL.md` Rule 2).
