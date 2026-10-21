# Daily Pulse

## Triggers

- `/pulse`
- `daily pulse`
- `yesterday's leads`
- `morning report`
- `how did we do yesterday`

## Purpose

A one-page morning brief for a single day: leads against the trailing 7-day average and the same weekday last week, the top source, ad spend, what moved, and any regular source that went quiet. Answers "did anything break or spike yesterday?"

## Build it

```python
from recipes_v2 import get_recipe
summary = get_recipe("daily-pulse")(last_30_days, as_of="2026-09-30", ad_rows=ad_rows,
                                    brand_profile=brand, customer_domain="example.com")
```

Registry keys: `daily-pulse`, `pulse`, `daily`, `morning-pulse`, `yesterday`.
Signature: `build_daily_pulse(history, as_of=None, ad_rows=None, brand_profile=None, customer_name=None, customer_domain="", compare_label=None, form_label=None, prepared_by=None, prepared_for=None, **kwargs)`

- `history`: the last 30 days of leads, including the day itself.
- `as_of` (optional): the day to report (date, datetime or "YYYY-MM-DD"). Default: the latest date in `history`.
- `ad_rows` (optional): AdRow list. Adds the day's spend, cost per paid lead and spend chips per platform.

## Data

Free-plugin entries are enough: Date Created plus the UTM and click-ID fields. UTM Grabber Premium adds AI assistants and search engines to the source names (organic source and referrer domain fields). Spend needs an ad connector.

## How the numbers work

- 7-day average: leads per day over the 7 days before the day, counting only days inside the pulled range. A day outside the range is unknown, not zero.
- A source moved when it is 2+ leads away from its own 7-day average and outside normal swing (more than 1.5 x the square root of that average).
- Went quiet: a source that averages 3+ leads a day and sent leads on 6 of the 7 days sent none. Red from 5 a day.
- Regulars: sources that sent leads on 5+ of the 7 days and average 1+ a day.
- Leads without a utm_source are grouped by channel ("Untagged paid search", "Direct visits").

## Section order (7 sections)

1. **title-block**: "N leads, X% above average." Subtitle: the top source and the biggest move, in one line. No meta line, to save space.
2. **stat-strip**: leads that day (14-day spark, delta vs the 7-day average), change vs the same weekday last week, top source, ad spend (paid leads without spend).
3. **section-header 01 What moved** + **callouts** (2 to 4): went quiet, up, down, regulars, untagged share.
4. **chart** (bar-horizontal): the top 4 sources that day, each with its usual daily rate.
5. **recommendations** (2 at most): check the quiet source, test the top form after a sharp drop, find what lifted a riser, tag untagged links, keep the top source running.
6. **closing**: the one thing to do today.

Short versions: `as_of` outside the pulled leads (pull through that day first); fewer than 3 days of history before the day.

On Letter paper the brief (headline, KPIs, what moved, sources) fills page 1 and the two actions and the closing sit on page 2.

## Voice guidance

Morning-coffee short. Name the source and the number in every line. A slow day is not a crisis: only call a source quiet when the zero is beyond normal swing, and say what to check.
