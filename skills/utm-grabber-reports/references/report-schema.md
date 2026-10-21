# Report schema v2 (all themes, all formats)

Every report is one JSON-able dict: `meta` + an ordered `sections` list. The same dict renders to HTML, PDF and PowerPoint in any theme:

```python
from build_report import build_report
build_report(summary, "/mnt/user-data/outputs/monthly-2026-10-05.html", theme="studio")   # or .pdf / .pptx
```

Recipes in `scripts/recipes_v2/` build these dicts. Never write HTML by hand.

v1 summaries (the 10 original section types) still render in every theme. v2 adds optional fields and 10 new section types.

---

## meta

```json
{
  "customer_name": "Northwind Dental",
  "customer_domain": "northwinddental.com",
  "brand_profile": { "company_name": "...", "logo": {...}, "colors": {...}, "theme": "studio" },
  "skill_version": "2.0.0",
  "generated_at": "2026-10-05T09:00:00Z",
  "compare_label": "August",                 // used in deltas: "Up 14% from August" / "vs August"
  "prepared_for": "Northwind Dental",        // agency white-label (optional)
  "prepared_by": "Brightline Agency",        // agency white-label (optional)
  "sources": [                               // data-source chips on the cover + footer
    {"name": "UTM Grabber", "detail": "1,186 leads"},
    {"name": "Google Ads", "detail": "$18,420 spend"}
  ],
  "theme": "studio",                         // optional override; else brand_profile.theme; else studio
  "paper": "letter"                          // PDF only: letter | a4
}
```

`connectors.sources_meta(utmg="1,186 leads", google_ads="$18,420 spend")` builds `sources`.

---

## Writing rules (enforced by `validate_v2.py`)

1. **One `*accent*` per title**, wrapping the meaningful noun the section is about. Never a year, date or bare number on its own. `"Paid is *51%* of the funnel."` is allowed because the number IS the subject; `"Your *2026* report"` is not.
2. **No em dashes anywhere.** Use a colon, a period or a comma. The renderer converts stray ones, but recipes must not emit them.
3. **Headlines lead with the outcome.** "September turned ad spend into $86K of revenue." beats "September revenue report."
4. **Closing titles are data-driven next steps**: `f"Next: move budget into *{best}*. It books patients at {cac} each."`
5. **Every number traces to data.** Recipes compute every figure from their inputs. No placeholders, no invented benchmarks.
6. Display values are pre-formatted strings (`"1,186"`, `"$23.27"`, `"3.1x"`, `"41%"`). Chart values are raw numbers.

---

## Section types

### title-block (always first)
```json
{"type": "title-block",
 "kicker": "Full-funnel performance · September 2026",   // "Report name · period"
 "title": "September turned *ad spend* into $86K of booked revenue.",
 "subtitle": "One or two sentences: the story of the period.",   // v2, optional
 "meta_bits": ["northwinddental.com", "Gravity Forms", "30 days"]}
```

### stat-strip (2 to 6 KPIs)
```json
{"type": "stat-strip", "stats": [
  {"label": "Leads", "value": "1,186", "delta_label": "+14%", "delta_direction": "up",
   "spark": [31, 38, 44, ...],     // v2: 8-30 points, oldest first
   "good": "up",                   // v2: "up" (default) | "down" (costs) | "neutral"
   "source": "UTM Grabber",        // v2: which platform the number comes from
   "note": "vs 1,040 in August"}   // v2: small context line
]}
```
`delta_direction` is the direction of change; `good` says whether up is good. Cost per lead going down is `{"delta_direction": "down", "good": "down"}` and renders green.

### hero-number
```json
{"type": "hero-number", "kicker": "Revenue per $1 of ad spend", "value": "$3.10",
 "label": "Up from $2.70 in August.", "delta_label": "+$0.40", "delta_direction": "up",
 "spark": [2.1, 2.3, 2.7, 3.1]}
```

### section-header
```json
{"type": "section-header", "number": "01", "kicker": "The funnel",
 "title": "From *visit* to booked patient.", "dek": "One line on where the numbers come from."}
```
Sections that follow a header belong to it (Ledger shows the header in a left rail; PowerPoint uses it as the slide title).

### chart / chart-insight
```json
{"type": "chart", "chart": {...}, "chart_title": "Daily leads by *platform*", "caption": "..."}
{"type": "chart-insight", "chart": {...}, "caption": "...",
 "insight_kicker": "The mix", "insight_title": "Paid search starts *41%* of journeys.",
 "insight_body": ["Sentence.", "Sentence."]}
```

Chart objects:

| type | fields |
|---|---|
| `doughnut` | `labels`, `values`, `unit` ("%" or null). Max 6 slices; extra fold into Other. |
| `bar-horizontal` | `labels`, `values`, `unit`, `x_title`, `highlight` (index or label), `notes` (per-row sublabel), `show_share` |
| `bar-vertical` | `labels`, `values`, `unit`, `highlight`, `show_values` |
| `bar-stacked` | `labels`, `stacks: [{label, values}]` |
| `bar-grouped` | `labels`, `groups: [{label, values}]` |
| `line` / `area` | `labels`, `values`, `unit` (peak + last value are labeled automatically) |
| `line-multi` | `labels`, `series: [{label, values, style?: "dashed"}]`, `band: {upper, lower}`, `forecast_start` (index), `forecast_label` |
| `waterfall` | `steps: [{label, value, kind: "start"\|"delta"\|"total"}]`, `unit` |
| `bar-diverging` | `labels`, `values` (+/-), `unit`, `good` ("up"\|"down") |

`unit`: `"%"`, `"$"`, `"x"`, or omitted for counts.

### ranked-list (tables)
```json
{"type": "ranked-list", "title": "Spend and leads by *platform*",
 "columns": [
   {"key": "rank", "label": "#", "type": "rank"},
   {"key": "name", "label": "Campaign", "type": "name"},
   {"key": "source", "label": "Source", "type": "source"},          // mono: utm values, URLs
   {"key": "leads", "label": "Leads", "type": "bar"},               // value + in-cell bar
   {"key": "spend", "label": "Spend", "type": "money", "align": "right"},
   {"key": "cpl", "label": "CPL", "type": "number", "align": "right"},
   {"key": "change", "label": "vs August", "type": "delta", "align": "right", "good": "up"},
   {"key": "status", "label": "Status", "type": "badge"},
   {"key": "trend", "label": "Trend", "type": "trend"},
   {"key": "platform", "label": "Platform", "type": "platform"},
   {"key": "daily", "label": "Last 30 days", "type": "spark"},
   {"key": "why", "label": "Why", "type": "text"}],
 "rows": [{"rank": "1", "name": "Brand search", "leads": {"value": 412, "label": "412"},
           "change": {"label": "+18%", "direction": "up"}, "status": {"label": "Scale", "tone": "good"},
           "trend": {"state": "rising", "label": "Rising"}, "daily": [3, 4, 2, 5], "_highlight": true}],
 "totals": {"name": "Total", "leads": "1,186", "spend": "$27,600"},
 "caption": "..."}
```
Badge tones: `good`, `warn`, `bad`, `neutral`, `brand`. Trend states: `rising`, `steady`, `cooling`, `cold`. Keep tables to 12 rows or fewer (PowerPoint splits longer tables across slides).

### recommendations (2 to 6 items, in priority order)
```json
{"type": "recommendations", "items": [
  {"label": "This week", "title": "Move $2,000 to *emergency* search terms",
   "body": "Why, with the number that justifies it.", "impact": "High", "effort": "Low",
   "metric": "About 18 extra patients"}]}
```

### insight-card
```json
{"type": "insight-card", "kicker": "The headline", "title": "*Google search* brought 41% of new patients.",
 "body": ["Sentence.", "Sentence."], "tone": "neutral"}      // tone: neutral | good | warn | bad
```

### closing (always last)
```json
{"type": "closing", "kicker": "The month in one line",
 "title": "Next: move $2,000 into *emergency search*. It books patients at $156 each.",
 "summary_stats": [{"value": "1,186", "label": "Leads"}],   // up to 4
 "bullets": ["Recap line.", "Recap line."],                  // up to 3
 "body": "Optional sentence."}
```

### funnel (new)
```json
{"type": "funnel", "title": "optional",
 "stages": [{"label": "Website sessions", "value": 48210, "source": "Google Analytics 4"},
            {"label": "Form leads", "value": 1186, "source": "UTM Grabber", "conv_label": "of sessions became leads"},
            {"label": "New patients", "value": 214, "source": "HubSpot", "conv_label": "of leads became patients"}],
 "insight_kicker": "Where it leaks", "insight_title": "Only *43%* of leads book.", "insight_body": ["..."],
 "caption": "..."}
```
Stage values are numbers; `display` overrides the shown value. A top stage more than 6x the next is drawn with a scale break.

### flow (new: two-column Sankey)
```json
{"type": "flow", "chart_title": "From discovery to *decision*", "left_title": "First touch",
 "right_title": "Last touch", "links": [{"from": "Paid social", "to": "Paid search", "value": 21}],
 "left_order": ["Paid search", "Paid social"], "caption": "..."}
```
Keep to 6 nodes per side or fewer.

### heatmap (new)
```json
{"type": "heatmap", "chart_title": "When *leads* arrive", "rows": ["Mon", ...], "cols": ["7a", ...],
 "values": [[2, 5, 9], ...], "low_label": "Fewer", "high_label": "More", "caption": "..."}
```

### matrix (new: quadrant scatter)
```json
{"type": "matrix", "chart_title": "Campaigns: cost per lead vs *volume*",
 "points": [{"label": "Brand search", "x": 188, "y": 8.2, "size": 188, "group": "Google Ads"}],
 "x_label": "Leads", "y_label": "Cost per lead", "y_unit": "$", "x_ref": 140, "y_ref": 28,
 "quadrants": {"tl": "Fix or cut", "tr": "Scale with care", "bl": "Hidden gems", "br": "Scale now"},
 "insight_kicker": "...", "insight_title": "...", "insight_body": ["..."]}
```
At most 3 groups (colors stay distinguishable for every reader). Use `x_ref`/`y_ref` = medians or targets.

### comparison (new: A vs B)
```json
{"type": "comparison", "a": {"label": "Google Ads", "sub": "$18,420 spend"}, "b": {"label": "Meta Ads"},
 "rows": [{"label": "Cost per lead", "a": 28.69, "b": 23.07, "a_display": "$28.69", "b_display": "$23.07", "better": "b"}],
 "caption": "..."}
```

### callouts (new: 2 to 4 short facts)
```json
{"type": "callouts", "items": [{"kicker": "Platform said", "value": "1,412", "title": "conversions reported", "tone": "neutral", "body": "optional"}]}
```

### scorecard (new: checks with status)
```json
{"type": "scorecard", "title": "Tracking *health*", "items": [
  {"label": "Google click ID captured", "value": "88%", "status": "warn", "detail": "Why and what to fix."}]}
```
Status: `pass` | `warn` | `fail` | `info` (always shown with an icon and a word, never color alone).

### timeline (new)
```json
{"type": "timeline", "title": "One patient's *journey*", "events": [
  {"date": "Sep 3, 12:06pm", "title": "Searched \"emergency dentist\"", "detail": "Google Ads, exact match",
   "tags": ["gclid", "utm_term=emergency dentist"], "kind": "touch"}]}     // kind: touch | conversion | purchase
```

### notes (new: methodology, small print)
```json
{"type": "notes", "title": "How we built this report", "items": ["Spend from Google Ads for Sep 1 to Sep 30.", "..."]}
```
Every cross-platform report ends its content with `notes` saying where each number came from and how rows were matched.

---

## Themes

`studio` (default), `boardroom`, `ledger`, `classic`. Any theme renders any report. See `references/themes.md`.
