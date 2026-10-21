# Weekly Executive Summary

## Triggers

- `/weekly`
- "weekly summary", "this week", "last 7 days", "Monday update"

## Purpose

The Monday one-pager for leadership: what happened in the last 7 days, what changed against the 7 before, and the two or three things to do this week. Tighter than the monthly; it prints on two pages.

## Build it

```python
from recipes_v2 import get_recipe
summary = get_recipe("weekly")(current, prior, brand_profile=brand, customer_domain="acme.com",
                               form_label="Gravity Forms")
```

Registry keys: `weekly`, `weekly-summary`, `weekly-executive-summary`.
Signature: `build_weekly(current, prior=None, brand_profile=None, customer_name=None, customer_domain="", form_label=None, compare_label=None, prepared_by=None, prepared_for=None, **kwargs)`

- `current`: UTM Grabber entries for the last 7 days. A longer pull (for example 30 days) also works: the recipe keeps the last 7 days and uses the 7 before as last week.
- `prior`: the previous 7 days, pulled in the same parallel batch. A longer prior is cut to the 7 days before the week.
- `compare_label` (optional): defaults to "last week".

## Section order

1. **title-block**: outcome headline. A source is named only when it explains most of the move: "Leads rose 12% to 87 this week, led by *Google*." Otherwise "This week brought *87 leads*, 12% fewer than last week." Subtitle names the top source and the biggest move.
2. **stat-strip**: leads (14-day spark), paid leads (14-day spark), fully tagged (pts), leads from the top source.
3. **01 What changed** (callouts): biggest riser, biggest drop, a new or quiet source, untagged leads rising, busiest day. Moves under 3 leads are left out.
4. **02 Sources**: top 5 sources as a bar list, each with last week's count, plus an insight on concentration and untagged leads.
5. **03 This week**: 2 or 3 moves. A drop or rise needs 5+ leads and 10%+ to earn one: check a source that dropped, back a riser, tag the links behind a rise in untagged leads. A source that went quiet (3+ leads last week) or a new one (2+ leads) also earns a move. The advice fits the traffic: ads (paused ad, spent budget), AI assistants (does it still recommend you), referral and social.
6. **closing**: "Next: check *Facebook* this week. It fell from 23 leads to 13." plus the busiest day and the top campaign. No summary numbers, so the report stays on two printed pages.

Under 10 leads this week: a short honest version that lists the leads and says why it stops.

## Voice guidance

Monday-morning brisk. Lead with the biggest change, not a recap. Every move is doable this week and names the source and the numbers behind it. Say "flat" when nothing moved; never invent drama.
