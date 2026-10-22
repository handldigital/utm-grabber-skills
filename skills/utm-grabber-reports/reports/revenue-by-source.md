# Revenue by Source

## Triggers

- `/revenue`
- `revenue by source`
- `woocommerce revenue`
- `sales by channel`
- `which campaigns made money`

## Purpose

Credits WooCommerce revenue to the channel, campaign and product behind each order, puts first touch next to last touch, and adds return on ad spend when spend is connected. Answers "where does our revenue come from, and where should the next dollar go?"

## Build it

```python
from recipes_v2 import get_recipe
summary = get_recipe("revenue")(orders, prior_orders, ad_rows=ad_rows,
                                brand_profile=brand, customer_domain="example.com")
```

Registry keys: `revenue`, `revenue-by-source`, `woocommerce`, `sales-by-source`.
Signature: `build_revenue(orders, prior_orders=None, ad_rows=None, leads=None, deal_rows=None, brand_profile=None, customer_name=None, customer_domain="", compare_label=None, form_label=None, prepared_by=None, prepared_for=None, ad_rows_prior=None, deal_rows_prior=None, leads_prior=None, **kwargs)`

- `orders`: WooCommerce order entries from the UTM Grabber MCP. Totals, status, dates and products go through `connectors.normalize_orders`; channels come from the UTM Grabber fields on each raw order.
- `prior_orders` (optional): the previous period, for every delta and the dashed daily line.
- `ad_rows`, `ad_rows_prior` (optional): AdRow lists for return on ad spend.
- `leads` + `deal_rows` (+ `deal_rows_prior`, `leads_prior`): used only when there are no orders. Won deals become the sales, dated by when each deal was created and credited through the lead with the same email.

## Data

| Field | Plan | Used for |
|---|---|---|
| WooCommerce orders with UTM Grabber fields (total, status, date, products) | Premium | Every number |
| First-touch fields on each order | Premium | First vs last touch |
| `organic_source_str (HandL)`, `handl_ref_domain (HandL)` on orders | Premium | AI assistants and search engines |
| Won CRM deals joined to UTM Grabber leads | Free + CRM | Fallback without a store |

## How the numbers work

- Revenue: completed and processing orders. Refunded orders appear under Refunds; cancelled, failed and pending orders are left out.
- Channel: the order's last-touch channel (paid search, paid social, organic search, AI assistants, email, organic social, referral, direct).
- Return on ad spend: revenue from orders whose last click was an ad on a platform in the ad rows, divided by that spend. Ad rows are cut to the order dates. The spark is a rolling 7-day ratio.
- Top product per channel: the product in the most of that channel's orders. "Sells more of": the product whose share of the channel's orders is highest against its share of all orders (5+ orders).

## Section order

1. **title-block**: revenue and the change vs the prior period. Subtitle: top channel, top campaign, return on ad spend.
2. **stat-strip**: revenue, orders, average order value (rolling spark), refunds (good when down), return on ad spend.
3. **insight-card** "The takeaway": the top channel's revenue and share, the runner-up, untagged revenue.
4. **section-header 01 By channel** + **chart-insight** (bar-horizontal in dollars, orders and average under each row; insight on the highest order value).
5. **section-header 02 By campaign** + **ranked-list** (top 8): campaign, utm_campaign (mono), revenue bar, orders, average value, share, change.
6. **section-header 03 First vs last touch** + **comparison** (top 6 channels) when 10+ orders carry first touch.
7. **section-header 04 Day by day** + **chart** (line-multi, prior period dashed).
8. **section-header 05 Products** + **ranked-list** (top 6 channels) when most orders list products.
9. **section-header Next steps** + **recommendations**: scale the campaign whose revenue rose the most (up 20%+), find out why a campaign slowed, credit the channel that finds buyers, tag untagged orders (15%+ of revenue), look into refunds (4%+ of orders), hold spend to the ROAS floor.
10. **notes** and **closing** (next step with the number behind it).

Short versions: no orders and no won deals (how to connect a store or CRM); fewer than 10 sales (every sale listed with its channel).

## Voice guidance

Owner to owner, money first. Lead with revenue, not order counts. Say "orders" for a store and "won deals" for a CRM. Return on ad spend counts ad-click revenue only; never present it as total revenue divided by spend.
