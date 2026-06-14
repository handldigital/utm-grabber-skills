# Custom Report Builder

Handles the long tail of unique, specific reports customers want. When the question is too specific for Q&A mode but doesn't match a canned report in the catalog.

Example request: "Build me a report showing HubSpot leads by campaign for the last 90 days, grouped by Monthly Ad Spend bracket, comparing Q1 to Q4."

No canned report handles that exact shape. The custom builder does.

## When to use this mode

Trigger the custom builder when:

1. The user's request is more elaborate than a single Q&A question (wants multiple dimensions, comparisons, or slides).
2. No canned report in `reports/` cleanly matches the request.
3. The user uses phrases like "build me", "custom report", "I want a report that shows", "create a deck on".

## The workflow

### Step 1: Parse the request into a structured spec

Before touching the MCP, decompose the request into:

```
spec = {
  subject: "HubSpot leads",
  filter: { CRM_Platform: "HubSpot" },
  group_by: ["utm_campaign", "Monthly_Ad_Spend"],
  time_range: "last 90 days",
  compare_to: "previous 90 days",
  slides_desired: ["overview", "by_campaign", "by_spend_bracket", "comparison", "recommendations"]
}
```

Confirm this spec back to the user in plain English in ONE short message:

> I'll build a report covering:
> - HubSpot-only leads from the last 90 days
> - Broken down by campaign and monthly ad spend bracket
> - Compared to the prior 90 days
>
> Shall I proceed?

If they say yes, run. If they want changes, adjust the spec and re-confirm.

### Step 2: Pull the data

Make standard MCP calls scoped to the time range. Filter entries client-side on the customer's chosen filter (CRM Platform = HubSpot in the example).

### Step 3: Transform per the grouping spec

Apply the grouping. For each group, compute the standard aggregates (count, share, top source, trend). If the user wants period comparisons, repeat the pull for the comparison window and compute deltas.

### Step 4: Render

Use the slide template shell but pick slide types à la carte based on the spec's `slides_desired`. Don't force a full 10-slide deck — 5–7 custom slides is usually right. Each slide should answer one of the dimensions in the spec.

Save to `/mnt/user-data/outputs/custom-{subject-slug}-{YYYY-MM-DD}.html` + .pdf.

## Principles

### 1. Don't over-interpret

If the user says "group by campaign", don't also group by source, medium, and week. Build exactly what they asked for, nothing more. If you think they'd benefit from another dimension, suggest it at the end — don't insert it.

### 2. Confirm before running

Always echo the spec and ask for confirmation. This prevents 10 minutes of work on the wrong report.

### 3. Reuse canned report components

If the user's request is 80% a canned report, start from that canned report's instructions and modify. E.g., a custom request for "campaign leaderboard but only HubSpot leads" should reuse the Top Campaign Leaderboard transformations with an added filter — not build from scratch.

### 4. Tell the user what's missing

If the request asks for data we don't have (ad spend, CPA, ROAS in Phase 1), say so in the confirmation step BEFORE pulling any data:

> You asked for cost-per-lead by campaign. We don't currently have ad spend data — that'll be in the Phase 2 ad platform connectors. I can build the rest of your report (leads by campaign, quality by campaign), but the cost column will be blank. Shall I proceed?

### 5. Name the output clearly

The custom report filename should reflect the custom spec so the user can find it later. "custom-hubspot-campaigns-vs-q4-2026-04-18.html" is better than "custom-report-2026-04-18.html".

## Capability boundaries

The custom builder can combine these building blocks:

- **Filters** on any form field or UTM field
- **Groupings** by any categorical field
- **Time ranges** — absolute, relative, or side-by-side periods
- **Metrics** — count, share %, avg (on numeric form fields), trend
- **Comparisons** — period-over-period, group-vs-group, source-vs-source

It CANNOT:
- Apply machine-learning clustering (no k-means, no LDA)
- Enrich with external data (no Clearbit, no industry lookup)
- Write SQL-style joins across different MCPs (agency-rollup is a separate special case)
- Forecast beyond one period (that's the Forecast report)

If the user asks for something outside these boundaries, say so and offer the nearest canned alternative.

## Example end-to-end

**User:** Build me a report showing HubSpot vs Salesforce leads by campaign for the last 90 days, with a quality comparison.

**Builder response (spec confirmation):**
> Here's what I'll build:
>
> 1. Cover + overview
> 2. HubSpot campaigns leaderboard (top 10 by volume, last 90 days)
> 3. Salesforce campaigns leaderboard (top 10 by volume, last 90 days)
> 4. Head-to-head: campaigns that appear in both, with relative performance
> 5. Quality comparison: Monthly Ad Spend distribution, HubSpot vs Salesforce
> 6. Recommendations
>
> One caveat: I don't have cost or CPA data — we're comparing volume and form-declared spend brackets, not dollar-for-dollar CAC. Proceed?

**User:** Yes.

**Builder:** Runs MCP pulls, builds the 6-slide HTML, saves, presents.
