# Side-by-Side Comparison

## Triggers

- `/compare`
- "compare", "X vs Y", "side by side", "which is better"

## Purpose

Any two segments on the same measures: two campaigns, two sources, two forms or two periods. Answers "which is working better, by how much, and on what?" with a verdict per measure.

## Build it

```python
from recipes_v2 import get_recipe
summary = get_recipe("side-by-side")(google_leads, "Google Ads", meta_leads, "Meta Ads",
                                     brand_profile=brand, customer_domain="acme.com")
```

Registry keys: `side-by-side`, `compare`, `comparison`.
Signature: `build_side_by_side(a_entries, a_label, b_entries, b_label, brand_profile=None, customer_name=None, customer_domain="", form_label=None, compare_label=None, prepared_by=None, prepared_for=None, **kwargs)`

- Filter each side before calling (for example by utm_source or utm_campaign). For two periods, pass each period's entries with labels such as "September" and "August".
- Sides in the same window share a calendar; different windows are lined up by day number.
- One side empty: a short report saying which filter to check.

## Section order

1. **title-block**: "*Google Ads* brought 79% more leads than Meta Ads." (or "3.3x the leads"). Subtitle: each side's leads and tagged share.
2. **stat-strip**: A leads and B leads (daily sparks), lead gap, tagging gap, both framed from the leading side.
3. **01 Head to head**: comparison rows: leads, leads per day (when windows differ), fully tagged, paid share, sources with leads, top source share, top campaign share, plus budget and timeframe rows when the form asks them. A tick needs a material gap: 3+ points on a rate, 3%+ on a count. Paid share and concentration are context, never wins.
4. **insight-card** "The verdict": "*Google Ads* wins 3 of 3 measures." or a split decision.
5. **02 Rhythm**: leads per day, both sides.
6. **03 Channel mix**: share of each side's leads by channel, with the biggest gap called out.
7. **04 Next steps**: lift the weaker side's tagging (10+ pts behind), study what the bigger side does differently (10%+ more leads), test the winner's top source on the other side, weigh lead quality when a quality row differs by 10+ pts, tag both sides when both are under 80%.
8. **closing**: the first recommendation as "Next: ..." with the number behind it.

## Voice guidance

Judicial. Name the winner on each measure; call a split decision a split. Keep the verdict to measures where a higher number is plainly better, and say so.
