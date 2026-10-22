# Agency Client Rollup

## Triggers

- `/rollup`
- "agency rollup", "all clients", "portfolio view", "all brands"

## Purpose

Every client on one page for an agency owner: who grew, who slipped, whose tagging needs work, and who to call first.

## Build it

```python
from recipes_v2 import get_recipe
clients = [{"name": "Northwind Dental", "domain": "northwinddental.com",
            "leads": nw_current, "leads_prior": nw_prior}, ...]
summary = get_recipe("agency-rollup")(clients, brand_profile=agency_brand, prepared_by="Brightline Agency")
```

Registry keys: `agency-rollup`, `rollup`, `portfolio`.
Signature: `build_agency_rollup(brand_data_list, brand_profile=None, customer_name=None, customer_domain="", form_label=None, compare_label=None, prepared_by=None, prepared_for=None, **kwargs)`

- Each item: `brand_name` or `name`; `entries` or `leads` (this window); `entries_prior` or `leads_prior` (optional, same-length earlier window); `domain` (optional, used in the call-to-action).
- A client counts as up or down when it moved by 5+ leads and 10%+. An empty prior list marks the client as new.

## Section order

1. **title-block**: "The portfolio grew 12% to *1,292 leads*." Subtitle: clients up and down, the biggest client's share, who slipped most.
2. **stat-strip**: portfolio leads (daily spark; change when every client has a prior), clients up, clients down, average tagging (plain average of clients) with the lowest client.
3. **01 The book**: table of up to 12 clients: leads bar, change, tagged badge (green 80%+, amber 50% to 79%, red under 50%), top source, daily spark. The client that slipped most is highlighted.
4. **callouts**: best client, needs attention, tagging gap (under 60%), biggest client's share.
5. **02 Growth map** (3+ clients with a prior): leads vs change, quadrants Growing, Big slipping, Small growing, At risk.
6. **03 Next steps**: call the client that fell most, fix tagging for the lowest client, pitch more work to the best grower, lower reliance on a client with 40%+ of portfolio leads.
7. **notes** and **closing**: "Next: call *Saltmarsh Family Law*. Its leads fell 28% this period."

## Voice guidance

Agency-owner tone: every client is money at stake. Recommendations are operational (who to call, which audit to run) and always name the client and the number.
