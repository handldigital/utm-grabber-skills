# Top Campaign Leaderboard

## Triggers

- `/campaigns`
- "top campaigns", "campaign leaderboard", "best campaigns", "which campaigns worked"

## Purpose

Every campaign ranked by leads, with growth against the previous period, momentum inside the period and a map of where to scale and what to fix. Answers "which campaigns worked, and which are slipping?"

## Build it

```python
from recipes_v2 import get_recipe
summary = get_recipe("leaderboard")(current, prior, brand_profile=brand, customer_domain="acme.com")
```

Registry keys: `leaderboard`, `campaigns`, `campaign-leaderboard`, `top-campaign-leaderboard`.
Signature: `build_leaderboard(current, prior=None, brand_profile=None, customer_name=None, customer_domain="", form_label=None, compare_label=None, prepared_by=None, prepared_for=None, **kwargs)`

- `current`: UTM Grabber entries for the window (30 days or a calendar month is typical).
- `prior` (recommended): the previous window of the same length. It needs 10+ leads to be used; it adds the change column, the growth map and the scale/fix recommendations.

## Section order

1. **title-block**: "*Brand search* led 13 campaigns with 30 leads." (or a tie). Subtitle: top-three share and how many campaigns grew or fell 15%+.
2. **stat-strip**: campaign-tagged leads (daily spark), campaigns with leads (new this period), top 3 share (pts), the top campaign's leads.
3. **01 The standings**: table of up to 12 campaigns: source / medium (mono), leads bar, share of all leads, change vs prior, momentum pill, daily spark. Momentum compares the second half of the period with the first and stays "Steady" inside normal random swing. The campaign to scale is highlighted.
4. **02 Growth map** (with a prior): matrix of leads (across) vs change (up), median line, quadrants Scale, Fix, New bets, Watch. New campaigns sit at +200% in their own color.
5. **03 Next steps**: scale the biggest grower (15%+ on 5+ leads); fix a big campaign that fell 15%+, or find out why a smaller one slowed; give a new campaign a fair test; refresh a big campaign cooling inside the period; tag links when 25%+ of leads lack utm_campaign. Advice fits the channel (ads, email, social).
6. **closing**: "Next: scale *Emergency dentist*. It grew 45% to 64 leads." with four summary numbers and three recap lines.

No campaign tags at all: a short honest report on adding utm_campaign. Under 10 leads: short version.

## Voice guidance

Competitive and specific. Name the winner, the faller and the new bet with their numbers. Trend pills carry the tone; the copy stays calm and never calls noise a trend.
