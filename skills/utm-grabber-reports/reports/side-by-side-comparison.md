# Side-by-Side Comparison

## Triggers

- `/compare`
- `compare`
- `vs`
- `X vs Y`
- `side by side`

## Purpose

Compares two entities on equivalent metrics: two campaigns, two sources, two periods, two landing pages, two CRMs. Answers "which is working better and by how much?"

## Before you build

1. Read `references/design-contract.md` — the two-tone house style, italic-accent rule, forbidden patterns.
2. Read `scripts/template-schema.md` — section type reference.
3. Read `references/rendering-pipeline.md` — MCP strategy and tool-call budgets.

The final deliverable renders via `templates/report-shell.html` (HTML default), with `scripts/build_pdf.py`, `scripts/build_pptx.py`, or `scripts/build_csv.py` available as alternative output formats offered after the HTML.

## Data needs

- Two subjects: parse from user request (e.g., "compare Q1-Search vs Q1-Display")
- Filter entries to each subject separately
- Compute same metrics for both sides: volume, daily avg, top source, hygiene, conversion quality

**Prior period required:** no

This report uses a single-period pull only. Do NOT run a second `get_entries` call — see `references/rendering-pipeline.md` on skipping the prior-period pull for non-delta reports.

## Section order

The report emits these sections, in this order:

**title-block**
: Kicker: "Side-by-Side · [subject A] vs [subject B]". Title: `"The *verdict* is in."` Meta: period, leads A, leads B.

**stat-strip**
: 2 stats per side (4 total): leads A, leads B, avg A, avg B. Use grouped visual rhythm.

**chart**
: Bar-grouped: metrics side-by-side (leads, leads/day, hygiene %, top-source share). Two bars per metric.

**insight-card**
: Kicker "The winner". Title: `"*[Subject A]* wins on volume. *[Subject B]* wins on quality."` Body: split decision explained.

**ranked-list**
: Top 5 differences with columns: metric, A value, B value, delta, winner.

**recommendations**
: 3 actions: what to learn from the winner, what to salvage from the loser, which test to run next.

**closing**
: Title: `"The *better* bet, clearly."`


## Voice guidance

Judicial. No hedging — name the winner on each metric. If it's a split decision, say so and rank the metrics by importance.

## What never changes

- Report uses the shared two-tone card language across every container.
- Every title has at most ONE `*word*` italic accent, rendered as italic brand-primary.
- Never invent new section types per report — stick to the 10 in `template-schema.md`.
- After delivering the HTML, offer PDF / PPTX / CSV as a one-line follow-up (see `SKILL.md` Rule 2).
