# Keyword Performance

## Triggers

- `/keywords`
- `keyword performance`
- `which keywords`
- `utm_term performance`

## Purpose

Ranks paid-search keywords (by utm_term) within Google Ads / Bing. Answers "which search terms actually drive leads vs. just click?"

## Before you build

1. Read `references/design-contract.md` — the two-tone house style, italic-accent rule, forbidden patterns.
2. Read `scripts/template-schema.md` — section type reference.
3. Read `references/rendering-pipeline.md` — MCP strategy and tool-call budgets.

The final deliverable renders via `templates/report-shell.html` (HTML default), with `scripts/build_pdf.py`, `scripts/build_pptx.py`, or `scripts/build_csv.py` available as alternative output formats offered after the HTML.

## Data needs

- Single period: last 30 days
- Filter entries with a populated utm_term AND paid search medium (cpc)
- Group by utm_term; optionally group by (utm_source, utm_term) to split Google vs Bing

**Prior period required:** no

This report uses a single-period pull only. Do NOT run a second `get_entries` call — see `references/rendering-pipeline.md` on skipping the prior-period pull for non-delta reports.

## Section order

The report emits these sections, in this order:

**title-block**
: Kicker: "Keyword Performance · [date range]". Title: `"Which *terms* convert."` Meta: keywords tracked, total leads, period.

**stat-strip**
: 3 stats: keywords tracked, top keyword leads, match-type mix %.

**chart**
: Horizontal bar of top 10 keywords.

**ranked-list**
: Top 10 with columns: rank, keyword, source (google/bing), leads, trend.

**insight-card**
: Kicker "Pattern". Title naming a theme in the top keywords (branded vs. generic, long-tail vs. short, intent level).

**recommendations**
: 3 actions: add more long-tail around top themes, pause zero-lead keywords, review bid strategy on top converters.

**closing**
: Title: `"Bid on *intent*, not volume."`


## Voice guidance

PPC-manager-ready. Reference match types, intent, Quality Score implicitly. Keep it actionable inside Google Ads.

## What never changes

- Report uses the shared two-tone card language across every container.
- Every title has at most ONE `*word*` italic accent, rendered as italic brand-primary.
- Never invent new section types per report — stick to the 10 in `template-schema.md`.
- After delivering the HTML, offer PDF / PPTX / CSV as a one-line follow-up (see `SKILL.md` Rule 2).
