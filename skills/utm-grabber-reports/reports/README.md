# Report specs · v0.8 section-based architecture

Every report in this directory follows the same architecture: it reads live UTM Grabber data, computes aggregations via `scripts/helpers.py`, emits a `sections` array matching `scripts/template-schema.md`, and renders through `templates/report-shell.html` (HTML), `scripts/build_pdf.py` (PDF), `scripts/build_pptx.py` (PPTX), or `scripts/build_csv.py` (CSV).

## Shared pattern

Every report spec in this directory includes:

1. **Purpose** — one or two sentences describing when to run this report and what question it answers.
2. **Data needs** — which MCP fields are required, which aggregation helpers to use, whether a prior period is needed.
3. **Section order** — the `sections` array structure (which section types in which order, with example content).
4. **Voice guidance** — recommended headline patterns, what to emphasize in insight cards, what tone to keep in recommendations.

Claude reads the relevant report spec after routing from SKILL.md's decision tree. The spec tells it the *shape* of the output; `design-contract.md` governs the *look*. Both are mandatory.

## Before building any report

1. Read `references/design-contract.md` — defines the two-tone house style, italic-accent rule, color tokens, forbidden patterns.
2. Read `scripts/template-schema.md` — defines every section type's expected fields.
3. Read the relevant report spec (this directory).
4. Read `references/rendering-pipeline.md` — defines the MCP pull strategy, caching, and tool-call budgets.

## Output formats

Every report spec produces an HTML deliverable by default. After delivering HTML, offer PDF/PPTX/CSV as one-line follow-ups per `SKILL.md` Rule 2.

## Spec index

**Period-over-period reports** (need prior-period pull for deltas):
- `monthly-performance-review.md` — the 30-day executive summary
- `weekly-executive-summary.md` — the 7-day one-pager
- `predictive-forecast.md` — baseline-driven lead forecast for next period

**Audit and quality reports** (single period):
- `utm-hygiene-audit.md` — attribution leak detection
- `anomaly-detector.md` — channel-level anomaly surfacing
- `lead-quality-scorer.md` — declared-intent ranking across all leads

**Ranked leaderboards** (single period, feature ranked-list):
- `top-campaign-leaderboard.md` — best-performing campaigns
- `landing-page-performance.md` — attribution by URL
- `form-performance.md` — submission rates by form
- `ad-creative-performance.md` — by utm_content
- `keyword-performance.md` — by utm_term
- `source-to-crm-mapping.md` — source × CRM matrix

**Deep dives and profiles** (subject-specific):
- `campaign-deep-dive.md` — all leads + stats for one campaign
- `lead-profile-enrichment.md` — single-lead attribution history

**Comparisons and what-ifs**:
- `side-by-side-comparison.md` — two entities (campaigns, sources, periods) compared
- `paid-vs-organic.md` — the fundamental split
- `budget-simulator.md` — what-if spend reallocation

**Agency workflows**:
- `agency-client-rollup.md` — portfolio view across all brand profiles
