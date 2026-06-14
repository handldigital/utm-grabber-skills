# Period-over-Period Comparisons

Every metric in every report carries a period comparison — "+12% vs last 30 days", "−8% vs prior week", or "first-month data, no comparison available". This is a universal feature, not a separate report. Load this file when building any report to get the comparison math right.

## Why this matters

A static number is a snapshot. A delta is a story. "500 leads" is data; "500 leads, +12% vs last month" is a finding. Every serious attribution tool shows deltas — this turns ours from descriptive to diagnostic.

## The comparison windows

For every report's primary time window, compute a matching comparison window immediately prior:

| Primary window | Comparison window |
|---|---|
| Last 7 days | The 7 days before that (days 8–14 ago) |
| Last 30 days | The 30 days before that (days 31–60 ago) |
| Last 90 days | The 90 days before that (days 91–180 ago) |
| This month (calendar) | Last calendar month |
| This quarter | Last quarter |
| YTD | Prior YTD (same days last year) |
| Custom range | Immediately prior span of the same length |

## How to compute

### One extra MCP call per report

After the main `get_entries` call, make a second call with the comparison window's start/end:

```
get_entries(plugin, [form_id], start=comparison_start, end=comparison_end, limit=0)
```

Compute the same transformations on the comparison data. Now every metric has a `current` and `prior` pair.

### Delta formatting

```
delta_pct = (current - prior) / prior × 100
```

Rules:

- If `prior == 0` and `current > 0` → show "new" instead of an infinite percentage.
- If `current == 0` and `prior > 0` → show "−100%" or "dropped to zero".
- If both are zero → show "no activity either period".
- If delta is less than ±3% → show "flat" instead of a number (avoid noise).

### Materiality threshold

Only highlight deltas that are BOTH:
1. At least ±10% in relative terms
2. At least 5 leads in absolute terms (ignore trivial swings in small numbers)

Below that threshold, show the number but don't highlight or editorialize.

## Visual treatment

### In stat cards

Below the big number, show a small delta pill:

```
    500 leads
    +12% vs last 30 days  ← green if up, red if down, grey if flat
```

Pill colour rules:
- `--b-accent` (bright blue) or a green `#30B47A`: positive when up is good (lead volume, coverage)
- A red (`#c4353a`): negative when down is bad
- `--b-muted`: flat or when direction is neutral (paid share — could be good or bad depending on strategy)

### In line charts

Add a light grey ghost line showing the comparison window's series. Label it "prior period". Makes trends visible at a glance.

### In tables

Add a Δ column at the end showing the delta per row:

| Source | Leads | Δ vs prior |
|---|---|---|
| Google | 143 | +28 (+24%) |
| Facebook | 47 | −6 (−11%) |
| Linkedin | 45 | +18 (+67%) |

## Narrative integration

The period comparison should show up in the insight text whenever it meaningfully changes the story:

**Without comparison (static):**
> Google is your top source this month with 143 leads.

**With comparison (dynamic):**
> Google is your top source this month with 143 leads — up 24% from last month's 115.

**When comparison reveals the real story:**
> Paid volume is up 8% overall, but the mix shifted: Google/CPC up 24%, LinkedIn/paid_social down 11%. Budget is following clicks even if totals look steady.

## When to omit comparisons

- First 30 days of a customer's data (no prior data exists)
- When the customer just changed something major (ad budget shift, tagging system change) that invalidates the comparison — flag this in the footer
- When comparison would mislead more than inform (e.g., campaign just launched, so prior period is zero)

In these cases, omit the delta and add a small note:

> Comparison not available — data coverage starts {date}.

## Special case: year-over-year

For long-running customers (12+ months of data), offer Y/Y as an additional comparison on demand:

- "Show me this month vs same month last year"
- Requires a third MCP call spanning the same window 12 months prior
- Should be opt-in — don't auto-include to avoid bloating every report

## Implementation note

The HTML template (`templates/report-shell.html`) should be updated to carry optional `prior` values alongside every metric. The renderer reads:

```json
{
  "totals": {
    "total_leads": 500,
    "total_leads_prior": 446,
    "total_leads_delta_pct": 12,
    "total_leads_delta_display": "+12%"
  }
}
```

If `_prior` is absent, the renderer hides the delta pill. If `_prior` is present, it shows.
