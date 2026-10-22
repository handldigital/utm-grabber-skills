# Report specs (v2)

Every report: live data in, a recipe builds the summary, `build_report()` writes HTML, PDF or PowerPoint in any of the four themes.

```python
from recipes_v2 import get_recipe
from build_report import build_report
summary = get_recipe("monthly")(leads, prior, brand_profile=brand, customer_domain="acme.com")
build_report(summary, "/mnt/user-data/outputs/monthly-2026-10-05.html", theme="studio")
```

Each spec in this folder states:
1. **Purpose**: the question the report answers and when to run it.
2. **Data**: what to pull (UTM Grabber window, prior window, other connectors) and the recipe signature.
3. **Sections**: the order the recipe produces.
4. **Voice**: what the headline and recommendations should emphasize.

Before changing or extending a report, read `references/report-schema.md` (section types and writing rules) and `references/themes.md`.

## Index

**Core performance**
- `monthly-performance-review.md` (`monthly`): the 30-day story, the flagship
- `weekly-executive-summary.md` (`weekly`): the 7-day one-pager
- `daily-pulse.md` (`daily-pulse`): yesterday vs the 7-day average, one page
- `quarterly-business-review.md` (`qbr`): the quarter vs the previous one, board-ready
- `top-campaign-leaderboard.md` (`leaderboard`): every campaign ranked, scale vs fix map
- `campaign-deep-dive.md` (`campaign-deep-dive`): one campaign end to end, with a verdict
- `paid-vs-organic.md` (`paid-vs-organic`): the fundamental split
- `anomaly-detector.md` (`anomaly`): what changed and what broke
- `predictive-forecast.md` (`forecast`): next week and month with a range
- `side-by-side-comparison.md` (`side-by-side`): any two segments compared
- `agency-client-rollup.md` (`agency-rollup`): every client on one page

**Leads, forms and tracking**
- `utm-hygiene-audit.md` (`audit`): where attribution leaks, in fix order
- `lead-quality-scorer.md` (`lead-scorer`): who to call first and why
- `lead-profile-enrichment.md` (`lead-profile`): one lead's full journey
- `form-performance.md` (`form-performance`): every form, including dormant ones
- `landing-page-performance.md` (`landing-page`): pages that win and pages that leak
- `source-to-crm-mapping.md` (`source-to-crm`): sources per declared CRM
- `lead-timing.md` (`lead-timing`): the day x hour map of when leads arrive

**Paid media, revenue and journeys**
- `ad-creative-performance.md` (`ad-creative`): utm_content winners and fatigue
- `keyword-performance.md` (`keyword`): utm_term by intent
- `budget-simulator.md` (`budget-simulator`): what-if budget shifts with a range
- `revenue-by-source.md` (`revenue`): WooCommerce revenue by channel and campaign
- `ai-assistant-referrals.md` (`ai-referrals`): leads from ChatGPT, Perplexity, Gemini, Claude, Copilot
- `customer-journey.md` (`journey`): first touch to last touch, fair credit per channel

**Cross-platform** (see `references/connectors.md`)
- `full-funnel.md` (`full-funnel`): visits to leads to customers to revenue
- `true-roas.md` (`true-roas`): which ads brought customers, cost per customer, ROAS
- `conversion-truth.md` (`conversion-truth`): what ad platforms report vs real leads
- `traffic-to-lead.md` (`traffic-to-lead`): traffic that never converts
- `pipeline-by-source.md` (`pipeline`): close rate and revenue by first touch
- `wasted-spend.md` (`wasted-spend`): spend that produced no leads

The v1 specs' recipes (`scripts/report_recipes.py`) remain for old summaries; new work uses `recipes_v2`.
