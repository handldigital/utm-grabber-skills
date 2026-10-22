# Keyword Performance

## Triggers

- `/keywords`
- `keyword performance`
- `which keywords`
- `utm_term performance`
- `search terms`

## Purpose

Ranks search terms (utm_term) by leads and sorts each one by intent with plain, visible rules: brand, competitor, problem or urgent, generic. Answers "what were people searching for when they became leads, and which terms deserve more budget?"

## Build it

```python
from recipes_v2 import get_recipe
summary = get_recipe("keyword")(current, prior, competitors=["Acme Dental", "smileco"],
                                ad_rows=ad_rows, brand_profile=brand, customer_domain="example.com")
```

Registry keys: `keyword`, `keywords`, `keyword-performance`, `utm-term`, `search-terms`.
Signature: `build_keyword(current, prior=None, competitors=None, brand_terms=None, ad_rows=None, brand_profile=None, customer_name=None, customer_domain="", compare_label=None, prepared_by=None, prepared_for=None, **kwargs)`

- `current`: UTM Grabber entries for the period.
- `prior` (optional): adds change columns and intent-share deltas.
- `competitors` (optional): competitor names. Without it no term is marked competitor, and the chart says so.
- `brand_terms` (optional): extra brand words beyond the customer name and domain.
- `ad_rows` (optional): AdRow list with keyword text. Adds keyword spend, a cost per lead column and negative-keyword suggestions.

## Intent rules (first match wins)

1. **Brand**: the term contains the customer name (with or without spaces), the domain stem, a distinctive word of the name (5+ letters, not a common business word like dental or marketing), or a `brand_terms` entry.
2. **Competitor**: the term contains a name from `competitors`.
3. **Problem or urgent**: the term contains emergency, urgent, near me, now, today, fix, repair, broken, pain, cost, price, quote, cheap, affordable and similar words (full list in the notes section).
4. **Generic**: everything else.

Terms are grouped ignoring case, quotes and match-type symbols. Negatives are suggested only when ad rows show spend on a term with no leads.

## Section order

1. **title-block**: headline names the intent that brought the most keyword leads. Subtitle names the top term and counts paid search leads with no keyword.
2. **stat-strip** (up to 5, in this priority): keyword leads (spark, delta), brand share (pts delta), urgent share when present, keyword spend when connected, paid search leads with no keyword, search terms, top term share.
3. **section-header 01 Search intent** + **chart-insight** (bar-horizontal of the four intents, terms per intent as notes).
4. **section-header 02 Keywords** + **ranked-list**: keyword (mono), intent badge, leads bar, share, change vs prior, cost per lead when spend matches.
5. **section-header 03 Next steps** + **recommendations**: negatives for zero-lead spenders, pass the keyword in utm_term, push the growing term, grow non-brand search, answer urgent searchers first, check brand tagging.
6. **notes**: the exact intent rules, brand words used, competitor list, spend status.
7. **closing**: next step with the number behind it.

Fewer than 10 keyword leads: a short version with the terms and their intent. No utm_term at all: a short version explaining the `utm_term={keyword}` tracking template.

## Voice guidance

PPC-manager ready: match types, bids, negatives, tracking templates. Keep it actionable inside Google Ads and Microsoft Ads. Quote search terms exactly as they arrived. Never claim a term converts better without spend data to back it.
