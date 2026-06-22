# Rendering Pipeline

**Read `references/voice-discipline.md` first. The "how" here is about speed. The "what to say" is about voice.**

## The non-negotiable speed target

Every report should finish in **≤4 tool-use rounds**, not counting `present_files`. That means:

1. ONE logical MCP pull (page 1, then any remaining pages issued in a single parallel batch — see below)
2. ONE bash/python execution that does EVERYTHING (load + normalize + transform + inject + save)
3. `present_files` to surface the output
4. Optionally ONE extra call if the customer explicitly asked for PDF/PPTX

No multi-script orchestration. No compute-then-inject separation. One script at the end.

## The default MCP strategy: page 1, then parallel rest

`get_entries` is paginated (max `per_page: 100`). You don't know how many pages a window has until page 1 returns, so:

1. **Round 1:** call page 1 with `per_page: 100`. For a delta report (monthly/weekly/forecast), call page 1 of BOTH the current and prior windows together in the same parallel batch.
2. Read `total_pages` from the pagination line (`Page 1 of 8 (100 per page, 730 total …)`).
3. **Round 2 (only if `total_pages > 1`):** issue pages `2 … total_pages` in a **single parallel tool-use batch** — for both windows at once if it's a delta report. Save each page to its own file.
4. Feed all page files to `helpers.load_entries([...])`, which concatenates + normalizes in one call.

A ~500-lead month is ~5 pages → 2 rounds. A "last week" Q&A (~100 leads) is 1 page → 1 round. An 8k-entry year is ~80 pages — rare; narrow the window or single-form it before paging that far.

Never page **sequentially** (page 1, wait, page 2, wait…). After page 1 you know the count — fire the rest at once. See `references/mcp-usage.md` for the full pagination + field-normalization contract.

## The single-script pattern

Write ONE Python script that does everything. Don't split compute and inject into two steps.

```python
# /home/claude/run-report.py
import json, re, sys
sys.path.insert(0, '/mnt/skills/user/utm-grabber-reports/scripts')
from helpers import *

# 1. Load raw entries from disk (saved after MCP pull)
current = load_entries_from_mcp_result('/home/claude/entries-current.json')
prior = load_entries_from_mcp_result('/home/claude/entries-prior.json')

# 2. Build the summary using pre-built helpers
summary = {
    "meta": { ... },
    "totals": { ... },
    "channel_mix": compute_channel_mix(current),
    "source_leaderboard": compute_source_leaderboard(current),
    # ... every section the report needs
}

# 3. Inject into template in the same script
with open('/mnt/skills/user/utm-grabber-reports/templates/report-shell.html') as f:
    template = f.read()

output = re.sub(
    r'(<script id="report-data" type="application/json">)[\s\S]*?(</script>)',
    lambda m: m.group(1) + '\n' + json.dumps(summary) + '\n' + m.group(2),
    template, count=1
)
# CRITICAL: the regex MUST include `type="application/json"`. Without that
# attribute, the pattern also matches mentions of <script id="report-data">
# inside HTML comments elsewhere in the template. When that happens, the
# non-greedy [\s\S]*? will scan forward to the next </script> tag and
# silently delete everything in between — including the brand-overrides
# <style> tag and the real data block. This is a real bug that broke v0.7.0
# and v0.7.1 and produced unrendered reports. Do not shorten the regex.

# 4. Save
path = '/mnt/user-data/outputs/monthly-review-2026-04-19.html'
with open(path, 'w') as f:
    f.write(output)

print(f"Done: {path}")
```

**One tool call.** Transforms AND renders in a single pass.

## Output formats (all three supported)

HTML is the default. PDF and PPTX are generated on explicit request via dedicated builders that take the same `summary` dict — same schema, same voice, same section layout.

- **HTML** → inject `summary` into `templates/report-shell.html`. Chart.js renders at view-time. Light theme only. Always offered.
- **PDF** → `scripts/build_pdf.py` prints the real `report-shell.html` via headless Chromium (Playwright). Same charts as the on-screen report; Chart.js + fonts are bundled and inlined so it works offline. Light theme only — gradient is PPTX-exclusive.
- **PPTX** → `scripts/build_pptx.py` via python-pptx. Charts pre-rendered to PNG (matplotlib). Supports both `light` and `gradient` themes.

After delivering HTML, offer the alternate formats as a one-line follow-up:

> Want this as a PDF, PowerPoint deck, or the leads as a CSV?

Only generate PDF / PPTX / CSV when the user explicitly asks for that format (either in the original request or in reply to the follow-up). Never generate all three preemptively — it wastes a tool call and the customer didn't ask.

## Page in parallel, never sequentially by date

Don't pull the window in sequential date chunks (week-by-week) — that adds round after round and the customer feels every one. Pull the whole date range at once and let pagination handle volume: page 1, then pages `2…total_pages` in a single parallel batch. Two rounds covers any normal-volume report.

If a page call fails, retry just that page once, then tell the user in plain language if it still fails. Never silent-loop.

## No repeated pulls within a session

After the first MCP pull, the data sits in `/home/claude/cache/`. For follow-up reports or questions in the same conversation, load from cache — don't re-fetch.

## Acknowledgment template

ONE short sentence before tools run. No step list. No "I'll" narration.

**NEVER promise a specific duration.** "About 15 seconds", "this will take a minute", etc. are forbidden. Real runtime varies with data volume, MCP latency, and tool overhead — any promise you make will often be wrong and erodes trust. Stay vague or silent about timing.

**Good acknowledgments:**
> Pulling your last 30 days now.

> Running the monthly review.

> On it — one sec.

**Bad acknowledgments:**
> Running your monthly review — about 15 seconds.   ← FORBIDDEN (specific time)
> This will take roughly a minute while I fetch...  ← FORBIDDEN (narrates process + time)
> Generating your report. First I'll pull MCP data... ← FORBIDDEN (process narration)

That's the whole pre-execution message: ≤8 words, no duration claim, no process description. Then tools run silently. Then deliver.

## Delivery template

After file is saved and presented, ONE short message:

```
Here's your {report name}. {One-sentence headline with specifics.}

Want to {one specific follow-up}?
```

Then call `ask_user_input_v0` with 2-3 buttons.

**Maximum: 3 sentences / 50 words before the buttons.**

## Error recovery without confession

| Internal reality | Customer hears |
|---|---|
| MCP 500 error | "Your site isn't responding. Try again in a minute." |
| Zero entries returned | "No submissions in the last 30 days. Check further back?" |
| Context overflow | Silently retry with chunking. No mention. |
| Tool-use limit hit | "One sec, finishing up." — deliver next turn, no explanation |
| Data issue | "Something looks off — let me try a narrower window." |
| Python/template error | Fix silently. Don't mention. |

**The customer never hears "script", "pipeline", "tool", "limit", or "Python".**

## What NOT to do

- **Don't** split transformation across multiple bash calls. One script.
- **Don't** pull in 5 chunks when 1 works.
- **Don't** generate PDF ever in this version (hard ban — see the disabled section above).
- **Don't** narrate the plan before executing.
- **Don't** summarize what you just did after delivering.
- **Don't** explain tool limits to the customer.
- **Don't** list 4 alternatives at the end of every message.
- **Don't** include filenames, function names, or code in chat output.

The report IS the deliverable. The chat is a greeter and doorman. Nothing more.


## Data-source memory: skip discovery after first run

Every time Claude runs a report, it's tempted to rediscover the customer's site from scratch:
`check_site_health` → `get_form_plugins` → `list_forms` → `get_entries`. That's 3-4 round-trips before any data lands.

**After the first successful MCP connection in a conversation**, Claude MUST save the data source to memory via `memory_user_edits`:

```
User's data source: customer_domain=<domain>, form_plugin=<plugin>, form_ids=[<ids>]
```

On subsequent reports (same conversation OR future conversations), Claude reads this from memory and skips discovery entirely — goes straight to `get_entries`. Saves 10-20 seconds per report.

If the memory has a data source but the customer's site has changed forms, `get_entries` will return an error or empty result. Handle that by re-running discovery once and updating memory.

## Cache check: always before MCP

Before any `get_entries` call, check the disk cache. Use **`load_cached_superset`** — it handles both exact-match hits AND the common Q&A case where the requested range is a subset of a previously cached pull (e.g. report pulled 30 days; user then asks about last week).

```python
from helpers import load_cached_superset, save_cached_entries
entries = load_cached_superset(customer_domain, form_ids, start_date, end_date)
if entries is None:
    # Cache miss — call MCP, then save the result
    ... call get_entries ...
    save_cached_entries(mcp_result_path, customer_domain, form_ids, start_date, end_date)
```

Cache TTL is 4 hours (`CACHE_TTL_SECONDS` in `helpers.py`). A follow-up question minutes — or hours — after a report should never trigger a re-pull. UTM data isn't live-critical, so a longer TTL is safe and meaningfully reduces MCP round-trips for Q&A-heavy conversations.

`load_cached_entries` (exact-match only) is still exposed for callers that need strict behavior, but `load_cached_superset` is the default for report and Q&A flows.

## Skip prior-period pull for reports that don't need deltas

Only these reports need a prior-period comparison (the "vs last period" deltas):
- Monthly performance review
- Weekly executive summary
- Predictive forecast (needs historical baseline)

All others — campaign leaderboard, UTM hygiene audit, lead profile, ad creative, keyword, landing page, form, source-to-CRM mapping, agency rollup, side-by-side, paid-vs-organic (single snapshot), anomaly detector — DO NOT need a prior-period pull. Skipping it saves a full MCP round-trip.

Only pull the prior period if the report spec explicitly calls for period-over-period deltas.

## The full optimized flow

For any report, the minimum tool-call sequence is:

1. **(conditional)** Check memory for data source. If missing, run discovery + save to memory.
2. **(conditional)** Check cache via `load_cached_superset` for the current-period range. If hit, skip the pull.
3. `get_entries(...)` page 1 with `per_page: 100` — for a delta report, page 1 of current + prior together in one parallel batch. Save each page to its own file.
4. **(only if `total_pages > 1`)** Issue pages `2…total_pages` (both windows) in a single parallel batch. Save each.
5. ONE bash script: `load_entries([page files])` (normalizes + concatenates) → compute sections → inject into template → save HTML. Save the concatenated result to cache.
6. `present_files`.

**Cached follow-up question: 2 rounds** (bash + present_files).
**Fresh small report (≤100 leads/window, 1 page): 3 rounds** (page-1 pull + bash + present).
**Fresh normal report (multi-page): 4 rounds** (page-1 batch + remaining-pages batch + bash + present).
**Worst case (cold site): ~5 rounds** (discovery folds into the first pulls).

If a report balloons past ~5 rounds for a normal-volume site, something's wrong — stop and check rather than stacking page calls.
