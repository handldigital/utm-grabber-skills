# Predictive Forecast

## Triggers

- `/forecast`
- `forecast`
- `predict`
- `next month`
- `projected leads`

## Purpose

Forecasts the next 30 days of leads based on the last 90 days of history. Answers "what should I expect next period, and where are the upside/downside risks?"

## Before you build

1. Read `references/design-contract.md` — the two-tone house style, italic-accent rule, forbidden patterns.
2. Read `scripts/template-schema.md` — section type reference.
3. Read `references/rendering-pipeline.md` — MCP strategy and tool-call budgets.

The final deliverable renders via `templates/report-shell.html` (HTML default), with `scripts/build_pdf.py`, `scripts/build_pptx.py`, or `scripts/build_csv.py` available as alternative output formats offered after the HTML.

## Data needs

- Current baseline: last 90 days of entries (longer history = better forecast)
- Aggregations: `compute_daily_volume` (for trend), `compute_channel_mix`, `compute_source_leaderboard`
- Forecast math: rolling 30-day average × seasonality factor (day-of-week). Keep methodology simple — do not claim ML unless actual ML is used.

**Prior period required:** no

This report uses a single-period pull only. Do NOT run a second `get_entries` call — see `references/rendering-pipeline.md` on skipping the prior-period pull for non-delta reports.

## Section order

The report emits these sections, in this order:

**title-block**
: Kicker: "Predictive Forecast · Next 30 days". Title: `"Your *projected* pipeline."` Meta: baseline window, data points, confidence.

**hero-number**
: Kicker "Projected leads · next 30 days". Value: the headline forecast (e.g., "485"). Label: "±12% range based on your last 90 days of history."

**chart**
: Line chart: historical (solid, muted color) transitioning into projected (dashed or lighter, brand primary). X-axis: day index.

**insight-card**
: Kicker "What this assumes". Title: `"Your *trend* is the dominant signal."` Body: the assumptions (stable mix, no major campaign changes, day-of-week seasonality applied).

**recommendations**
: 4 what-ifs: if you increase top channel spend 20%, expect X; if top campaign fatigues, expect Y; etc. Actionable, not academic.

**closing**
: Title: `"Plan *for* the likely path."` Body: offer to re-run with specific changes.


## Voice guidance

Humble about prediction limits. Use "projected" and "estimated" — never "will". Always give a range, never a single number without bounds.

## What never changes

- Report uses the shared two-tone card language across every container.
- Every title has at most ONE `*word*` italic accent, rendered as italic brand-primary.
- Never invent new section types per report — stick to the 10 in `template-schema.md`.
- After delivering the HTML, offer PDF / PPTX / CSV as a one-line follow-up (see `SKILL.md` Rule 2).
