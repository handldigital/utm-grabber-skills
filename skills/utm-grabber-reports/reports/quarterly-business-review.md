# Quarterly Business Review

## Triggers

- `/qbr`
- `quarterly review`
- `board report`
- `quarter in review`
- `how did the quarter go`

## Purpose

A board-ready review of the quarter against the previous one: leads, cost, customers and revenue; month by month by channel; the shift in channel mix; the top campaigns; wins and risks; and the plan for next quarter. Answers "how did the quarter go, and what do we do next?"

## Build it

```python
from recipes_v2 import get_recipe
summary = get_recipe("qbr")(q3_leads, q2_leads, ad_rows=q3_ads, ad_rows_prior=q2_ads,
                            deal_rows=q3_deals, deal_rows_prior=q2_deals, brand_profile=brand)
```

Registry keys: `qbr`, `quarterly`, `quarterly-business-review`, `board`, `quarter`.
Signature: `build_qbr(current, prior=None, ad_rows=None, ad_rows_prior=None, deal_rows=None, deal_rows_prior=None, orders=None, brand_profile=None, customer_name=None, customer_domain="", compare_label=None, form_label=None, prepared_by=None, prepared_for=None, orders_prior=None, **kwargs)`

- `current`: the quarter's leads. `prior` (optional): the previous quarter's leads.
- `ad_rows`, `ad_rows_prior` (optional): spend and cost per paid lead.
- `deal_rows`, `deal_rows_prior` (optional): won deals as new customers and revenue.
- `orders`, `orders_prior` (optional): WooCommerce orders. They replace deals for orders and revenue.

## Data

Free-plugin leads cover leads, channels and campaigns. UTM Grabber Premium adds AI assistants as a channel (organic source and referrer domain fields) and WooCommerce orders. Spend needs an ad connector; customers need a CRM or a store.

## How the numbers work

- The quarter label ("Q3") needs data that starts within 3 days of a calendar quarter's first day. If it also ends within 3 days of the quarter's last day it counts as the full quarter, else "Q3 to date". Any other window (one month, the last 30 days, two quarters) is named by its dates: "September", "the last 90 days".
- When the two periods differ in length, changes compare per-day rates ("186 leads against 140 at Q2's daily pace") and the subtitle says so.
- Cost per paid lead: spend divided by paid leads over the dates the ad rows cover. Spend, deals or orders that cover only part of the quarter are flagged on their tile and in the notes; partial spend also gets a scorecard line, and no delta is drawn from partial deals.
- Sparks are weekly across the quarter. Share shift: each channel's share of leads this quarter minus last quarter, in points.
- Wins and risks: lead flow up or down 5%+; cost per paid lead down 5%+ or up 10%+; the fastest-growing channel and campaign; a campaign down 40%+; a channel down 20%+ a day; a campaign that faded 40%+ from the quarter's first month to its last; one channel with half of all leads; 15%+ of leads untagged.

## Section order

1. **title-block**: leads and the change vs the prior quarter (per day when lengths differ). Subtitle: top channel, spend and cost, customers and revenue.
2. **stat-strip** (up to 6): leads, leads per day, ad spend, cost per paid lead, customers or orders, revenue.
3. **insight-card** "The quarter in one line": the channel that grew most.
4. **section-header 01 Month by month** + **chart** (bar-grouped, full width, one bar per month for each channel) + **insight-card** "The movers".
5. **section-header 02 Channel mix** + **chart** (bar-diverging, points) when a prior quarter exists.
6. **section-header 03 Campaigns** + **ranked-list** (top 10 with change and a status badge).
7. **section-header 04 Wins and risks** + **scorecard** (up to 3 wins, then up to 3 risks).
8. **section-header 05 Next quarter** + **recommendations**: scale the riser, fix or refresh the faller, build a second channel, keep pages easy for AI assistants to cite, tag every link, connect a full quarter of spend and sales.
9. **notes** and **closing** ("Next quarter: ...").

Short version: fewer than 10 leads.

## Voice guidance

Board-ready: few words, big numbers, every claim beside its comparison. Wins first, risks second, never alarmist. The plan names channels and campaigns, not bid settings.
