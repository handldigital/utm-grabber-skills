# Landing Page Performance

## Triggers

- `/landing-pages`
- `landing page performance`
- `best pages`
- `page performance`

## Purpose

Ranks landing pages by leads, shows each page's biggest source, and flags pages where leads arrive with no UTMs. Answers "which pages bring leads, from where, and which ones lose attribution on the way in?"

## Build it

```python
from recipes_v2 import get_recipe
summary = get_recipe("landing-page")(current, prior, brand_profile=brand, customer_domain="example.com")
```

Registry keys: `landing-page`, `landing-pages`, `pages`, `landing-page-performance`.
Signature: `build_landing_page(current, prior=None, brand_profile=None, customer_name=None, customer_domain="", compare_label=None, prepared_by=None, prepared_for=None, **kwargs)`

- `current`: UTM Grabber entries for the period.
- `prior` (optional): adds the change column, rising and falling page recommendations, and the tagged-share delta.

## How the numbers work

- Page = the first-touch landing page when UTM Grabber recorded one, else `handl_landing_page (HandL)`, else `Source URL`. The notes say how many leads used each.
- Paths are normalized: no domain, query string, fragment, trailing slash or letter case.
- Tagged = the lead carried at least one of utm_source, utm_medium or utm_campaign.
- Leak check: a page needs a fix when 30% or more of its leads arrive untagged; it is watched from 10%, or when any paid click (gclid, fbclid, msclkid) arrives untagged. The table's Tagged badge uses the same thresholds, so colors and verdicts always agree.
- Untagged paid clicks are also counted site-wide: they usually share one root cause (a missing tracking template), so the first recommendation fixes the platform, not page by page.

## Section order

1. **title-block**: headline names the top page and its share. Subtitle gives page count, top-three share and how many pages leak.
2. **stat-strip**: leads (spark, delta), pages with leads, top three share, tagged leads (pts delta), paid clicks untagged.
3. **insight-card** "The takeaway": the top page, its biggest source, the runner-up.
4. **section-header 01 Top pages** + **chart** (bar-horizontal, top 8, biggest source under each path) + **ranked-list**: path (mono), leads bar, share, top source, Tagged badge, change vs prior.
5. **section-header 02 Attribution leaks** + **scorecard**: up to five leaking pages with the fix, one line for the rest to watch, one line for the pages that pass.
6. **section-header 03 Next steps** + **recommendations**: add UTMs to the platform whose clicks arrive untagged, fix tagging on the worst page, check a falling page's form, find out why a page grew, use the top page as the template, test the top three forms.
7. **notes**: page basis, normalization, leak rules.
8. **closing**: next step with the number behind it.

Fewer than 10 leads with a page: a short version listing the pages.

## Voice guidance

Page-level and tactical: headlines, offers, forms, the links that feed a page. Without sessions we can't judge conversion rate, so never call a page "weak" for having fewer leads; talk about volume, sources and tags.
