# Ad Creative Performance

## Triggers

- `/ad-creative`
- `ad creative performance`
- `which ads`
- `utm_content performance`

## Purpose

Ranks ad creatives (by utm_content) within each paid channel. Answers "which ad variants are pulling their weight?"

## Before you build

1. Read `references/design-contract.md` — the two-tone house style, italic-accent rule, forbidden patterns.
2. Read `scripts/template-schema.md` — section type reference.
3. Read `references/rendering-pipeline.md` — MCP strategy and tool-call budgets.

The final deliverable renders via `templates/report-shell.html` (HTML default), with `scripts/build_pdf.py`, `scripts/build_pptx.py`, or `scripts/build_csv.py` available as alternative output formats offered after the HTML.

## Data needs

- Single period: last 30 days
- Filter entries with a populated utm_content AND a paid medium (cpc, paid social, display)
- Group by (utm_source, utm_content) to see variants per channel

**Prior period required:** no

This report uses a single-period pull only. Do NOT run a second `get_entries` call — see `references/rendering-pipeline.md` on skipping the prior-period pull for non-delta reports.

## Section order

The report emits these sections, in this order:

**title-block**
: Kicker: "Ad Creative Performance · [date range]". Title: `"Your *top* ads."` Meta: channels analyzed, creatives tracked, period.

**stat-strip**
: 3 stats: creatives tracked, top creative leads, creatives with zero leads.

**chart**
: Bar-grouped: top 5 creatives by channel.

**ranked-list**
: Top 10 creatives with columns: rank, utm_content, source·medium, leads, trend.

**insight-card**
: Kicker "Pattern in what wins". Title naming a common thread across top creatives (headline length, offer type, emotional tone).

**recommendations**
: 3 actions: pause zero-lead creatives, duplicate winning creative in adjacent channels, test a variant of the top creative.

**closing**
: Title: `"Fewer *better* ads."`


## Voice guidance

Creative-team-ready. Reference hooks, headlines, offers. Never evaluate ads you haven't seen — stick to the lead counts.

## What never changes

- Report uses the shared two-tone card language across every container.
- Every title has at most ONE `*word*` italic accent, rendered as italic brand-primary.
- Never invent new section types per report — stick to the 10 in `template-schema.md`.
- After delivering the HTML, offer PDF / PPTX / CSV as a one-line follow-up (see `SKILL.md` Rule 2).
