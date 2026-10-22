# Customer Journeys

## Triggers

- `/journey`
- `customer journey`
- `first touch vs last touch`
- `multi-touch attribution`
- `which channels start journeys`

## Purpose

Connects each lead's first visit to the visit that converted, shows the paths between channels, and gives every channel fair credit three ways: first touch, last touch and a 50/50 split. Names the channel that last-click reporting undervalues most. Answers "which channels find people, and which only close them?"

## Build it

```python
from recipes_v2 import get_recipe
summary = get_recipe("journey")(leads, prior, deal_rows=deal_rows, orders=orders,
                                brand_profile=brand, customer_domain="example.com")
```

Registry keys: `journey`, `customer-journey`, `first-to-last`, `multi-touch`, `attribution-paths`.
Signature: `build_journey(leads, prior=None, deal_rows=None, orders=None, brand_profile=None, customer_name=None, customer_domain="", compare_label=None, form_label=None, prepared_by=None, prepared_for=None, **kwargs)`

- `leads`: UTM Grabber entries for the period.
- `prior` (optional): adds the change in the share of leads that changed channel.
- `deal_rows` (optional): won deals are credited the same three ways, through the lead with the same email.
- `orders` (optional): WooCommerce order entries from the UTM Grabber MCP. They carry their own first touch and take priority over deals for revenue credit.

## Data

| Field | Plan | Used for |
|---|---|---|
| `traffic_source`, `utm_source`, `utm_medium` (first touch, HandL) | Premium | First-touch channel |
| `referrer (first touch, HandL)`, `landing_page (first touch, HandL)` (click IDs in the URL) | Premium | First-touch channel |
| `organic_source_str (HandL)`, `handl_ref_domain (HandL)` | Premium | AI assistants and search engines |
| utm fields, click IDs, `traffic_source (HandL)` | Free | Last-touch channel |

## How the numbers work

- Channels: paid search, paid social, other paid, organic search, AI assistants, email, organic social, referral, direct. The same rules classify both touches.
- 50/50 split: each lead gives half its credit to each touch; a lead that stayed on one channel gives that channel full credit. "Split vs last" is the split minus last-touch credit.
- Undervalued: the split gives the channel at least 10% more than last click does (and 1% of the total). Overcredited is the reverse; Even otherwise.
- Most undervalued: the largest gap between first-touch and last-touch credit. It must be 3+ leads and 10% of its last-touch count before the headline names it.
- The flow and the bar chart keep the 5 biggest channels and fold the rest into Other, so each side has 6 nodes at most.
- Leads without first-touch data are left out and counted in the notes.

## Section order

1. **title-block**: "{Channel} opens N journeys but closes only M." Subtitle: the share that changed channel, and the top closer.
2. **stat-strip**: leads traced, changed channel (pts vs prior), top opener, top closer, revenue traced.
3. **insight-card** "The takeaway": how much last click undervalues the channel, and which channel it flatters.
4. **section-header 01 The paths** + **flow** (first visit to converting visit).
5. **section-header 02 Openers vs closers** + **chart** (bar-grouped, full width so every channel name fits) + **insight-card**.
6. **section-header 03 Fair credit** + **ranked-list** of lead credit and, with deals or orders, a **ranked-list** of revenue credit: first touch bar, last touch, 50/50 split, split vs last, Undervalued / Overcredited / Even badge.
7. **section-header 04 Next steps** + **recommendations**: judge the undervalued channel on first touch (or keep a paid opener funded), keep the closer and fund its openers, count AI assistants as an opener, credit the channel that finds revenue, review both touches monthly.
8. **notes**: definitions, channel rules, exclusions, revenue source.
9. **closing**: judge the undervalued channel on first touch, with its counts.

Short versions: fewer than 10 leads; fewer than 10 leads with first-touch data (explains that UTM Grabber Premium records the first visit, and shows today's last-touch mix).

## Voice guidance

Fair and plain: "opens" and "closes", never "attribution model". The point is budget, so always say what last click would wrongly tell you to cut, and name the closer that depends on it.
