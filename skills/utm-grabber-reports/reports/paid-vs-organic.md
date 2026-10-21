# Paid vs Organic

## Triggers

- `/paid-vs-organic`
- "paid vs organic", "paid or organic", "organic vs paid", "should we spend more on ads"

## Purpose

The fundamental split: how big each side is, which is growing, who feeds each side, how lead quality compares, and (with first-touch data) which side opens the journeys the other closes. Answers "where should the next dollar go?"

## Build it

```python
from recipes_v2 import get_recipe
summary = get_recipe("paid-vs-organic")(current, prior, brand_profile=brand, customer_domain="acme.com")
```

Registry keys: `paid-vs-organic`, `paid-organic`.
Signature: `build_paid_vs_organic(current, prior=None, brand_profile=None, customer_name=None, customer_domain="", form_label=None, compare_label=None, prepared_by=None, prepared_for=None, **kwargs)`

- `current`: UTM Grabber entries for the window (30 to 90 days).
- `prior` (recommended): the previous window of the same length (10+ leads to be used). It drives the trajectory headline.
- Paid means a paid last touch (cpc, ppc, paid social, or a Google or Microsoft click ID). Organic is every other lead: search, social, referral, email, direct.

## Section order

1. **title-block**: with a prior, the trajectory: "*Organic* grew 24% while paid fell 4%." (a 10+ point gap), else "Paid and organic moved together; paid holds at *63%* of leads." Subtitle: counts and the top source on each side.
2. **stat-strip**: paid leads and organic leads (daily sparks, change), paid share (pts), paid leads fully tagged (pts).
3. **01 The split**: comparison rows: leads, share, change vs prior, top source share, top landing page share, fully tagged, and budget and timeframe rows when the form asks them. Ticks need a 3+ point gap.
4. **02 Trajectory**: paid and organic per day (per week beyond 45 days) with an insight on change vs prior and first half vs second half (labeled when inside normal swing).
5. **03 Sources**: top five sources on each side; organic leads without a utm_source are grouped by channel.
6. **04 First touch** (only when first-touch fields exist, UTM Grabber Premium): first vs last touch per side and how many paid leads organic opened.
7. **Next steps**: back the side with momentum, tag paid ad URLs (under 90% tagged), test a second paid channel (one source 70%+ of paid), protect the top organic page (20%+), credit organic for opened journeys (25%+), weigh quality gaps of 10+ points.
8. **notes** and **closing**: the first recommendation with its number, for example "Next: protect your *home page*. It brings 36% of organic leads."

## Voice guidance

Portfolio manager, not referee: both sides matter. Frame moves as allocation (more here, protect that), never replacement. Every claim names the side, the source or page, and the number.
