# Template Schema — v0.8.0

Every report is a JSON object with `meta` and `sections`. The template iterates `sections` in order and renders each using its `type`.

## Top-level structure

```json
{
  "meta": {
    "customer_name": "Acme Co",
    "customer_domain": "acme.example.com",
    "brand_profile": { ... },
    "skill_version": "0.8.0",
    "generated_at": "2026-04-20T18:30:00Z"
  },
  "sections": [ ... ]
}
```

### `meta.brand_profile`

```json
{
  "company_name": "Acme Co",
  "logo": { "type": "text" | "url" | "upload", "value": "..." },
  "colors": {
    "primary": "#0E8C6B",
    "accent":  "#5DBFA0",
    "ink":     "#0B1F1A",
    "muted":   "#5A6B64",
    "surface": "#F0F8F5"
  }
}
```

Logo `type`:
- `"text"` — `value` is HTML, rendered as-is inside the logo slot. Use for text-based wordmarks.
- `"url"` — `value` is a URL to an image. Rendered as `<img src="...">`.
- `"upload"` — `value` is a base64-encoded PNG. Rendered as `<img src="data:image/png;base64,...">`.

## Section types

### 1. `title-block`

The hero of the report. Always the first section.

```json
{
  "type": "title-block",
  "kicker": "Monthly Performance Review · Mar 20 – Apr 19, 2026",
  "title": "Your *attribution* picture.",
  "meta_bits": ["acme.example.com", "Gravity Forms", "490 submissions", "30 days"]
}
```

Rules:
- `title` must contain exactly one `*word*` fragment — the italic accent
- `kicker` is a single line, mono uppercase, brand-primary color
- `meta_bits` is an array of short strings, rendered with `·` separators

### 2. `stat-strip`

2, 3, or 4 two-tone stat cards in a row.

```json
{
  "type": "stat-strip",
  "stats": [
    { "value": "490", "label": "Leads captured", "delta_label": "+12%", "delta_direction": "up" },
    { "value": "16.3", "label": "Leads per day" },
    { "value": "51%", "label": "Paid traffic", "delta_label": "+3pt", "delta_direction": "up" },
    { "value": "58%", "label": "UTM coverage", "delta_label": "−6pt", "delta_direction": "down" }
  ]
}
```

Rules:
- `value` is rendered as italic serif. Format as a string ("490", "51%", "16.3").
- `label` is rendered as uppercase mono kicker.
- `delta_label` + `delta_direction` are optional. Direction is `"up" | "down" | "flat"`.
- Use 2, 3, or 4 stats. More than 4 breaks the layout.

### 3. `section-header`

A divider between major content areas in a long report. Not a full card — just typography.

```json
{
  "type": "section-header",
  "number": "03",
  "kicker": "Volume Trend",
  "title": "Daily *rhythm* of leads."
}
```

Rules:
- `number` is a zero-padded string (`"01"`, `"02"`).
- `title` follows the italic-accent rule.

### 4. `hero-number`

A big, centered metric — the entire section is one two-tone card.

```json
{
  "type": "hero-number",
  "kicker": "Your hygiene score",
  "value": "58%",
  "label": "of your leads arrive with a fully-tagged UTM trio. The other 42% are missing attribution data."
}
```

Rules:
- `value` is rendered as huge italic serif (144px). Keep short — a single number or percentage.
- `label` is a short descriptive sentence. Body font.

### 5. `chart`

A full-width chart with caption. No insight card alongside.

```json
{
  "type": "chart",
  "chart": { "type": "area", "labels": [...], "values": [...] },
  "caption": "Peak of 29 on Apr 10 · daily avg 16.3"
}
```

See "Chart types" below.

### 6. `chart-insight`

Chart on left 60%, two-tone insight card on right 40%.

```json
{
  "type": "chart-insight",
  "chart": { "type": "doughnut", "labels": [...], "values": [...], "unit": "%" },
  "caption": "Share of form submissions by last-touch source",
  "insight_kicker": "The mix",
  "insight_title": "Paid is *51%* of the funnel.",
  "insight_body": [
    "Paid marketing is the dominant engine, but organic and direct provide mid-funnel stability.",
    "Watch for concentration risk — top three sources account for 68% of paid volume."
  ]
}
```

### 7. `ranked-list`

A tabular list with column schema. Header row uses brand surface tint.

```json
{
  "type": "ranked-list",
  "columns": [
    { "key": "rank",     "label": "#",         "type": "rank",        "width": "48px" },
    { "key": "campaign", "label": "Campaign",  "type": "name" },
    { "key": "source",   "label": "Source",    "type": "source",      "width": "180px" },
    { "key": "leads",    "label": "Leads",     "type": "number",      "align": "right", "width": "90px" },
    { "key": "trend",    "label": "Trend",     "type": "trend",       "width": "130px" }
  ],
  "rows": [
    { "rank": "1", "campaign": "Q1 Reactivation Search", "source": "google · cpc",
      "leads": "40", "trend": { "state": "steady", "label": "→ Steady" } },
    ...
  ]
}
```

Column types:
- `rank` — large serif numeral, muted
- `name` — primary body, 500 weight
- `source` — mono, 13px, muted (for source·medium, URLs)
- `number` — large serif number
- `mono-number` — mono font numeric (for counts, averages)
- `trend` — trend pill with state `"steady" | "rising" | "cooling" | "cold"` and a label like `"→ Steady"`

### 8. `recommendations`

2×2 grid of two-tone action cards.

```json
{
  "type": "recommendations",
  "items": [
    { "label": "Action 01", "title": "Fix UTM tagging on top landing pages",
      "body": "42% of leads arrive without a full UTM trio. Audit top 5 referring pages and add missing tags." },
    ...
  ]
}
```

Rules:
- Always 4 items (renders a 2×2 grid).
- `label` is short mono caps (e.g., "Action 01", "Fix 01 · Today", "Week 1").
- `title` follows the italic-accent rule.

### 9. `insight-card`

A standalone two-tone callout between sections. Used when you need to surface a key finding without attaching it to a chart.

```json
{
  "type": "insight-card",
  "kicker": "What this says",
  "title": "*Q1 Reactivation Search* is carrying the month.",
  "body": [
    "The top three campaigns account for most of the period's volume.",
    "Before your next budget cycle, audit the cold campaigns for creative fatigue."
  ]
}
```

### 10. `closing`

Always the last section. Short farewell with italic accent + helper text.

```json
{
  "type": "closing",
  "title": "That's *your* month.",
  "body": "Need a specific follow-up? Ask for the hygiene audit, the forecast, or dive into any source."
}
```

## Chart types (used inside `chart` and `chart-insight`)

All chart objects have a `type` plus type-specific fields:

### `doughnut`
```json
{ "type": "doughnut", "labels": ["Paid", "Organic", ...], "values": [51, 22, ...], "unit": "%" }
```

### `bar-horizontal`
```json
{ "type": "bar-horizontal", "labels": [...], "values": [...], "x_title": "Leads" }
```

### `bar-vertical`
```json
{ "type": "bar-vertical", "labels": [...], "values": [...] }
```

### `bar-stacked`
```json
{
  "type": "bar-stacked",
  "labels": ["Google", "Facebook", "Linkedin", ...],
  "stacks": [
    { "label": "cpc", "values": [143, 0, 0, ...] },
    { "label": "paid social", "values": [0, 39, 37, ...] }
  ]
}
```

### `bar-grouped`
```json
{
  "type": "bar-grouped",
  "labels": ["Paid", "Organic", "Direct"],
  "groups": [
    { "label": "First touch", "values": [145, 82, 35] },
    { "label": "Last touch",  "values": [245, 28, 88] }
  ]
}
```

### `line` / `area`
```json
{ "type": "area", "labels": ["Mar 20", "Mar 21", ...], "values": [12, 18, 22, ...] }
```

## Safety

Every chart call is wrapped in try/catch. A missing or malformed chart section logs a warning and skips that one visual — it doesn't break subsequent sections. Missing `data-slot` fields render empty. Missing `sections` entries with unknown types are skipped silently.

Still — produce the complete schema every time. Skipping fields leaves blank blocks that look broken.
