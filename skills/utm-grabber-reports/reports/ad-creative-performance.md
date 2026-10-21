# Ad Creative Performance

## Triggers

- `/ad-creative`
- `ad creative performance`
- `which ads`
- `utm_content performance`

## Purpose

Ranks ad creatives (utm_content values on paid leads), flags the ones wearing out week by week, and says which to scale, rotate or pause. With ad spend connected it adds cost per lead per creative and the ads that spent without a single lead. Answers "which ads are pulling their weight, and which are tiring?"

## Build it

```python
from recipes_v2 import get_recipe
summary = get_recipe("ad-creative")(current, prior, ad_rows=ad_rows,
                                    brand_profile=brand, customer_domain="example.com")
```

Registry keys: `ad-creative`, `ad-creative-performance`, `creative`, `utm-content`.
Signature: `build_ad_creative(current, prior=None, ad_rows=None, brand_profile=None, customer_name=None, customer_domain="", compare_label=None, prepared_by=None, prepared_for=None, **kwargs)`

- `current`: UTM Grabber entries for the period. 28 to 31 days gives four full weeks for the fatigue check.
- `prior` (optional): the previous period. Adds the change column, trend statuses and the growth axis of the matrix.
- `ad_rows` (optional): normalized AdRow list (`connectors.normalize_ad_rows`). Adds ad spend, cost per lead, a cost column, and "No leads" rows for ads that spent without converting.

## How the numbers work

- Creatives are utm_content values on paid leads (a paid medium or an ad click ID). If no paid lead carries utm_content, every tagged lead is used and the report says so.
- Values are grouped ignoring case and punctuation, so `Hero_CTA` and `hero-cta` count once.
- Weeks are full 7-day windows ending on the last day of data; leftover days are left out so a partial week never looks like a drop.
- Fatiguing: weekly leads fell three weeks in a row, or the latest week is more than 40% below the creative's own first week with leads (that week needs 4 or more leads). The report leads with the creative losing the most leads per week.
- Spend matches a creative when the ad name equals the utm_content value (`connectors.norm_key`). Summary cost per lead divides all ad spend by all paid leads.

## Section order

1. **title-block**: outcome headline naming the top creative, or the top creative wearing out. Subtitle counts creatives and names the first fatiguing one.
2. **stat-strip** (up to 5): creative leads (daily spark, delta), ad spend and cost per lead when connected (else creatives with leads), fatiguing count, share of paid leads carrying utm_content.
3. **insight-card** "The takeaway": the fatiguing top creative, or how concentrated volume is.
4. **section-header 01 Leaderboard** + **ranked-list** (12 rows): creative (ad name from the ad rows when they match), campaign (mono), leads bar, share or cost per lead, change vs prior, weekly spark, status badge (Fatiguing, Rising, Cooling, New, Steady, No leads). The steepest fatiguing creatives always appear, with their real rank.
5. **section-header 02 Fatigue watch** + **chart-insight** (bar-grouped by week: the top 3 creatives plus the steepest fatiguing one) + **matrix** (leads vs growth, grouped by ad platform, at most 3 groups; fatiguing creatives are never called scale candidates). Skipped when the period has fewer than two full weeks.
6. **section-header 03 Next steps** + **recommendations**: rotate the fatiguing creative, pause zero-lead spenders, scale the biggest growing creative (or brief new creative when none is growing), rework the slowest, tag missing utm_content.
7. **notes**: scope, week rules, fatigue rule, where spend came from or that it is not connected.
8. **closing**: next step with the number behind it.

Fewer than 10 creative leads: a short version listing the creatives seen, with a note on why it is short. No utm_content at all: a short version that explains how to tag ads.

## Voice guidance

Creative-team ready. Talk about hooks, offers and rotation, never about how an ad looks: we only see lead counts. Name the creative in every recommendation. A creative that grew vs last month but is fading inside this month is fatiguing; say both.
