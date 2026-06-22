# UTM Hygiene Audit

## Triggers

- `/audit`
- `hygiene audit`
- `utm audit`
- `tagging audit`
- `attribution leaks`

## Purpose

Finds broken UTM tagging — leads arriving with click IDs but no UTM parameters (untagged ad URLs), or organic/referral traffic without tracking. Answers "where is my attribution leaking and which fixes are highest-impact?"

## Before you build

1. Read `references/design-contract.md` — the two-tone house style, italic-accent rule, forbidden patterns.
2. Read `scripts/template-schema.md` — section type reference.
3. Read `references/rendering-pipeline.md` — MCP strategy and tool-call budgets.

The final deliverable renders via `templates/report-shell.html` (HTML default), with `scripts/build_pdf.py`, `scripts/build_pptx.py`, or `scripts/build_csv.py` available as alternative output formats offered after the HTML.

## Data needs

- Single period: last 30 days of entries
- Aggregations: `compute_hygiene_counts`, `compute_leaky_urls` (new helper to group leaks by source URL)
- Leak types: Paid with click ID but no UTM (gclid/fbclid/msclkid), Referrer with no UTM, Direct-with-referrer-mismatch

**Prior period required:** no

This report uses a single-period pull only. Do NOT run a second `get_entries` call — see `references/rendering-pipeline.md` on skipping the prior-period pull for non-delta reports.

## Section order

The report emits these sections, in this order:

**title-block**
: Kicker: "UTM Hygiene Audit · [date range]". Title: `"Where your *attribution* is leaking."` Meta: domain, form, "X submissions audited", period.

**hero-number**
: Kicker "Your hygiene score". Value: coverage % (e.g., "58%"). Label: "of your leads arrive with a fully-tagged UTM trio. The other X leads are missing attribution data."

**stat-strip**
: 4 stats: fully tagged count, attribution leaks count, paid platforms leaking count, pages to fix count.

**section-header**
: Number "01". Kicker "Leaky URLs". Title: `"Top *pages* losing attribution."`

**ranked-list**
: Top 5 URLs by leak count with columns: rank, source URL, leak count, leak type (× Paid gclid / ↘ Referrer / etc.). Use `type: trend` for leak-type column with state coloring.

**insight-card**
: Kicker "What this means". Title naming the total leaks lost per month. Body: explains paid vs referrer leak types in plain language.

**section-header**
: Number "02". Kicker "Fix Order". Title: `"What to fix *first*."`

**recommendations**
: 4 fixes ordered by impact: check ad URL templates, tag referral links, audit Meta URL params, re-run audit after fixes. Labels like "Fix 01 · Today", "Fix 02 · This week".

**closing**
: Title: `"Fix these and you'll *recover* attribution."` Body: emphasis on running monthly.


## Voice guidance

Diagnostic, not alarmist. Every leak type has a specific root cause. Recommendations always name the *action*, not the problem.

## What never changes

- Report uses the shared two-tone card language across every container.
- Every title has at most ONE `*word*` italic accent, rendered as italic brand-primary.
- Never invent new section types per report — stick to the 10 in `template-schema.md`.
- After delivering the HTML, offer PDF / PPTX / CSV as a one-line follow-up (see `SKILL.md` Rule 2).
