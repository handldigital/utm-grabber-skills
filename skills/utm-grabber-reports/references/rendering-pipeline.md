# Rendering Pipeline

**Read `references/voice-discipline.md` first. The "how" here is about speed. The "what to say" is about voice.**

## The non-negotiable speed target

Every report should finish in **≤4 tool-use rounds**, not counting `present_files`. That means:

1. ONE logical MCP pull (page 1, then any remaining pages issued in a single parallel batch : see below)
2. ONE bash/python execution that does EVERYTHING (load + normalize + transform + inject + save)
3. `present_files` to surface the output
4. Optionally ONE extra call if the customer explicitly asked for PDF/PPTX

No multi-script orchestration. No compute-then-inject separation. One script at the end.

## The default MCP strategy: page 1, then parallel rest

`get_entries` is paginated (max `per_page: 100`). You don't know how many pages a window has until page 1 returns, so:

1. **Round 1:** call page 1 with `per_page: 100`. For a delta report (monthly/weekly/forecast), call page 1 of BOTH the current and prior windows together in the same parallel batch.
2. Read `total_pages` from the pagination line (`Page 1 of 8 (100 per page, 730 total …)`).
3. **Round 2 (only if `total_pages > 1`):** issue pages `2 … total_pages` in a **single parallel tool-use batch** : for both windows at once if it's a delta report. Save each page to its own file.
4. Feed all page files to `helpers.load_entries([...])`, which concatenates + normalizes in one call.

A ~500-lead month is ~5 pages → 2 rounds. A "last week" Q&A (~100 leads) is 1 page → 1 round. An 8k-entry year is ~80 pages : rare; narrow the window or single-form it before paging that far.

Never page **sequentially** (page 1, wait, page 2, wait…). After page 1 you know the count : fire the rest at once. See `references/mcp-usage.md` for the full pagination + field-normalization contract.

## The single-script pattern (v2)

Write ONE Python script that loads, builds the summary with a recipe, and writes every requested format.

```python
# /home/claude/run-report.py
import sys
sys.path.insert(0, "/mnt/skills/user/utm-grabber-reports/scripts")
from helpers import load_entries, save_cached_entries
from recipes_v2 import get_recipe
from build_report import build_report

current = load_entries(["/home/claude/cur-p1.json", "/home/claude/cur-p2.json"])
prior = load_entries(["/home/claude/pri-p1.json"])

summary = get_recipe("monthly")(current, prior, brand_profile=BRAND, customer_domain="acme.com",
                                form_label="Gravity Forms")
paths = build_report(summary, ["/mnt/user-data/outputs/monthly-2026-10-05.html"], theme=THEME)
print(paths)
```

Cross-platform reports add the connector rows in the same script:

```python
from connectors import normalize_ad_rows, normalize_deal_rows
ads = normalize_ad_rows(google_rows, platform="Google Ads") + normalize_ad_rows(meta_rows, platform="Meta Ads")
deals = normalize_deal_rows(hubspot_rows)
summary = get_recipe("true-roas")(current, ad_rows=ads, deal_rows=deals, brand_profile=BRAND,
                                  customer_domain="acme.com")
```

Never write report HTML by hand and never edit the legacy template; the recipe + `build_report` path is the whole job.

## Output formats

The same `summary` dict builds every format; asking for another format later costs one short run, no data pulls.

- **HTML** `build_report(summary, "x.html", theme)`: self-contained, fonts embedded, responsive, hover details, data tables.
- **PDF** `build_report(summary, "x.pdf", theme, paper="letter"|"a4")`: headless Chromium prints the print layout (paginated, running footer, full-bleed dark pages for Boardroom).
- **PPTX** `build_report(summary, "x.pptx", theme)`: native editable deck, native charts, embedded fonts.
- **CSV** `build_csv.export_entries_to_csv(entries, path)`.

After delivering HTML, offer the alternate formats in one line:

> Want this as a PDF or a PowerPoint deck?

Only generate PDF, PPTX or CSV when the user asks for that format (in the original request or in reply).

## Page in parallel, never sequentially by date

Don't pull the window in sequential date chunks (week-by-week) : that adds round after round and the customer feels every one. Pull the whole date range at once and let pagination handle volume: page 1, then pages `2…total_pages` in a single parallel batch. Two rounds covers any normal-volume report.

If a page call fails, retry just that page once, then tell the user in plain language if it still fails. Never silent-loop.

## No repeated pulls within a session

After the first MCP pull, the data sits in `/home/claude/cache/`. For follow-up reports or questions in the same conversation, load from cache : don't re-fetch.

## Acknowledgment template

ONE short sentence before tools run. No step list. No "I'll" narration.

**NEVER promise a specific duration.** "About 15 seconds", "this will take a minute", etc. are forbidden. Real runtime varies with data volume, MCP latency, and tool overhead : any promise you make will often be wrong and erodes trust. Stay vague or silent about timing.

**Good acknowledgments:**
> Pulling your last 30 days now.

> Running the monthly review.

> On it : one sec.

**Bad acknowledgments:**
> Running your monthly review : about 15 seconds.   ← FORBIDDEN (specific time)
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
| Tool-use limit hit | "One sec, finishing up." : deliver next turn, no explanation |
| Data issue | "Something looks off : let me try a narrower window." |
| Python/template error | Fix silently. Don't mention. |

**The customer never hears "script", "pipeline", "tool", "limit", or "Python".**

## What NOT to do

- **Don't** split transformation across multiple bash calls. One script.
- **Don't** pull in 5 chunks when 1 works.
- **Don't** generate PDF ever in this version (hard ban : see the disabled section above).
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

On subsequent reports (same conversation OR future conversations), Claude reads this from memory and skips discovery entirely : goes straight to `get_entries`. Saves 10-20 seconds per report.

If the memory has a data source but the customer's site has changed forms, `get_entries` will return an error or empty result. Handle that by re-running discovery once and updating memory.

## Cache check: always before MCP

Before any `get_entries` call, check the disk cache. Use **`load_cached_superset`** : it handles both exact-match hits AND the common Q&A case where the requested range is a subset of a previously cached pull (e.g. report pulled 30 days; user then asks about last week).

```python
from helpers import load_cached_superset, save_cached_entries
entries = load_cached_superset(customer_domain, form_ids, start_date, end_date)
if entries is None:
    # Cache miss : call MCP, then save the result
    ... call get_entries ...
    save_cached_entries(mcp_result_path, customer_domain, form_ids, start_date, end_date)
```

Cache TTL is 4 hours (`CACHE_TTL_SECONDS` in `helpers.py`). A follow-up question minutes : or hours : after a report should never trigger a re-pull. UTM data isn't live-critical, so a longer TTL is safe and meaningfully reduces MCP round-trips for Q&A-heavy conversations.

`load_cached_entries` (exact-match only) is still exposed for callers that need strict behavior, but `load_cached_superset` is the default for report and Q&A flows.

## When to pull the prior window

Pull the prior window in the SAME parallel batch as the current one for every report whose recipe takes `prior` (monthly, weekly, daily-pulse, qbr, leaderboard, paid-vs-organic, ad-creative, keyword, landing-page, form-performance, audit, anomaly as `baseline`). It adds "vs last period" deltas without adding a round. Forecast and qbr take a longer `history` instead.

Skip the prior pull for single-snapshot reports: lead-profile, side-by-side, budget-simulator, lead-scorer, source-to-crm, journey, lead-timing, ai-referrals (unless the user asks for a trend).

## The full optimized flow

For any report, the minimum tool-call sequence is:

1. **(conditional)** Check memory for data source. If missing, run discovery + save to memory.
2. **(conditional)** Check cache via `load_cached_superset` for the current-period range. If hit, skip the pull.
3. `get_entries(...)` page 1 with `per_page: 100` : for a delta report, page 1 of current + prior together in one parallel batch. Save each page to its own file.
4. **(only if `total_pages > 1`)** Issue pages `2…total_pages` (both windows) in a single parallel batch. Save each.
5. ONE bash script: `load_entries([page files])` (normalizes + concatenates) → `get_recipe(key)(...)` → `build_report(summary, path, theme)`. Save the concatenated entries to cache.
6. `present_files`.

**Cached follow-up question: 2 rounds** (bash + present_files).
**Fresh small report (≤100 leads/window, 1 page): 3 rounds** (page-1 pull + bash + present).
**Fresh normal report (multi-page): 4 rounds** (page-1 batch + remaining-pages batch + bash + present).
**Worst case (cold site): ~5 rounds** (discovery folds into the first pulls).

If a report balloons past ~5 rounds for a normal-volume site, something's wrong : stop and check rather than stacking page calls.
