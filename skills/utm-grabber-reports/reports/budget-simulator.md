# Budget Simulator

## Triggers

- `/budget-simulator`
- `budget simulator`
- `what if budget`
- `reallocate spend`

## Purpose

Models the lead outcome of reallocating spend between channels. Answers "what if I moved 20% from Google to Facebook — what would leads look like?"

## Before you build

1. Read `references/design-contract.md` — the two-tone house style, italic-accent rule, forbidden patterns.
2. Read `scripts/template-schema.md` — section type reference.
3. Read `references/rendering-pipeline.md` — MCP strategy and tool-call budgets.

The final deliverable renders via `templates/report-shell.html` (HTML default), with `scripts/build_pdf.py`, `scripts/build_pptx.py`, or `scripts/build_csv.py` available as alternative output formats offered after the HTML.

## Data needs

- Single period: last 90 days (for stable per-channel rates)
- Require user to state the reallocation (can default to simulations)
- Compute per-channel lead-per-spend rate (if spend is known) or lead-per-day baseline
- Apply reallocation multiplier to each channel's baseline

**Prior period required:** no

This report uses a single-period pull only. Do NOT run a second `get_entries` call — see `references/rendering-pipeline.md` on skipping the prior-period pull for non-delta reports.

## Section order

The report emits these sections, in this order:

**title-block**
: Kicker: "Budget Simulator · Last 90 days baseline". Title: `"What *if* you moved spend?"` Meta: channels modeled, baseline period, scenario.

**stat-strip**
: 3 stats: baseline leads/month, projected leads under scenario, net delta.

**chart**
: Bar-grouped: current baseline vs scenario per channel. Labels clearly say "baseline" and "scenario".

**insight-card**
: Kicker "Caveat". Title: `"This assumes *linear* scaling."` Body: explain diminishing returns, saturation, and that the sim is a first-order estimate.

**ranked-list**
: Per-channel: current leads, projected leads, delta, risk flag (high if budget moves > 30%).

**recommendations**
: 3 actions: the directional change to try first, how to test it safely in 2 weeks, what to measure to validate.

**closing**
: Title: `"Model it, then *test* it."`


## Voice guidance

Cautious-analyst. Every projection is a guess. Always name the assumptions. Never present sim numbers without caveats.

## What never changes

- Report uses the shared two-tone card language across every container.
- Every title has at most ONE `*word*` italic accent, rendered as italic brand-primary.
- Never invent new section types per report — stick to the 10 in `template-schema.md`.
- After delivering the HTML, offer PDF / PPTX / CSV as a one-line follow-up (see `SKILL.md` Rule 2).
