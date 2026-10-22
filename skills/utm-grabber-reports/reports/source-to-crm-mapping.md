# Source to CRM Mapping

## Triggers

- `/source-crm`
- "source to crm", "crm by source", "which sources feed which crms"

## Purpose

For B2B forms that ask "Which CRM do you use?": which UTM sources bring leads on which CRM, and where a channel clearly leans toward one stack. Answers "how should messaging change by channel?"

## Build it

```python
from recipes_v2 import get_recipe
summary = get_recipe("source-to-crm")(current, prior, brand_profile=brand, customer_domain="acme.com")
```

Registry keys: `source-to-crm`, `source-crm`, `crm`.
Signature: `build_source_to_crm(current, prior=None, brand_profile=None, customer_name=None, customer_domain="", form_label=None, compare_label=None, prepared_by=None, prepared_for=None, crm_field=None, **kwargs)`

- The CRM question is found automatically (any form field whose label contains "crm"); pass `crm_field="Your CRM"` to force one.
- Answers are grouped by spelling (hubspot and HubSpot); "none" or "no" shows as No CRM.
- No CRM field: a one-page honest report with the exact question to add. Under 10 answers: a short version asking to make the question required.
- `prior` (optional, 10+ leads): adds deltas on the answer rate and the top CRM's share.

## Section order

1. **title-block**: "*Salesforce* leads the CRM answers at 26%, mostly from Google." Subtitle: how many answered and the clearest pairing.
2. **stat-strip**: answered the CRM question (pts), CRMs named, the top CRM's share (pts), no CRM yet.
3. **01 The map**: heatmap of top sources (plus "No UTM source") by CRM, then an insight on the strongest pairing by lift: "LinkedIn leads name *HubSpot* 3.2x as often as average." A pairing needs 5+ leads and an excess beyond 2 standard deviations; otherwise the card says no source leans hard.
4. **02 By CRM**: table: CRM, leads bar, share, top source, and the source it leans toward (1.2x or more).
5. **03 Next steps**: speak the CRM in that channel's ads, build a CRM-specific landing page for the second pairing, give no-CRM leads their own path (15%+), make the question required (under 70% answered), tag untagged answers (25%+).
6. **notes** and **closing**: "Next: speak *HubSpot* in LinkedIn ads. 65% of those leads use it."

## Voice guidance

B2B sophistication: a CRM signals company maturity and budget. Only call a pairing a pattern when the rule says so; small samples are named as such, not dressed up.
