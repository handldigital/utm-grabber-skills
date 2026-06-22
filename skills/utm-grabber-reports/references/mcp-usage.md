# MCP Usage Guide

How to use the UTM Grabber MCP server efficiently. Load this file if you hit an error, get an ambiguous result, or need to call the server in a non-obvious way.

## The four tools

The UTM Grabber MCP exposes exactly four tools:

1. `check_site_health` — confirms the site is live and the plugin is responding.
2. `get_form_plugins` — lists all supported form plugins and which are active.
3. `list_forms` — returns forms for one plugin, with their IDs.
4. `get_entries` — pulls form submissions with full UTM data.

There is no tool for aggregates, no tool for ad-spend data, no tool for creating/editing entries. All analytics happen client-side (in Claude) from the raw entry data.

## The call sequence — always in this order

```
check_site_health
    ↓
get_form_plugins            (pick one with isActive=true)
    ↓
list_forms(plugin)          (pick the form(s) the user asked about)
    ↓
get_entries(selected_form_plugin, selected_form_ids,
            selected_start_date, selected_end_date,
            page, per_page)   (paginated — see below)
```

Never skip a step. Each one validates the next. If `check_site_health` fails, stop immediately.

## Choosing the form

When the user doesn't specify a form:

1. If only one form exists, use it.
2. If multiple forms exist, prefer the one with the most entries (call `get_entries` once per form with `per_page: 1` and read the `total` from the pagination line — no need to pull every entry just to count).
3. If forms look equal in volume, ask the user: "You have three forms — Demo Request, Contact, and Newsletter Signup. Which one should I analyze?"

Do not silently pick the first form in the list. That produces wrong answers for sites with many forms.

## Choosing the date range

Map the user's phrasing to concrete dates using today as the anchor:

| User said | Start | End |
|---|---|---|
| "today" | today 00:00 | today |
| "yesterday" | yesterday 00:00 | yesterday 23:59 |
| "this week" | 7 days ago | today |
| "last week" | 14 days ago | 7 days ago |
| "this month" or "last 30 days" or "monthly" | 30 days ago | today |
| "last quarter" or "last 90 days" | 90 days ago | today |
| "year to date" | Jan 1 of current year | today |
| Explicit dates | as given | as given |
| Nothing specified | 30 days ago | today |

Dates are in `YYYY-MM-DD` format. The MCP interprets them in the site's timezone (set in WordPress admin) — not UTC, not Claude's timezone.

## Pagination (v3.1.20+)

`get_entries` is **paginated**. One call returns a single page — `per_page` entries (default 50, **max 100**) — plus a pagination line:

> `Page 1 of 8 (100 per page, 730 total matching entries).`

and, while more remain, `More entries available. Call again with page=2 to fetch the next page.`

### Pulling a full window

1. Call page 1 with `per_page: 100`.
2. Read `total_pages` from the pagination line.
3. Loop `page: 2 … total_pages`, saving each page's raw result to its own file (`entries-current-p1.json`, `-p2.json`, …).
4. Hand the list of page files to `helpers.load_entries([...])` — it concatenates AND normalizes (see below) in one call.

A ~500-lead month is ~5 pages; an 8k-entry year is ~80 pages. Only page as far as the window needs — narrow the date range or pick a single form before paging through thousands.

### Just need a count?

Call `per_page: 1` and read `total` from the pagination line. One call, no entry data pulled.

## Field normalization — REQUIRED before aggregating

The paginated MCP keys each entry by **numeric form-field id**, not by name:

```json
{ "3": "Google", "4": "cpc", "7": "SpringSale", "form_id": "1",
  "date_created": "2026-04-16 13:03:36", "source_url": "..." }
```

A separate `field_labels` block in the same response maps those ids to names (`field_labels["1"]["3"] == "utm_source (HandL)"`). The helpers expect **named** keys (`utm_source (HandL)`, `Date Created`, …) — so raw entries MUST be normalized first, or every UTM lookup returns empty.

Don't do this by hand. `helpers.load_entries()` reads the page file(s), pulls out `field_labels`, rewrites each entry's keys to the human label, and adds the canonical `Date Created` / `Form ID` / `Source URL` aliases:

```python
from helpers import load_entries
current = load_entries(['/home/claude/entries-current-p1.json',
                        '/home/claude/entries-current-p2.json'])   # normalized + concatenated
```

`load_entries` is a safe no-op on already-named data (demo data, pre-3.1.20 files), so always route MCP results through it. `load_entries_from_mcp_result(path)` still exists for single-file callers and delegates to the same logic.

### Conversation-scoped caching

Within one conversation, don't pull the same window twice. Before calling `get_entries`, check the disk cache with `load_cached_superset` (in `helpers.py`) — it returns cached entries when the requested range is a *subset* of something already pulled (e.g. a monthly report covers a later "last week" question). After a fresh pull, save it with `save_cached_entries(page_files, domain, form_ids, start, end)` — pass the **list of all page files** (not just page 1); it concatenates + normalizes them into one cache entry so a later hit returns the whole window. Cache TTL is 4 hours.

## Large responses

A single page of 100 entries can be large enough to land in a tool-results file rather than inline. That's fine — pass the file path(s) straight to `load_entries`, which reads from disk. Never paste thousands of raw entries back into the conversation; aggregate in Python and pass only the compact summary object to the renderer.

## Error patterns and recovery

### "Site unreachable" or `check_site_health` returns an error
- Tell the user their WordPress site isn't responding to the MCP.
- Common causes: plugin deactivated, access code rotated, site in maintenance mode, firewall blocking.
- Do NOT proceed with any cached or guessed data. Stop and say so.

### `get_form_plugins` shows all plugins as inactive
- No form plugin is active. Tell the user: "It looks like none of the supported form plugins are active on your site. Activate Gravity Forms, Fluent Forms, WPForms, etc. and I'll be able to pull your attribution data."

### `list_forms` returns an empty array
- The plugin is active but has no forms. Tell the user and stop.

### `get_entries` returns zero entries for the date range
- Honest answer: "I looked at the last 30 days and found zero submissions on the Attribution Demo Request form. Either the form isn't live, it's not being used, or the date range is wrong. Would you like to check a wider range?"

### Entries are missing UTM data entirely
- This is itself a finding. Produce the report anyway — the "UTM Hygiene" section becomes the main story: "You captured 200 leads this month, but 180 have no UTMs at all. Here's where to start fixing it…"

## Staying within context

If you're pulling a large number of entries, keep the aggregation script separate from the reporting logic:

1. Pull entries → save raw to disk.
2. Run Python aggregation → produce a compact summary object (not the raw entries).
3. Pass only the summary into the rendering step.

Never attempt to fill the HTML template by looping over 1000 raw entries in conversation. The summary object should be <1000 tokens even for a huge site.

## What the MCP does NOT return

These are the Phase 2 features — NOT available today:

- Ad spend (CPM, CPA, ROAS)
- Paid click cost
- Ad creative performance
- Cross-platform deduplicated reach
- CRM pipeline stage (we see the CRM name, not what happened to the lead inside that CRM)
- Multi-visit journey detail beyond first touch + last touch (we have 2 touches, not N)

When a user asks for any of these, respond with: "That needs the UTM Grabber Ad Platform connector, which is rolling out in the next release. For now, I can show you [alternative from current data]."
