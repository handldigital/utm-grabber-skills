# Full-Funnel Performance

## Triggers

- `/full-funnel`
- `full funnel`
- `funnel report`
- `from ad spend to revenue`
- `cross-platform monthly`

## Purpose

The flagship cross-platform monthly. Ad spend, website sessions, form leads, deals, customers and revenue on one page, channel by channel, with ROAS and cost per customer. Answers "what did our marketing turn into this month, and where does the funnel leak?" Every source except UTM Grabber is optional: a missing source drops its stage and columns, and the notes say "Connect X to add Y".

## Build it

```python
from recipes_v2 import get_recipe
summary = get_recipe("full-funnel")(leads, prior, ad_rows=ads, ad_rows_prior=ads_prior,
                                    visit_rows=visits, visit_rows_prior=visits_prior,
                                    deal_rows=deals, deal_rows_prior=deals_prior, crm_name="HubSpot",
                                    brand_profile=brand, customer_domain="example.com")
```

Registry keys: `full-funnel`, `funnel`, `full-funnel-performance`.
Signature: `build_full_funnel(leads, prior=None, ad_rows=None, ad_rows_prior=None, visit_rows=None, visit_rows_prior=None, deal_rows=None, deal_rows_prior=None, orders=None, orders_prior=None, brand_profile=None, customer_name=None, customer_domain="", compare_label=None, form_label=None, prepared_by=None, prepared_for=None, **kwargs)`

| Source | Needed | What to request (same window, plus the prior window) |
|---|---|---|
| UTM Grabber | Required | Entries for the period (`leads`) and the period before (`prior`). |
| Google Ads, Meta Ads, Microsoft Ads | Optional | Campaign x day: spend, clicks, impressions. Adds spend, ROAS, cost per customer. |
| Google Analytics 4 | Optional | `sessionSource`, `sessionMedium`, `landingPagePlusQueryString`, `date`; `sessions`, `engagedSessions`. Adds the sessions stage and lead rates. |
| HubSpot, Salesforce, Pipedrive | Optional | Deals with contact email, stage, amount, create date, close date. Adds deals, customers, revenue. |
| WooCommerce | Optional | Orders (`orders=`), used for customers and revenue only when no deals are passed. |

Rows can be raw connector payloads or already normalized. Extra keywords: `crm_name` (default "HubSpot", used in copy and chips), `store_name` (default "WooCommerce"), `history` (older leads, so a deal can match an earlier form fill).

## How the numbers work

- A lead counts toward an ad platform when its utm_source and utm_medium or a click ID (gclid, fbclid, msclkid) show one; otherwise toward UTM Grabber's channel (Organic, Social, Referral, Direct). Sessions are grouped by the same rules from GA4 source and medium (AI assistants count as Organic, email as Referral).
- Deals match leads by lowercase email. Customers are won deals and revenue is their amount. Deals with no form lead get their own table row, so totals tie out to the CRM.
- Funnel deal stages count only deals matched to this period's leads; the caption says how many of all deals that is.
- ROAS = revenue from customers who came through an ad platform / that platform's spend. The table's Total line shows paid ROAS and says so.
- The leak is whichever is lower: lead-to-deal rate or close rate on decided deals (won / (won + lost)). Without a CRM, sessions-to-lead.
- Customer, revenue and ROAS changes are held back when this period's share of open deals is 10+ points above the prior period's: a young cohort, not a decline. The notes say why.
- If no lead carries an ad platform's tags, spend shows but ROAS does not, and tagging becomes the first recommendation.

## Section order

1. **title-block**: "September turned $27.9K of ads into *$165K* of revenue." (falls back to customers, leads or sessions when spend or revenue is missing). Subtitle ties ad revenue to total revenue and names the deal and close rates.
2. **stat-strip** (2 to 6): ad spend, sessions, leads (sparks, deltas), customers, revenue, ROAS, cost per customer. Sessions drop when all seven exist.
3. **insight-card** "The takeaway": the channel with the most revenue (or leads) and where the rest came from.
4. **section-header 01 The funnel** + **funnel**: sessions (GA4), leads (UTM Grabber), deals created and customers won (CRM), each labeled with its source, with the biggest-leak insight.
5. **section-header 02 Channels** + **ranked-list**: spend, sessions, leads bar, lead rate, customers, revenue, ROAS, cost per customer, Total line.
6. **section-header 03 Spend to revenue** + **chart-insight** (waterfall: ad spend, each platform's revenue less its spend, revenue from ads) + **comparison** of the two biggest platforms.
7. **section-header 04 Next steps** + **recommendations**: shift or test budget by ROAS, follow up leads with no deal, lift a leaking channel, capture the source of deals with no form lead, connect the missing source.
8. **notes**: every source with its window, the matching rules, match rates, what is not connected.
9. **closing**: the next step with the number behind it.

Fewer than 10 leads: a short version. No leads: the standard empty report.

## Voice guidance

Owner-level and plain. Lead with what the money turned into, then where it leaks. Name each platform as "your Google Ads", "your HubSpot". Never call a young deal cohort a decline; say how many deals are still open.
