# Lead Quality Scorer

## Triggers

- `/score-leads`
- `score leads`
- `lead quality`
- `best leads`
- `prioritize leads`

## Purpose

Scores every lead 0 to 100 with transparent, additive points from signals that exist in the entries, then hands sales a call list. Answers "which leads should we call first, and why?"

## Build it

```python
from recipes_v2 import get_recipe
summary = get_recipe("lead-scorer")(current, brand_profile=brand, customer_domain="example.com")
```

Registry keys: `lead-scorer`, `lead-quality`, `score-leads`, `lead-quality-scorer`.
Signature: `build_lead_scorer(current, prior=None, brand_profile=None, customer_name=None, customer_domain="", compare_label=None, prepared_by=None, prepared_for=None, brand_terms=None, **kwargs)`

- `current`: UTM Grabber entries for the period. One row per person (best-scoring submission).
- `prior` (optional): adds the change in hot leads.
- `brand_terms` (optional): extra brand words for the brand-search signal.

## Scoring rules (also printed in the report)

- Paid search click (Google or Microsoft Ads) +10. Searched your name +15. Urgent or price words in the term +15.
- Budget answer: +25 for $25,000 or more, +18 from $5,000, +10 from $1,000, +5 below that (lower end of a range).
- Timeframe: +20 now or this week, +14 this month, +8 this quarter, +2 any other answer. A preferred-time answer like "as soon as possible" +15.
- Named a service +10, or +15 when it is urgent (emergency, pain, broken). Phone number +5, company +5, two or more forms +15.
- Visited a pricing, contact, booking, demo or comparison page +10. First landed on a different page than the form +5.
- Capped at 100. Hot 50+, Warm 25 to 49, Cold under 25. Form fields are found by name (budget, spend, timeframe, service...). Signals missing from the data are listed in the notes. Device is never scored.

## Section order

1. **title-block**: how many leads scored Hot. Subtitle: tiers and average score.
2. **stat-strip**: leads scored (spark), hot, warm, average score.
3. **insight-card** "Who to call first": the top lead, their reasons, source and time, the next two names, and phone vs email advice when devices are known.
4. **section-header 01 Call list** + **ranked-list** (top 15): lead name, masked email (`j***@domain.com`), source (mono), score bar, Hot/Warm/Cold badge, top two reasons.
5. **section-header 02 Score spread** + **chart-insight** (bar-vertical of score bands): the signal that most sets hot leads apart (share among hot vs all leads), the best source, why cold leads score low (only for questions the forms really ask).
6. **section-header 03 Next steps** + **recommendations**: call the hot leads, nurture the warm tier, put more behind the best source, add a "how soon" question (budget only for B2B-style forms with a company field) or make a skipped one required.
7. **notes** "How the score works".
8. **closing**: who to call, with the score.

Fewer than 10 people: a short version (call list, rules, closing).

## Voice guidance

Sales ready, not analytical. Each lead is a person to contact today. Always mask emails, never print IPs. Reasons must be readable at a glance.
