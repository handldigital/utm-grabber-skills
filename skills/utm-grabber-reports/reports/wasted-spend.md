# Wasted Spend Finder

## Triggers

- `/wasted-spend`
- `wasted ad spend`
- `which keywords waste money`
- `negative keywords`
- `spend with no leads`

## Purpose

Finds the search terms and ads that spend money without bringing a lead, totals that waste, and says what to do with each: add a negative, fix the landing page, or watch. Answers "where is my ad budget going with nothing to show for it?"

## Build it

```python
from recipes_v2 import get_recipe
summary = get_recipe("wasted-spend")(leads, ad_rows=ads, brand_profile=brand, customer_domain="example.com")
```

Registry keys: `wasted-spend`, `wasted`, `zero-lead-spend`, `negative-keywords`.
Signature: `build_wasted_spend(leads, ad_rows=None, brand_profile=None, customer_name=None, customer_domain="", compare_label=None, form_label=None, prepared_by=None, prepared_for=None, **kwargs)`

| Source | Needed | What to request |
|---|---|---|
| UTM Grabber | Required | Entries for the window, with utm_term on search leads. |
| Google Ads, Microsoft Ads | Required for keywords | Keyword or search-term rows: campaign, ad group, keyword (or search term), date, spend, clicks, impressions, conversions. |
| Meta Ads and other ads without keywords | Optional | Campaign, ad name, date, spend, clicks. Checked at the ad level. |

Without ad data: a short version pointing to the keyword report. With keywords but no lead carrying utm_term, the report works at the ad level and says how to add utm_term.

## How the numbers work

- Leads match search terms by utm_term within the same campaign (case, quotes and match-type symbols ignored); a lead whose campaign tag matches nothing is matched by term alone on its platform. Ads without keyword rows match by utm_campaign, then utm_content.
- Wasted spend = spend on search terms and ads with zero leads. Costly terms are flagged but never counted as waste.
- Add negative: no leads and no platform conversions after 10+ clicks, or a term with a no-intent word (jobs, free, diy, how to, course and similar). Fix landing page: the platform counted conversions but no form lead came through. Watch: fewer than 10 clicks, or leads at 2.5 times the average keyword cost per lead (on the larger of $100 or 2% of keyword spend).
- If fewer than 60% of search leads carry utm_term, a warning card says some terms may have brought leads we can't see.

## Section order

1. **title-block**: "*$1,244* of ad spend brought no leads." Subtitle: the biggest single waste and the average cost per keyword lead.
2. **hero-number**: spend with no leads, with its share of total ad spend.
3. **stat-strip** (up to 5): search term spend, terms with spend, terms with no leads, cost per keyword lead, ads with no leads.
4. **section-header 01 Search terms** + **ranked-list**: term (mono), campaign, spend, clicks, leads, cost per lead, action badge.
5. **section-header 02 By campaign** + **chart** (bar of wasted spend by campaign) + **insight-card** on the biggest leak + **ranked-list** of ads with no (or very costly) leads.
6. **section-header 03 Next steps** + **recommendations**: add the negatives (named, with the dollars), fix the landing page, pause zero-lead ads, lower the bid on a costly term, pass the keyword in utm_term.
7. **notes** and **closing** ("Next: add 3 *negative keywords*. They spent $1,244 with no leads.").

Fewer than 10 leads from ads (or none carrying their tags): a short, honest version.

## Voice guidance

PPC-manager ready: negatives, match types, bids, tracking templates. Quote search terms exactly. Never call spend wasted when the leads simply weren't tagged; say so instead.
