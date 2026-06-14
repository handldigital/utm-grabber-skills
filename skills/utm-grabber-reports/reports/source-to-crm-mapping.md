# Source to CRM Mapping

## Triggers

- `/source-crm`
- `source to crm`
- `crm by source`
- `which sources feed which crms`

## Purpose

Cross-tabs traffic sources against declared CRM platforms. Answers "which of my sources bring customers who use which CRMs?" Useful for B2B tool vendors.

## Before you build

1. Read `references/design-contract.md` — the two-tone house style, italic-accent rule, forbidden patterns.
2. Read `scripts/template-schema.md` — section type reference.
3. Read `references/rendering-pipeline.md` — MCP strategy and tool-call budgets.

The final deliverable renders via `templates/report-shell.html` (HTML default), with `scripts/build_pdf.py`, `scripts/build_pptx.py`, or `scripts/build_csv.py` available as alternative output formats offered after the HTML.

## Data needs

- Single period: last 30 days
- Require a `crm` form field in entries
- Group by (utm_source, crm) → count leads in each cell

**Prior period required:** no

This report uses a single-period pull only. Do NOT run a second `get_entries` call — see `references/rendering-pipeline.md` on skipping the prior-period pull for non-delta reports.

## Section order

The report emits these sections, in this order:

**title-block**
: Kicker: "Source to CRM Mapping · [date range]". Title: `"Which *sources* bring which CRMs."` Meta: sources, CRMs declared, period.

**stat-strip**
: 3 stats: sources active, CRMs declared, top pairing leads.

**chart**
: Bar-stacked: top 5 sources × top CRMs. Each source is a bar segmented by CRM.

**ranked-list**
: Top source-CRM pairings with columns: rank, source, CRM, leads, % of that CRM's total.

**insight-card**
: Kicker "Match-making". Title: the clearest signal (e.g., `"*HubSpot* users come from LinkedIn. *Salesforce* from paid search."`)

**recommendations**
: 3 actions: target messaging to dominant CRM per channel, test CRM-specific landing pages, suppress offers for mismatched CRMs.

**closing**
: Title: `"Personalize by *CRM*."`


## Voice guidance

B2B sophistication. Understand that CRM usage signals company maturity, budget, and stack preference.

## What never changes

- Report uses the shared two-tone card language across every container.
- Every title has at most ONE `*word*` italic accent, rendered as italic brand-primary.
- Never invent new section types per report — stick to the 10 in `template-schema.md`.
- After delivering the HTML, offer PDF / PPTX / CSV as a one-line follow-up (see `SKILL.md` Rule 2).
