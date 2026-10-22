# Close Rate by First Touch (Pipeline by Source)

## Triggers

- `/pipeline`
- `close rate by source`
- `which channels close`
- `deals by first touch`
- `CRM pipeline by source`

## Purpose

Joins CRM deals to UTM Grabber leads by email and shows, for the channel of each person's first visit, how many deals they opened, how many closed, what they were worth and how long they took. Contrasts first-touch with last-touch revenue credit, so channels that start journeys get their due. Answers "which channels bring the leads that actually close?"

## Build it

```python
from recipes_v2 import get_recipe
summary = get_recipe("pipeline")(leads, deal_rows=deals, ad_rows=ads, prior=prior, deal_rows_prior=deals_prior,
                                 crm_name="HubSpot", brand_profile=brand, customer_domain="example.com")
```

Registry keys: `pipeline`, `close-rate`, `crm-pipeline`, `deals-by-source`, `pipeline-by-source`.
Signature: `build_pipeline(leads, deal_rows=None, ad_rows=None, prior=None, deal_rows_prior=None, brand_profile=None, customer_name=None, customer_domain="", compare_label=None, form_label=None, prepared_by=None, prepared_for=None, **kwargs)`

| Source | Needed | What to request |
|---|---|---|
| UTM Grabber | Required | Entries for the window and the prior window (deals often come from last month's leads); `history` for older leads. |
| HubSpot, Salesforce, Pipedrive | Required | Deals created in the window (plus deals closed in it): contact email, stage, amount, create date, close date. Pass `crm_name`. |
| Google Ads, Meta Ads | Optional | Spend for the window. Adds ad cost per customer for platform rows. |

Without deals: a short version with leads by first touch.

## How the numbers work

- Deals match leads by lowercase email: this period's leads first, then `prior`, then `history`. Deals with no form lead get their own grey line so totals tie out to the CRM.
- First touch is the channel of the person's first recorded visit (UTM Grabber's first-touch fields); an ad platform is split out when the first visit's UTMs or a click ID on its landing page show one. Leads with no first-touch data fall back to last touch, and the notes count them.
- Close rate = won / (won + lost); open deals are left out. Days to close = close date minus create date, median of won deals. Average deal = won revenue / won deals.
- Ad cost per customer = a platform's spend / the won deals whose first visit came from it.
- The headline names the best close rate among channels with enough decided deals (the larger of 10 or 5% of all decided deals), when it beats the average by 5+ points; otherwise the channel with the most won revenue.
- Won, revenue and days-to-close changes are held back when this period's open-deal share is 10+ points above the prior period's.

## Section order

1. **title-block**: "Leads whose first visit came from *Google Ads* close 64% of decided deals." Subtitle: deals, won, close rate, revenue, open deals.
2. **stat-strip** (up to 6): deals, won, close rate, won revenue, average deal, days to close.
3. **insight-card** "The takeaway": the channel that starts more won revenue than it gets credit for, and its opposite.
4. **section-header 01 First touch to outcome** + **flow** (first touch to Won, Open, Lost; 6 nodes max) + **ranked-list**: deals bar, won, close rate, won revenue, average deal, days to close, ad cost per customer, Total line.
5. **section-header 02 First vs last touch** + **comparison**: won revenue credited by first touch vs last touch for the top channels.
6. **section-header 03 Next steps** + **recommendations**: judge the opener on first touch, feed the best-closing channel, follow up open deals (with how many are 14+ days old), speed up the slowest channel, shift budget by ad cost per customer, capture the source of deals with no form lead.
7. **notes** and **closing** ("Next: judge *Organic* on first touch. It started 24% of won revenue.").

Fewer than 10 matched deals, or leads with no source at all: a short, honest version.

## Voice guidance

Sales-and-marketing ready. Speak in deals, close rates and days, and always say how many deals are still open. Never call a channel weak on last-touch numbers alone.
