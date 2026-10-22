# Budget Simulator

## Triggers

- `/budget-simulator`
- `budget simulator`
- `what if budget`
- `reallocate spend`

## Purpose

Models what happens to leads if you move part of the budget (or effort) from one channel or campaign to another, as an honest range. Answers "what if I moved 20% from Google to LinkedIn?"

## Build it

```python
from recipes_v2 import get_recipe
summary = get_recipe("budget-simulator")(current, {"shift_from": "google", "shift_to": "linkedin", "pct": 20},
                                         ad_rows=ad_rows, brand_profile=brand, customer_domain="example.com")
```

Registry keys: `budget-simulator`, `budget`, `what-if`, `simulator`.
Signature: `build_budget_simulator(current, scenario=None, ad_rows=None, brand_profile=None, customer_name=None, customer_domain="", compare_label=None, prepared_by=None, prepared_for=None, **kwargs)`

- `current`: the baseline period. 60 to 90 days gives steadier rates.
- `scenario`: `shift_from`, `shift_to` and `pct`. Each name is matched to a campaign first, then an ad platform (`google` means Google Ads paid leads), then a utm_source. Without a scenario the two biggest channels are modeled and the subtitle says so.
- `ad_rows` (optional): AdRow list. Used when it covers both sides of the shift.

## The model (stated in the report)

- **No spend**: leads are assumed proportional to effort, and effort buys the same leads in both channels. The donor loses `pct` of its leads. High end: the receiver wins them all back (so the best case is flat). Low end: the receiver saturates with a square-root response.
- **With spend**: the donor loses leads at its average cost per lead. High end: the receiver keeps today's cost per lead. Low end: square-root response, `leads x sqrt(1 + moved / current spend)`.
- Every projection is a low to high range; the waterfall shows the middle of it.

## Section order

1. **title-block**: verdict headline (could add, would cost, a coin flip, or at best flat), with the range. Subtitle gives both channels' leads and spend.
2. **stat-strip**: leads today (spark), projected low end and projected high end (each with its delta vs today and the change in leads in the note), cost per lead today and after the shift when spend is known. The range is split into two KPIs so values stay short on phones.
3. **insight-card** "The assumption": the model in plain words.
4. **section-header 01 The scenario** + **chart-insight** (waterfall for the two channels: today, less from the donor, added in the receiver, with the shift) + **comparison** (today vs with the shift, ranges in the displays).
5. **section-header 02 Next steps** + **recommendations**: the verdict (test, keep the budget, test a smaller shift, or connect spend first), the reverse shift when the same model says it would gain, the weekly number to track, connect spend, tag untagged leads.
6. **notes**: baseline, how each name was matched, formulas.
7. **closing**: next step with the break-even number.

Fewer than 10 leads, an unknown channel, a donor with no leads, or a bad pct: a short, honest version that says what to fix.

## Voice guidance

Cautious analyst. Every projection is a range and every assumption is named. Lead with break-even: how many leads the receiving channel must add to justify the move.
