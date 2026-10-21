# Form Performance

## Triggers

- `/forms`
- `form performance`
- `which forms`
- `form submissions`

## Purpose

Ranks forms by submissions and checks each one's health: trend, UTM capture, spam-looking entries and dormant forms. Answers "which forms are worth keeping, fixing or retiring?"

## Build it

```python
from recipes_v2 import get_recipe
summary = get_recipe("form-performance")(current, prior, forms=[{"id": "3", "title": "Book a visit"}],
                                         brand_profile=brand, customer_domain="example.com")
```

Registry keys: `form-performance`, `forms`, `form`.
Signature: `build_form_performance(current, prior=None, forms=None, brand_profile=None, customer_name=None, customer_domain="", compare_label=None, prepared_by=None, prepared_for=None, **kwargs)`

- `current`: UTM Grabber entries for the period, grouped by Form ID.
- `prior` (optional): adds change columns and trend statuses.
- `forms` (optional): `[{"id", "title"}]` from `list_forms`. Names the forms and adds listed forms with no submissions as dormant rows.

## How the numbers work

- With UTMs: share of a form's submissions with at least one of utm_source, utm_medium or utm_campaign. A form far below the rest (under 10% while the site averages 30% or more) is flagged "No UTMs": its hidden UTM Grabber fields are probably missing.
- Spam-like, judged per form: a disposable or test email, a blank name on a form where most entries have one, or three or more entries in the same second (two when the time has seconds).
- Dormant: under one submission per two weeks.
- Lead quality per form uses the lead quality scorer rules; a form whose leads score 20% above average earns a "more visible spot" recommendation.

## Section order

1. **title-block**: the top form's share. Subtitle: active forms, dormant forms, spam share when it matters.
2. **stat-strip**: submissions (spark, delta), active forms, top form share, with UTMs, spam-like share; dormant forms when there are any or a form list was given.
3. **insight-card** "The takeaway": the biggest problem (no UTMs, spam, dormant), else the concentration.
4. **section-header 01 Leaderboard** + **ranked-list**: form, submissions bar, share, change vs prior, with UTMs, spam-like, status badge (Dormant, Spam risk, No UTMs, Rising, Cooling, Steady, Active).
5. **section-header 02 Rhythm** + **chart-insight** (line-multi of the top 3 forms, daily up to 45 days, weekly beyond): first half vs second half of the period per form.
6. **section-header 03 Next steps** + **recommendations**: add UTM fields, filter spam, check a falling form, fix or retire a dormant one, test the top form weekly, promote the form with the best leads.
7. **notes**: grouping, UTM and spam definitions.
8. **closing**: the first recommendation with its number.

One form only: a summary of that form (volume, daily chart, UTM and spam health). Fewer than 10 submissions: a short version listing the forms.

## Voice guidance

Operational. Forms earn their place or they don't. Recommendations talk about placement, hidden fields and spam protection, and always name the form.
