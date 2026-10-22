# Monthly Performance Review

## Triggers

- `/monthly`
- "monthly report", "performance review", "last 30 days", "the deck", "how did we do this month"
- The default report when a request is vague.

## Purpose

The flagship: the month's lead story in one read. Volume and its change, where leads came from (channel mix, sources, campaigns), who opens journeys vs who closes them, the daily rhythm, and what to do next. Built to forward to a boss or client as-is.

## Build it

```python
from recipes_v2 import get_recipe
summary = get_recipe("monthly")(current, prior, brand_profile=brand, customer_domain="acme.com",
                                form_label="Gravity Forms")
```

Registry keys: `monthly`, `monthly-review`, `monthly-performance-review`.
Signature: `build_monthly(current, prior=None, brand_profile=None, customer_name=None, customer_domain="", form_label=None, compare_label=None, prepared_by=None, prepared_for=None, **kwargs)`

- `current`: UTM Grabber entries for the window (a calendar month or the last 30 days).
- `prior` (strongly recommended): the previous window of the same length, pulled in the same parallel batch. Adds every delta, the prior-period line and the rising/falling campaign recommendations.
- `compare_label` (optional): defaults to the prior month's name for calendar months, else "the previous 30 days".

For spend, cost per lead and revenue in the same story, run `full-funnel` instead (needs ad, analytics or CRM connected).

## Section order

1. **title-block**: outcome headline ("September brought 1,186 *leads*, 14% more than August."), subtitle naming the top source and the tagged share.
2. **stat-strip**: leads (daily spark), leads per day, paid share (pts), fully tagged share (pts).
3. **insight-card** "The takeaway": the top channel's share and the tagging gap.
4. **01 Channel mix**: donut of last-touch channels with an insight; when first-touch fields exist (UTM Grabber Premium), a first vs last touch grouped bar naming the channel that opens more journeys than it gets credit for.
5. **02 Sources and campaigns**: top sources bar list; top campaigns table (leads bar, share, change, trend).
6. **03 Volume**: leads per day, this period vs the prior (dashed).
7. **04 Next steps**: 2 to 4 recommendations from thresholds (tagging under 85%, the growing campaign (up 15%+) with the most leads, a campaign that fell below 60% of its prior volume, keep feeding the top channel).
8. **closing**: "Next: feed *{top source}*. It sent {share} of your leads." with four summary numbers and three recap lines.

Empty window: short honest report. Under 10 leads: recipes still run; say the sample is small.

## Voice guidance

Executive, specific, calm. Lead with the change and the biggest source. Every recommendation names a campaign or channel and the number behind it. Never mention spend or cost unless an ad platform is connected (use `full-funnel` for that).
