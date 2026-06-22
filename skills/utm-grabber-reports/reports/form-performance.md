# Form Performance

## Triggers

- `/forms`
- `form performance`
- `which forms`
- `form submissions`

## Purpose

Ranks forms by submission volume when multiple forms exist. Answers "which forms are worth keeping, improving, or killing?"

## Before you build

1. Read `references/design-contract.md` — the two-tone house style, italic-accent rule, forbidden patterns.
2. Read `scripts/template-schema.md` — section type reference.
3. Read `references/rendering-pipeline.md` — MCP strategy and tool-call budgets.

The final deliverable renders via `templates/report-shell.html` (HTML default), with `scripts/build_pdf.py`, `scripts/build_pptx.py`, or `scripts/build_csv.py` available as alternative output formats offered after the HTML.

## Data needs

- Single period: last 30 days
- Requires multiple form_ids — if only one form, note this and summarize it instead
- Aggregation: group by form_id, join with form metadata from `list_forms`

**Prior period required:** no

This report uses a single-period pull only. Do NOT run a second `get_entries` call — see `references/rendering-pipeline.md` on skipping the prior-period pull for non-delta reports.

## Section order

The report emits these sections, in this order:

**title-block**
: Kicker: "Form Performance · [date range]". Title: `"Which *forms* earn their keep."` Meta: forms tracked, total subs, period.

**stat-strip**
: 3 stats: forms active, top form submissions, avg submissions per form.

**ranked-list**
: All active forms with columns: rank, form name, submissions, top source.

**insight-card**
: Kicker "Distribution". Title naming the concentration pattern (e.g., `"*One form* handles 70% of submissions."`)

**recommendations**
: 3 actions based on pattern: simplify lowest-converter, duplicate best-converter at new touchpoint, add tracking to any forms with zero submissions.

**closing**
: Title: `"Keep what *works*."`


## Voice guidance

Operational. Forms either earn their place in the site or they don't. Recommendations reference form UX and placement.

## What never changes

- Report uses the shared two-tone card language across every container.
- Every title has at most ONE `*word*` italic accent, rendered as italic brand-primary.
- Never invent new section types per report — stick to the 10 in `template-schema.md`.
- After delivering the HTML, offer PDF / PPTX / CSV as a one-line follow-up (see `SKILL.md` Rule 2).
