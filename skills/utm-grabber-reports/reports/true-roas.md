# Which Ads Brought Customers (True ROAS)

## Triggers

- `/true-roas`
- `true ROAS`
- `which ads actually brought customers`
- `ad ROI`
- `spend to revenue by ad`

## Purpose

Joins every ad's spend to the leads it brought and the customers those leads became. Ranks ads by real revenue, maps them by leads and cost per lead, lists the spend that didn't pay back, and compares ROAS by platform. Answers "which ads actually brought customers, and where should the budget go?" Without deals or orders it stops at cost per lead and says revenue is not connected.

## Build it

```python
from recipes_v2 import get_recipe
summary = get_recipe("true-roas")(leads, ad_rows=ads, deal_rows=deals, prior=prior, ad_rows_prior=ads_prior,
                                  crm_name="HubSpot", brand_profile=brand, customer_domain="example.com")
```

Registry keys: `true-roas`, `roas`, `ad-roi`, `which-ads`, `spend-to-revenue`.
Signature: `build_true_roas(leads, ad_rows=None, deal_rows=None, orders=None, prior=None, ad_rows_prior=None, brand_profile=None, customer_name=None, customer_domain="", compare_label=None, form_label=None, prepared_by=None, prepared_for=None, **kwargs)`

| Source | Needed | What to request |
|---|---|---|
| UTM Grabber | Required | Entries for the window; `prior` adds deltas on spend, leads and cost per lead. |
| Google Ads, Meta Ads, Microsoft Ads | Required | Campaign, ad group, ad name, date, spend, clicks, impressions. Ad names must match the utm_content values on your ads. |
| HubSpot, Salesforce, Pipedrive | Optional | Deals with contact email, stage, amount, create and close dates. Adds customers, revenue, ROAS. |
| WooCommerce | Optional | Orders with their UTM fields (`orders=`), used when no deals are passed. Each order is matched by its own utm_campaign and utm_content. |

Without ad spend: a short version listing the leads your ads sent, pointing to the ad creative report.

## How the numbers work

- Leads match ads by utm_campaign (the campaign name), then utm_content (the ad name), ignoring case and punctuation. A tag one or two letters off counts for the closest campaign. Notes give the share that matched an ad, only a campaign, or nothing.
- Won deals match leads by lowercase email and are credited to that lead's ad; platform totals also include customers whose lead matched only a platform.
- Cost per lead = spend / leads. ROAS = revenue / spend. "Spend that didn't pay back" = ads with at least the larger of $50 or 1% of spend and no customers, or less than $1 back per $1. Ads whose only customers are open deals are shown as such, not cut.
- The headline counts how few ads brought half of the revenue (or leads).

## Section order

1. **title-block**: "*5 of your 21 ads* brought half of your ad revenue." Subtitle: their share of spend and the best ad's return per $1.
2. **stat-strip** (up to 6): ad spend (spark, delta), leads from ads, cost per lead, customers, revenue, ROAS. Without revenue: clicks.
3. **insight-card** "The takeaway": the best ad's return against the weakest ad's (without revenue: the cost-per-lead spread).
4. **section-header 01 The map** + **matrix**: leads (x) vs cost per lead (y), bubble = spend, grouped by platform (3 groups max), lines at the median and the average cost per lead.
5. **section-header 02 Winners** + **ranked-list**: top 10 ads by revenue: platform, spend, leads bar, customers, revenue, ROAS pill.
6. **section-header 03 Leaks** + **ranked-list**: spend that didn't pay back (or, without revenue, spend with no leads), with a status badge.
7. **section-header 04 Platforms** + **comparison** (two platforms) or **chart-insight** bar of ROAS (three or more).
8. **section-header 05 Next steps** + **recommendations**: move a named amount from the weakest ad to the best, cut back the next weakest, raise budget on a high-volume winner, pause zero-lead ads, tag utm_content, connect the CRM.
9. **notes** and **closing** ("Next: move $1,090 from *Carousel - Family Care* to ...").

Fewer than 10 leads from ads (or none tied to them): a short, honest version.

## Voice guidance

Media-buyer ready: name the ad, the dollars and the return per $1 in every recommendation. Judge an ad on customers and revenue, never on platform conversions. Say when a verdict waits on open deals.
