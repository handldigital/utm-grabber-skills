# Anomaly Detector

## Triggers

- `/anomaly`
- "anomalies", "what changed", "sudden drop", "spike", "is something broken"

## Purpose

What moved this week against its usual pace, across channels, sources and campaigns, and where to look first. Separates real changes from normal random swing, so nobody chases noise.

## Build it

```python
from recipes_v2 import get_recipe
summary = get_recipe("anomaly")(last_7_days, previous_30_days, brand_profile=brand, customer_domain="acme.com")
```

Registry keys: `anomaly`, `anomalies`, `what-changed`.
Signature: `build_anomaly(current, baseline, brand_profile=None, customer_name=None, customer_domain="", form_label=None, compare_label=None, prepared_by=None, prepared_for=None, **kwargs)`

- `current`: the window to check (usually the last 7 days). Empty: an honest empty report that says to test the forms.
- `baseline`: the period before it (30 days is typical). Any overlap with the window is dropped. No baseline: a short report asking for one.
- Expected = baseline leads scaled to the window's length. Fix: a drop of 50%+ beyond 2 standard deviations. Watch: a drop of 25%+ beyond 1.5. Spike: a rise of 50%+ beyond 2. Drops and spikes need 5+ leads involved. Went quiet: 3+ expected and none arrived (Fix at 4+). New: under 1 expected and 3+ arrived.

## Section order

1. **title-block**: the biggest drop first: "The *Lookalike* campaign ran 84% below its usual pace this week.", else the biggest spike, else "No *anomalies* this week."
2. **stat-strip**: leads vs expected (spark), flagged, largest drop, largest rise (each marked "within normal swing" when not flagged).
3. **01 The scorecard**: flagged items first (Fix, Watch, Spike, New), topped up with healthy channels for context.
4. **02 By source**: change vs the usual pace for the top 8 sources (diverging bars, rises capped at +200%), then callouts for a new source, a source that went quiet, the biggest drop and spike.
5. **03 Daily**: baseline days, this window and the baseline's daily average.
6. **04 What to check**: investigations matched to the traffic (paid: account, budget, rejected ads; organic: rankings and indexing; referral and email links; AI assistants; direct: test the forms), confirm a spike before moving budget, follow up a new source, run the check weekly.
7. **notes** and **closing**: "Next: check the *Lookalike* campaign today. It ran 84% below its usual pace."

## Voice guidance

Urgent but calm. "Investigate", not "broken": the report flags where to look, never blames a channel without proof. When nothing moved, say so plainly and stop.
