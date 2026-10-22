# When Leads Arrive

## Triggers

- `/lead-timing`
- `when do leads come in`
- `best time`
- `dayparting`
- `ad scheduling`

## Purpose

Maps when leads arrive by day of week and hour, names the best and quietest windows, compares paid and organic timing, splits devices, and turns the pattern into ad schedules, phone cover and email send times. Answers "when should we run ads, answer the phones and send email?"

## Build it

```python
from recipes_v2 import get_recipe
summary = get_recipe("lead-timing")(leads, prior, brand_profile=brand, customer_domain="example.com")
```

Registry keys: `lead-timing`, `timing`, `when`, `dayparting`, `best-time`.
Signature: `build_lead_timing(leads, prior=None, brand_profile=None, customer_name=None, customer_domain="", compare_label=None, form_label=None, prepared_by=None, prepared_for=None, **kwargs)`

- `leads`: UTM Grabber entries with a full Date Created timestamp. 30 to 90 days gives a steadier map.
- `prior` (optional): adds deltas for leads, after-hours share and phone share.

## Data

| Field | Plan | Used for |
|---|---|---|
| `Date Created` with a time of day | Free | Heatmap, windows, dayparts |
| utm fields and click IDs | Free | Paid vs organic |
| `user_agent (HandL)` (or the form's User Agent field) | Premium | Phone, desktop and tablet split |

## How the numbers work

- Times are read as recorded in Date Created: the site's time zone, or UTC when values end in Z (the dek and notes say which).
- Windows are 3 consecutive hours on one day. Best: the most leads. Quietest daytime: the fewest among windows that start between 8am and 5pm.
- Office hours: Monday to Friday, 8am to 6pm. Dayparts: night (midnight to 6am), morning, afternoon, evening.
- Busiest day divides each weekday's leads by how many times that weekday falls in the period.
- Paid: the converting visit was an ad click. Organic: every other lead. Each side is shown as a share of its own leads.

## Section order

1. **title-block**: "{Day} {daypart}s bring the most leads: N between X and Y." Subtitle: after-hours share and phone share.
2. **stat-strip**: leads (daily spark), busiest day, peak hour, after hours (pts), on a phone (pts).
3. **insight-card** "The takeaway": the share of leads that arrive while the office is closed.
4. **section-header 01 The week** + **callouts** (best window, quietest daytime window, busiest day, after hours) + **heatmap** (7 days x 24 hours).
5. **section-header 02 Paid vs organic** + **chart-insight** (bar-grouped by daypart) with 10+ leads on each side.
6. **section-header 03 Devices** + **chart-insight** (doughnut) when most leads carry a user agent.
7. **section-header Next steps** + **recommendations**: raise bids in the paid peak and trim the quietest window, staff the phones for the best window, an instant reply after hours (20%+), an email send time, a phone check of the form (60%+ on phones).
8. **notes** and **closing** (the best window and its leads).

Short versions: fewer than 10 leads; dates without times.

## Voice guidance

Operational and concrete. Use days and clock times ("Wednesday 8am to 11am"), never hour numbers. Every recommendation names a window and the leads in it.
