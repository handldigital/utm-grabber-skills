# Rendering Pipeline

**Read `references/voice-discipline.md` first. The "how" here is about speed. The "what to say" is about voice.**

## The non-negotiable speed target

Every report must finish in **≤4 tool calls total**, not counting `present_files`. That means:

1. ONE MCP pull (not chunked unless forced)
2. ONE bash/python execution that does EVERYTHING (data transform + template injection + file save)
3. `present_files` to surface the output
4. Optionally ONE extra call if the customer explicitly asked for PDF/PPTX

No multi-script orchestration. No compute-then-inject separation. One script. One call.

## The default MCP strategy: single pull

For a monthly report against a normal-volume site (~500 leads/month), use:

```
get_entries(plugin, form_ids, start=-30d, end=today, limit=1500)
```

One call, done. Saves 4-5 tool rounds vs weekly chunking.

Only chunk if:
- The response returns exactly `limit` entries (suggesting truncation), OR
- The customer tells you their site is high-volume, OR
- You've already tried once and hit context overflow

For 90-day reports: `limit: 3000` in one call. For annual: chunk monthly (but annual is rare — don't optimize for it).

For comparison windows (period-over-period), issue BOTH `get_entries` calls **in parallel in a single tool-use response** — not sequentially. The MCP server handles them concurrently and you save a full round-trip (~1–3 seconds per delta report). Only after both return, run the single transform script.

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
- **PDF** → `scripts/build_pdf.py` via WeasyPrint. Charts pre-rendered to SVG (no JS required). Light theme only — gradient is PPTX-exclusive.
- **PPTX** → `scripts/build_pptx.py` via python-pptx. Charts pre-rendered to PNG. Supports both `light` and `gradient` themes.

After delivering HTML, offer the alternate formats as a one-line follow-up:

> Want this as a PDF, PowerPoint deck, or the leads as a CSV?

Only generate PDF / PPTX / CSV when the user explicitly asks for that format (either in the original request or in reply to the follow-up). Never generate all three preemptively — it wastes a tool call and the customer didn't ask.

## No chunked pulls by default

Chunked weekly pulls look safer but add 4 extra tool rounds. Customer feels the delay.

The `limit: 1500` single-pull handles 99% of sites. Risk of context overflow on one pull < certainty of user impatience on five pulls.

If a pull DOES fail or truncate, fall back to chunking silently. Never announce it.

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
2. **(conditional)** Check cache via `load_cached_superset` for the current-period range. If hit, skip step 3.
3. `get_entries(plugin, form_ids, start, end, limit=1500)` — save to cache after.
4. **(delta reports only)** If prior is also a cache miss, issue the prior-period `get_entries` **in the same tool-use response as the current-period pull** so they run in parallel.
5. ONE bash script: compute all sections + inject into template + save HTML to outputs.
6. `present_files`.

**Minimum tool calls for a cached follow-up question: 2** (bash script + present_files).
**Minimum for a fresh report with saved data source: 3** (parallel get_entries counts as one tool-use turn + bash + present_files).
**Worst case (cold, unknown site): 6** (discovery × 3 + parallel current+prior + bash + present).

If a report takes more than 6 tool calls, something's wrong. Stop and check — don't keep stacking calls.
