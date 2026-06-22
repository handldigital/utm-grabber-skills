# Campaign Deep Dive

## Triggers

- `/campaign-deep-dive`
- `deep dive on`
- `tell me about campaign`
- `analyze campaign`

## Purpose

Full profile of a single campaign — every lead, daily pattern, contributing creatives, landing-page mix. Answers "what is this one campaign actually doing?"

## Before you build

1. Read `references/design-contract.md` — the two-tone house style, italic-accent rule, forbidden patterns.
2. Read `scripts/template-schema.md` — section type reference.
3. Read `references/rendering-pipeline.md` — MCP strategy and tool-call budgets.

The final deliverable renders via `templates/report-shell.html` (HTML default), with `scripts/build_pdf.py`, `scripts/build_pptx.py`, or `scripts/build_csv.py` available as alternative output formats offered after the HTML.

## Data needs

- Single period: last 90 days (campaigns need long tails)
- Filter to entries where utm_campaign matches the requested campaign
- Aggregate: daily volume, creative mix (utm_content), landing page mix, lead quality distribution

**Prior period required:** no

This report uses a single-period pull only. Do NOT run a second `get_entries` call — see `references/rendering-pipeline.md` on skipping the prior-period pull for non-delta reports.

## Section order

The report emits these sections, in this order:

**title-block**
: Kicker: "Campaign Deep Dive · [campaign name]". Title: `"*[campaign]* in detail."` Meta: date range, total leads, active days.

**stat-strip**
: 4 stats: total leads, leads per active day, top ad creative leads, top landing page leads.

**chart**
: Area: daily lead volume for this campaign with weekly rolling average overlay.

**chart-insight**
: Bar-horizontal: top 5 creatives within the campaign. Insight card names the winning creative.

**ranked-list**
: Top 10 leads in the campaign with columns: date, email (truncated), company, source·medium, score (if available).

**insight-card**
: Kicker "The arc". Title summarizing the campaign's trajectory (ramping, peaked, declining).

**recommendations**
: 3 actions specific to this campaign's state (extend, pause, refresh creative, expand budget, etc.).

**closing**
: Title: `"One *campaign*, fully seen."`


## Voice guidance

Intimate and specific. This is the one report where we get narrative — the campaign has an arc, a personality, a story.

## What never changes

- Report uses the shared two-tone card language across every container.
- Every title has at most ONE `*word*` italic accent, rendered as italic brand-primary.
- Never invent new section types per report — stick to the 10 in `template-schema.md`.
- After delivering the HTML, offer PDF / PPTX / CSV as a one-line follow-up (see `SKILL.md` Rule 2).
