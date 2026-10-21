# Cross-platform reports: combining UTM Grabber with ads, analytics, CRM and revenue

UTM Grabber knows where every lead came from. Other connectors in the same AI app know the rest. Cross-platform reports pull from each connector, normalize the rows, and join them to UTM Grabber leads with `scripts/connectors.py`.

**Never fabricate a number from a platform that is not connected.** If a report needs spend and no ad connector is available, run the UTM Grabber part, say plainly what is missing, and offer the closest report that works without it.

## What each source contributes

| Source | Connector examples | Rows we need | Normalizer |
|---|---|---|---|
| Leads (always) | UTM Grabber MCP `get_entries` | entries | `helpers.load_entries([...])` |
| Revenue (WooCommerce) | UTM Grabber MCP with form plugin `woocommerce` | orders | `connectors.normalize_orders(entries)` |
| Ad spend | Google Ads, Meta Ads, Microsoft Ads, LinkedIn Ads | campaign (and ad, keyword) x day: spend, clicks, impressions, conversions | `connectors.normalize_ad_rows(rows, platform="Google Ads")` |
| Visits | Google Analytics 4 | source, medium, landing page x day: sessions, engaged sessions | `connectors.normalize_visit_rows(rows)` |
| Deals | HubSpot, Salesforce, Pipedrive | deal: contact email, stage, amount, created, closed | `connectors.normalize_deal_rows(rows)` |

The normalizers accept the field names those connectors commonly return (`metrics.cost_micros`, `campaign.name`, `spend`, `sessionSource`, `sessionSourceMedium`, `landingPagePlusQueryString`, `dealstage`, `closedate`, `amount` ...). Unknown fields are ignored.

## What to request from each connector

- **Google Ads:** campaign name, ad group name, ad name (or ad id), keyword or search term, date, cost (`cost_micros`), clicks, impressions, conversions, conversion value. Same date window as the leads. Search-term rows are optional (wasted-spend report).
- **Meta Ads:** campaign name, ad set name, ad name, date, spend, impressions, link clicks, results/leads (platform-reported).
- **GA4:** dimensions `sessionSource`, `sessionMedium` (or `sessionSourceMedium`), `landingPagePlusQueryString`, `date`; metrics `sessions`, `engagedSessions`, `keyEvents`.
- **HubSpot / Salesforce / Pipedrive:** deals created in the window (plus deals closed in the window), with the associated contact email, stage, amount, create date, close date.

Pull every source for the same window. For period comparisons, pull the prior window too, in the same parallel batch.

## How rows are joined (and what to say about it)

| Join | Rule | Match rate the notes report |
|---|---|---|
| Ads to leads | `utm_campaign` == campaign name (normalized: lowercase, punctuation to `_`), then `utm_content` == ad name for ad-level reports | share of paid leads matched to a campaign |
| Visits to leads | (`utm_source`, `utm_medium`) == (session source, session medium); landing pages by path | per channel |
| Deals to leads | lowercase email | share of deals matched to a lead |
| Orders to leads | the order's own UTM fields (WooCommerce orders carry them), else email | share of orders with a source |

Match rates are always computed from the pulled rows. Never quote a "typical" rate.

Every cross-platform report ends with a `notes` section stating the window, each source and the join rule, plus the share of rows that matched. Example: "Leads matched to ad campaigns by utm_campaign; 91% of paid leads matched a campaign."

When matching is weak (for example many leads without a campaign tag), say so in the report and point to the UTM hygiene audit.

## Recipes that use connectors

| Report key | Needs | Optional |
|---|---|---|
| `full-funnel` | leads | ad_rows, visit_rows, deal_rows or orders (each adds a funnel stage) |
| `true-roas` | leads + ad_rows | deal_rows or orders (adds customers, revenue, ROAS) |
| `conversion-truth` | leads + ad_rows | none |
| `traffic-to-lead` | leads + visit_rows | none |
| `pipeline` | leads + deal_rows | ad_rows (adds cost per customer) |
| `wasted-spend` | leads + ad_rows with keyword/search-term rows | none |
| `revenue` | orders (or deal_rows) | ad_rows (adds ROAS) |

Pass connector rows as keyword arguments: `get_recipe("true-roas")(leads, ad_rows=ads, deal_rows=deals, brand_profile=brand, ...)`.

## Customer-facing language

Say "your Google Ads account", "your HubSpot", "your analytics". Never say connector, MCP, API, rows, join, or normalize. If a platform is missing: "Connect your Google Ads to this chat and I'll add spend and cost per lead to this report."
