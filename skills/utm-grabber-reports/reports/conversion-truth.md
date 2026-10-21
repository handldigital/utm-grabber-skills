# Ad Platforms vs Reality (Conversion Truth)

## Triggers

- `/conversion-truth`
- `are my ad platforms over-reporting`
- `platform conversions vs real leads`
- `reconcile Google Ads and Meta conversions`

## Purpose

Puts what Google Ads, Meta Ads and Microsoft Ads say they converted next to the leads UTM Grabber actually captured from them, by platform and by campaign. Shows how much each platform over-reports, what that does to cost per lead, and whether your leads carry the click IDs needed to send real leads back so the platforms bid on reality. Answers "how many of the conversions my platforms report are real?"

## Build it

```python
from recipes_v2 import get_recipe
summary = get_recipe("conversion-truth")(leads, ad_rows=ads, prior=prior, ad_rows_prior=ads_prior,
                                         brand_profile=brand, customer_domain="example.com")
```

Registry keys: `conversion-truth`, `platform-vs-reality`, `over-reporting`, `reconciliation`.
Signature: `build_conversion_truth(leads, ad_rows=None, prior=None, ad_rows_prior=None, brand_profile=None, customer_name=None, customer_domain="", compare_label=None, form_label=None, prepared_by=None, prepared_for=None, **kwargs)`

| Source | Needed | What to request |
|---|---|---|
| UTM Grabber | Required | Entries for the window; `prior` adds last period's over-reporting. |
| Google Ads, Meta Ads, Microsoft Ads | Required | Campaign x day: conversions (Google `metrics.conversions`, Meta `results` or leads), spend, clicks. Same window as the leads. |

Without ad data, or with ad data that has no conversions: a short version that says what to request.

## How the numbers work

- Reported = conversions as each platform counts them (its own attribution window and conversion actions).
- Real = form submissions in the same window credited to that platform by utm_source and utm_medium or a click ID.
- Campaigns match when utm_campaign equals the campaign name, ignoring case and punctuation; tags one or two letters off count for the closest campaign. Leads with no campaign tag, or a tag that matches nothing, get their own grey lines so every real lead is shown.
- Over-reported = (reported - real) / real. Status: Matches within 10%, Over-reports 10% to 40%, Far over above 40%, Not tracked when the platform reports none.
- Click-ID capture: share of each platform's leads with gclid (or wbraid/gbraid), fbclid or msclkid; Healthy at 90%+, Watch from 60%, Fix below. Plus the share of ad leads with an email.

## Section order

1. **title-block**: "Your ad platforms counted *175 conversions* your forms never got." Subtitle: reported vs real per platform, and the furthest-off campaign.
2. **section-header 01 The gap** + **callouts** (platforms said / your forms got / over-reported, with last period) + **chart-insight** (waterfall: reported, each platform's overcount, leads your forms got) with the worst platform and its real cost per lead.
3. **section-header 02 By campaign** + **ranked-list**: campaign, platform, reported, real leads bar, over-reported, status badge, Total line.
4. **section-header 03 Ready to send back** + **scorecard**: click-ID capture per platform and email on ad leads.
5. **section-header 04 Next steps** + **recommendations**: send real leads back to the worst platform (offline conversions for Google and Microsoft, server-side conversions for Meta; UTM Grabber Premium can send them), judge the worst campaign on real leads with both costs, keep the click ID, fix mistyped campaign tags.
6. **notes** and **closing** ("Next: send real leads back to *Meta Ads*. It over-reported by 28%.").

Fewer than 10 leads from the platforms (or none carrying their tags): a short, honest version.

## Voice guidance

Calm and factual: platforms count differently, they are not lying. Lead with the gap in leads, then its cost: the real cost per lead next to the platform's cost per conversion. Say "UTM Grabber Premium", never "V3". No technical words about how data moves.
