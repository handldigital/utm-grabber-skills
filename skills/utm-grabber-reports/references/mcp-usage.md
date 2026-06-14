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
get_entries(plugin, [form_ids], start, end, limit)
```

Never skip a step. Each one validates the next. If `check_site_health` fails, stop immediately.

## Choosing the form

When the user doesn't specify a form:

1. If only one form exists, use it.
2. If multiple forms exist, prefer the one with the most entries (call `get_entries` once per form with `limit: 10` to count, then pick).
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

## Handling the limit parameter

`get_entries` defaults to 75. For anything larger than a weekly report on a low-volume site, this is not enough.

### Default strategy: chunked weekly pulls

The safest default for monthly+ reports is to pull in **7-day chunks** rather than one large pull. This works on any site size, never blows context, and lets you fail gracefully if one chunk errors.

Example: for a 30-day monthly report, make FIVE calls covering days 0-7, 7-14, 14-21, 21-28, 28-30. Each call uses `limit: 500` (enough for ~70 leads/day). Aggregate in Python.

```
For weekly_chunk in [(today-7, today), (today-14, today-7), ...]:
    get_entries(start=weekly_chunk.start, end=weekly_chunk.end, limit: 500)
```

For 90-day quarterly reports, use 2-week chunks (~6-7 chunks total). For 180+ days, use monthly chunks.

### Why not just use `limit: 0`?

Two problems:
1. **Context overflow.** A high-volume site can return 10,000+ entries, exceeding Claude's context window and causing data loss.
2. **Retry granularity.** If a huge pull fails partway, the whole operation fails. Chunked pulls can retry individual weeks without restarting.

`limit: 0` is only appropriate for:
- Weekly reports on any site size
- Monthly reports on sites you KNOW are low-volume (< ~300 leads/month)

### Conversation-scoped caching

Within a single Claude conversation, the same data pull shouldn't be made twice. Before calling `get_entries`, check if a cache file exists at `/home/claude/cache/entries-{plugin}-{form_id}-{start}-{end}.json`. If it does, load from disk instead of calling the MCP.

Create the cache directory once per session:

```bash
mkdir -p /home/claude/cache
```

After each `get_entries` call, save the result:

```python
with open(f'/home/claude/cache/entries-{plugin}-{form_id}-{start}-{end}.json', 'w') as f:
    json.dump(result, f)
```

Subsequent reports in the same conversation that need the same data load from disk — usually 30-50% speedup for multi-report sessions.

Cache is invalidated at the end of the conversation (files in `/home/claude/` don't persist across sessions), so no staleness risk.

### Rules of thumb

- **Weekly report, any site:** default `limit: 75` is fine for most, `limit: 500` for high-volume. Single call.
- **Monthly report:** chunked weekly (5 calls of `limit: 500`).
- **Quarterly report:** chunked 2-weekly (6-7 calls of `limit: 500`).
- **Annual report:** chunked monthly (12 calls of `limit: 1000`), with explicit progress updates to the user ("pulling month 6 of 12...").

### When in doubt

Start with `limit: 75` and inspect. If the response returns exactly 75 entries, widen. Tell the user what you did: "Pulled 500 entries covering the full 30 days in 5 weekly chunks" is transparent and builds trust.

## Dealing with large responses

A pull of 1000+ entries will be saved to a tool-results file rather than inlined. Read that file with `bash_tool` + Python for aggregation rather than trying to inline the raw JSON:

```python
import json
with open('/mnt/user-data/tool_results/<file>.json') as f:
    raw = json.load(f)
text = raw[0]['text']
# Find the start of the JSON array in the text
entries_json = text[text.index('[\n  {'):]
entries = json.loads(entries_json)
```

Then aggregate in Python. Do not paste thousands of entries back into the conversation.

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
