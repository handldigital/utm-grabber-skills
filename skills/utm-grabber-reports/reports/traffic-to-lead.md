# Traffic That Never Converts (Traffic to Lead)

## Triggers

- `/traffic-to-lead`
- `traffic that never converts`
- `visits but no leads`
- `lead rate by page`
- `conversion rate by channel`

## Purpose

Divides UTM Grabber leads by Google Analytics 4 sessions, channel by channel, source by source and page by page. Finds the busy pages with almost no leads, the channels whose visitors rarely convert, and the hidden gems that convert well on little traffic. Answers "where do visitors come and leave without becoming leads?"

## Build it

```python
from recipes_v2 import get_recipe
summary = get_recipe("traffic-to-lead")(leads, visit_rows=visits, prior=prior, visit_rows_prior=visits_prior,
                                        brand_profile=brand, customer_domain="example.com")
```

Registry keys: `traffic-to-lead`, `traffic-leaks`, `visits-no-leads`, `conversion-rate`.
Signature: `build_traffic_to_lead(leads, visit_rows=None, prior=None, visit_rows_prior=None, brand_profile=None, customer_name=None, customer_domain="", compare_label=None, form_label=None, prepared_by=None, prepared_for=None, **kwargs)`

| Source | Needed | What to request |
|---|---|---|
| UTM Grabber | Required | Entries for the window; `prior` adds deltas. |
| Google Analytics 4 | Required | Dimensions `sessionSource`, `sessionMedium` (or `sessionSourceMedium`), `landingPagePlusQueryString`, `date`; metrics `sessions`, `engagedSessions`. Same window as the leads, plus the prior window. |

Without GA4: a short version with leads by channel, pointing to the landing page report.

## How the numbers work

- Lead rate = leads / sessions. Channels use UTM Grabber's rules on both sides (ad platforms split out; AI assistants count as Organic, email as Referral).
- Source / medium: a lead with UTM tags uses them; an untagged lead is placed the way analytics would place its visit (gclid means google / cpc, then search engine, then referring site), else (direct) / (none).
- A lead's page is the landing page of the visit that ended in the form (first-touch page or form page as fallbacks), matched to GA4 landing pages by path, lowercase, without query strings.
- A page leaks when it has at least the larger of 100 sessions or 1% of all sessions and a lead rate under a quarter of the site-wide rate (and under 1%). Careers, legal, login, cart and thank-you pages are shown but never counted as leaks. Blog-style paths get "Add a call to action"; other pages "Add a form".
- Hidden gem: a top-15 page with fewer sessions than the median, 5+ leads and 1.5 times the site rate.

## Section order

1. **title-block**: "*2 busy pages* drew 4,928 sessions and 0 leads." (or the site rate and best channel when nothing leaks). Subtitle: site rate, best vs weakest channel.
2. **stat-strip** (up to 5): sessions and leads (sparks, deltas), lead rate (pts), sessions on leaking pages, engaged sessions.
3. **section-header 01 By channel** + **chart-insight** (bar of lead rate by channel) + **ranked-list** of the top 12 source / medium pairs with a status badge.
4. **section-header 02 Landing pages** + **matrix** (sessions vs lead rate, bubble = sessions, grouped as blog, site and not-lead pages) + **ranked-list** "Traffic that never converts" with the fix for each page.
5. **section-header 03 Next steps** + **recommendations**: add a call to action or form to the top leaking pages, send traffic to the hidden gem, fix where a big channel's visitors land (never Direct), line up UTM names that analytics never saw.
6. **notes** and **closing** ("Next: add a call to action to */blog/...*. It drew 3,303 sessions and 0 leads.").

Fewer than 10 leads: a short version.

## Voice guidance

Website-owner ready: pages, buttons, forms. Quote paths exactly. A page with no form is not broken, it is missing a next step; say what to add.
