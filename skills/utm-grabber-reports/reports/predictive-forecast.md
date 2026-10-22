# Predictive Forecast

## Triggers

- `/forecast`
- "forecast", "predict", "next month", "projected leads", "how many leads should we expect"

## Purpose

The next 7 and 30 days of leads with a likely range, the weekly rhythm to staff for, and which channels are trending. Built for planning; it never claims more precision than the history supports.

## Build it

```python
from recipes_v2 import get_recipe
summary = get_recipe("forecast")(history, brand_profile=brand, customer_domain="acme.com")
```

Registry keys: `forecast`, `predictive-forecast`, `predict`.
Signature: `build_forecast(history, brand_profile=None, customer_name=None, customer_domain="", form_label=None, compare_label=None, prepared_by=None, prepared_for=None, **kwargs)`

- `history`: UTM Grabber entries for 30 to 120 days (90 is best). Under 21 days: a short honest report with today's pace, labeled a guess.
- Method, in plain words: a weekday pattern (each weekday's average against the overall average) times a weekly level. The level follows a straight line through the weekly totals only when that trend is bigger than 2 standard errors; otherwise it holds the last 4 weeks' average.
- Range: about 4 in 5 outcomes (1.28 standard deviations of past weekly misses, scaled to the horizon) and never narrower than normal count noise. Numbers are rounded and always "about".

## Section order

1. **title-block**: "Expect about *470 leads* in the next 30 days." Subtitle: the range, the weeks of history and the change against the last 30 days.
2. **stat-strip**: next 7 days (weekly spark, range), next 30 days (vs the last 30), likely range (plus or minus), trend in leads a week.
3. **01 The forecast**: actual leads for up to the last 12 weeks, then 30 forecast days (dashed) with a shaded daily band; then the weekday rhythm (busiest day only when it leads by 10%+, else weekdays vs weekends).
4. **02 By channel**: each channel's own weekly trend, scaled so channels add up to the total: last 30 days, next 30 days, change, trend pill (Rising or Cooling only beyond noise).
5. **03 Method**: plain-words notes on the pattern, the trend, the range and the assumptions.
6. **04 Next steps**: plan follow-up capacity for the range, budget for a rising channel, find what is slowing a cooling one, re-run after a launch or pause.
7. **closing**: "Next: plan for about *470 leads*. Expect 440 to 500 in the next 30 days."

## Voice guidance

Humble about prediction. Use "about", "likely" and "expect", never "will". Always give the range with the number, and say what would break the forecast.
