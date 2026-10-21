# Tracking Audit (UTM Hygiene)

## Triggers

- `/audit`
- `hygiene audit`
- `utm audit`
- `tagging audit`
- `tracking audit`
- `attribution leaks`

## Purpose

Scores tracking health and names each specific leak: paid clicks that lost their tags, missing click IDs, split spellings, campaign typos, pages that drop tags. Answers "where is my attribution leaking, and what do I fix first?"

## Build it

```python
from recipes_v2 import get_recipe
summary = get_recipe("audit")(current, prior, brand_profile=brand, customer_domain="example.com")
```

Registry keys: `audit`, `hygiene`, `utm-audit`, `utm-hygiene-audit`, `tracking-audit`.
Signature: `build_audit(current, prior=None, brand_profile=None, customer_name=None, customer_domain="", compare_label=None, prepared_by=None, prepared_for=None, **kwargs)`

- `current`: UTM Grabber entries for the period.
- `prior` (optional): adds the score's change in points.

## The seven checks (scorecard order)

1. **Full UTM coverage on campaign traffic**: ads, email and social leads with source, medium and campaign (pass 90%, watch 70%). Organic, referral and direct visits are left out because they never carry a campaign, and so are sites that add only utm_source on their own (chatgpt.com, perplexity.ai).
2. **Paid clicks that lost their UTMs**: a gclid, fbclid or msclkid with no UTMs.
3. **Google click ID on Google Ads leads** (google with a paid medium; pass 90%, watch 60%).
4. **Meta click ID on Meta Ads leads** (facebook or instagram with a paid medium).
5. **One spelling per source, medium and campaign**: values that match once case and punctuation are ignored.
6. **Campaign names that look like typos**: names one or two edits away from a campaign with more leads, counted once each with the leads they split off. Numbered series and short variants like `_us` / `_uk` are skipped.
7. **Landing pages losing tags**: half or more of a page's leads (3 or more) arrive with no UTMs.

A check with nothing to measure shows as Info and does not count toward "checks passed".

## Section order

1. **title-block**: headline leads with the costliest leak (paid clicks with no UTMs), else the fully tagged share and how many checks need a fix. It only says every check passed when at least four checks ran. Subtitle: checks passed and what to fix first.
2. **hero-number**: tracking health score = share of leads fully tagged, with the change in points and a weekly spark.
3. **stat-strip**: leads audited, no UTMs at all, paid clicks untagged, checks passed.
4. **section-header 01 The checks** + **scorecard** (the seven checks, each with its count and fix).
5. **section-header 02 Where tags go missing** + **chart-insight** (bar-horizontal of tagging states) + **ranked-list** of pages losing tags (only when a page lost 2 or more, or any paid click) + **ranked-list** of campaign traffic missing part of its tags.
6. **section-header 03 Fix order** + **recommendations** in fix-priority order, "This week" first, ending with "Rerun this audit after the fixes".
7. **notes**: definitions and thresholds.
8. **closing**: the first fix with the number behind it.

Fewer than 10 leads: a spot check (score, scorecard and a note on why it is short).

## Voice guidance

Diagnostic, not alarmist. Every leak has a root cause and a concrete fix (auto-tagging, tracking template, final URL, naming sheet). Recommendations name the action, not the problem.
