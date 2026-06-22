# Lead Profile Enrichment

## Triggers

- `/lead`
- `tell me about`
- `lead profile`
- `who is`
- `lead enrichment`

## Purpose

Full attribution history for a single lead — every touchpoint, every UTM parameter, every form field. Answers "who is this lead and how did they actually get here?"

## Before you build

1. Read `references/design-contract.md` — the two-tone house style, italic-accent rule, forbidden patterns.
2. Read `scripts/template-schema.md` — section type reference.
3. Read `references/rendering-pipeline.md` — MCP strategy and tool-call budgets.

The final deliverable renders via `templates/report-shell.html` (HTML default), with `scripts/build_pdf.py`, `scripts/build_pptx.py`, or `scripts/build_csv.py` available as alternative output formats offered after the HTML.

## Data needs

- Filter: single email or entry ID from the user
- Return ALL entries for that email across history, plus the enriched profile (company, titles, declared spend, CRM)
- If multiple sessions: show first-touch and last-touch separately

**Prior period required:** no

This report uses a single-period pull only. Do NOT run a second `get_entries` call — see `references/rendering-pipeline.md` on skipping the prior-period pull for non-delta reports.

## Section order

The report emits these sections, in this order:

**title-block**
: Kicker: "Lead Profile · [redacted email]". Title: `"Who *they* are."` Meta: first seen, last seen, total touchpoints.

**stat-strip**
: 4 stats: touchpoints, days active, forms submitted, declared spend (if any).

**insight-card**
: Kicker "First touch". Title: where they came from originally (e.g., `"Found you via *LinkedIn* ad, 47 days ago."`) Body: their first landing page and UTMs.

**ranked-list**
: Every touchpoint chronologically with columns: date, source·medium, campaign, landing page, form.

**insight-card**
: Kicker "Declared context". Title: synthesizing their form answers (spend bracket, CRM, urgency, company type).

**recommendations**
: 2 actions: what to say on the sales call given the attribution path, which CRM fields to pre-fill from the data.

**closing**
: Title: `"Ready for *your* outreach."` Body: offer CSV export of just this lead's history.


## Voice guidance

Sales-rep-ready. A human, not a row in a spreadsheet. Privacy: always mask/truncate emails in shown output.

## What never changes

- Report uses the shared two-tone card language across every container.
- Every title has at most ONE `*word*` italic accent, rendered as italic brand-primary.
- Never invent new section types per report — stick to the 10 in `template-schema.md`.
- After delivering the HTML, offer PDF / PPTX / CSV as a one-line follow-up (see `SKILL.md` Rule 2).
