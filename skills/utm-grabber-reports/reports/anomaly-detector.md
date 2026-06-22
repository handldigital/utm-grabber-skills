# Anomaly Detector

## Triggers

- `/anomaly`
- `anomalies`
- `what changed`
- `sudden drop`
- `spike`

## Purpose

Surfaces channels, campaigns, or sources whose lead volume has changed dramatically vs their 30-day baseline. Answers "what shifted in the last week and should I care?"

## Before you build

1. Read `references/design-contract.md` — the two-tone house style, italic-accent rule, forbidden patterns.
2. Read `scripts/template-schema.md` — section type reference.
3. Read `references/rendering-pipeline.md` — MCP strategy and tool-call budgets.

The final deliverable renders via `templates/report-shell.html` (HTML default), with `scripts/build_pdf.py`, `scripts/build_pptx.py`, or `scripts/build_csv.py` available as alternative output formats offered after the HTML.

## Data needs

- Current period: last 7 days
- Baseline: last 30 days (to compute rolling average per channel)
- Compute per-channel z-score or % deviation from baseline
- Flag anomalies: > 2 stddev up/down, or > 50% change in volume from baseline

**Prior period required:** no

This report uses a single-period pull only. Do NOT run a second `get_entries` call — see `references/rendering-pipeline.md` on skipping the prior-period pull for non-delta reports.

## Section order

The report emits these sections, in this order:

**title-block**
: Kicker: "Anomaly Detector · Last 7 days". Title: `"What *changed* this week."` Meta: baseline window, period, anomaly count.

**stat-strip**
: 3 stats: anomalies detected, largest drop %, largest spike %.

**insight-card**
: Kicker "Headline anomaly". Title: the single biggest change (e.g., `"*Facebook ads* dropped 62% vs baseline."`) Body: what a marketer should immediately check.

**ranked-list**
: All detected anomalies with columns: rank, channel/source/campaign, baseline avg, current, delta %, state (rising/cooling/cold).

**section-header**
: Number "02". Kicker "What to investigate". Title: `"Where to *look*."`

**recommendations**
: 4 investigation paths for the top anomalies: check ad account status, review budget changes, examine creative approval queue, verify pixel fires. Not fixes — *investigations*.

**closing**
: Title: `"Run this *daily* during volatile weeks."` Body: suggest the monthly review for context.


## Voice guidance

Urgent but calm. Distinguish "investigation needed" from "proven problem". Never blame a channel without data.

## What never changes

- Report uses the shared two-tone card language across every container.
- Every title has at most ONE `*word*` italic accent, rendered as italic brand-primary.
- Never invent new section types per report — stick to the 10 in `template-schema.md`.
- After delivering the HTML, offer PDF / PPTX / CSV as a one-line follow-up (see `SKILL.md` Rule 2).
