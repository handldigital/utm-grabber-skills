# Campaign Deep Dive

## Triggers

- `/campaign-deep-dive`
- "deep dive on", "tell me about campaign", "analyze campaign", "how is {campaign} doing"

## Purpose

One campaign end to end: volume and rhythm, where its leads came from, which ads and pages did the work, and a verdict (scale, refresh, pause, hold or keep testing) with the rule behind it.

## Build it

```python
from recipes_v2 import get_recipe
summary = get_recipe("campaign-deep-dive")(current, "brand_search", prior=prior,
                                           brand_profile=brand, customer_domain="acme.com")
```

Registry keys: `campaign-deep-dive`, `campaign`, `deep-dive`.
Signature: `build_campaign_deep_dive(current, campaign_name, prior=None, brand_profile=None, customer_name=None, customer_domain="", form_label=None, compare_label=None, prepared_by=None, prepared_for=None, **kwargs)`

- `current`: all UTM Grabber entries for the window (not just the campaign's), so share and rank are real.
- `campaign_name`: matched to utm_campaign ignoring letter case, spaces and underscores ("Brand Search" finds `brand_search`). No match: a short report listing the campaigns that did bring leads and the closest tag.
- `prior` (recommended): all entries for the previous window of the same length (10+ leads to be used).

## Section order

1. **title-block**: "*Brand search* grew 11% to 30 leads." Subtitle: share of all leads, rank, top source / medium and landing page.
2. **stat-strip**: leads (daily spark, change), share of all leads (pts), active days, last 7 days vs its own weekly average.
3. **insight-card** "The verdict" (tone good, warn, bad or neutral) with the rule in plain words:
   - scale: leads up 15%+ on 10+ leads
   - refresh: down 15% to 50%, or the second half 15%+ below the first (beyond normal swing)
   - pause: down 50%+, or no lead in the last 7 days
   - hold: within 15% of the earlier period; keep testing: new this period
4. **01 Volume**: leads per day against all other leads, or against the average other campaign when the rest of the site is 4x+ bigger (so the campaign's line stays readable).
5. **02 Sources**: source / medium bar when the tag spans 2+ pairs; first-touch channel bar when first-touch fields exist (UTM Grabber Premium), naming the channel that warmed these leads up.
6. **03 Ads and pages**: utm_content table (share, change, momentum) and landing pages table. Pages show leads, not conversion rates.
7. **04 Next steps**: the verdict's action, shift spend to the best ad (2x the weakest, 5+ leads), check message match on a page with 40%+ of leads, tag ads when 30%+ lack utm_content.
8. **notes** and **closing**: "Next: scale *Brand search*. It grew 45% to 64 leads."

Under 10 campaign leads: short honest version.

## Voice guidance

Intimate and specific: the campaign has an arc. State the verdict first, then the evidence. Never call a change a trend when it sits inside normal swing; the rule is printed so the reader can check it.
