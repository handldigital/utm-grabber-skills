# Data Dictionary

Reference for every field the UTM Grabber MCP returns. Load this file if a field name is unfamiliar, if you're unsure how to aggregate a value, or if you need to classify traffic sources.

## ⚠️ Raw entries are keyed by numeric field id — normalize first

As of plugin v3.1.20 the paginated `get_entries` keys each entry by **numeric form-field id**, not by the human names below: `{ "3": "Google", "4": "cpc", "form_id": "1", "date_created": "2026-04-16 13:03:36" }`. A separate `field_labels` map in the response translates ids → names per form (`field_labels["1"]["3"] == "utm_source (HandL)"`).

**Always load entries through `helpers.load_entries([page files])`.** It applies `field_labels`, so by the time you aggregate, every entry uses the named keys documented in this file (`utm_source (HandL)`, `Date Created`, `Form ID`, `Source URL`, …). The names below describe the *normalized* shape. See `references/mcp-usage.md` for the pagination + normalization contract.

## Entry-level fields

Every form submission ("entry") returned by `get_entries` contains a mix of form-specific fields (what the user typed into the form) and UTM-Grabber-captured fields (attribution data captured by the plugin).

### Core identifiers

| Field | Meaning |
|---|---|
| `Entry ID` | Unique numeric ID of this submission. Use for deduplication. |
| `Form ID` | Which form this submission belongs to. |
| `Date Created` | ISO datetime of submission. Use this for all time-series analysis. |
| `IP Address` | Source IP — **do not display this in reports** (privacy). |
| `Source URL` | The page the form was submitted from. Critical for the UTM hygiene audit. |
| `User Agent` | Browser/OS string — only relevant for device-breakdown reports. |

### UTM Grabber "last touch" fields (HandL prefix)

Captured at the moment the form was submitted. These answer "what channel closed this lead?".

| Field | Meaning |
|---|---|
| `utm_source (HandL)` | Source of last-touch traffic (e.g., "google", "facebook"). Empty = untagged. |
| `utm_medium (HandL)` | Medium of last-touch traffic (e.g., "cpc", "paid_social", "email"). |
| `utm_campaign (HandL)` | Campaign name of last touch. |
| `utm_content (HandL)` | Ad creative / variant identifier. |
| `utm_term (HandL)` | Keyword term (mostly paid search). |
| `gclid (HandL)` | Google Ads click ID — presence alone confirms paid Google. |
| `fbclid (HandL)` | Facebook click ID — presence alone confirms Facebook traffic. |
| `msclkid (HandL)` | Microsoft Ads click ID — confirms paid Bing. |
| `traffic_source (HandL)` | UTM Grabber's classification: "Paid", "Organic", "Social", "Referral", "Direct". Use this for channel-mix charts. |

### UTM Grabber "first touch" fields (HandL first-touch prefix)

Captured the very first time this user visited the site, before they filled out any form. Preserved across sessions via first-party cookie.

| Field | Meaning |
|---|---|
| `utm_source (first touch, HandL)` | First-touch source. |
| `utm_medium (first touch, HandL)` | First-touch medium. |
| `utm_campaign (first touch, HandL)` | First-touch campaign. |
| `traffic_source (first touch, HandL)` | First-touch classification. |
| `landing_page (first touch, HandL)` | The first page this visitor ever landed on. |
| `referrer (first touch, HandL)` | The HTTP referrer of the first visit. |

**Key insight to use in reports:** Compare `traffic_source (HandL)` vs `traffic_source (first touch, HandL)` to build the "first touch vs last touch" story. This is one of the most valuable insights UTM Grabber captures — almost no competitor does this.

### Form-specific fields

These vary by form. Any field the customer added to their form will appear in the entry. Common examples from the demo `Attribution Demo Request` form:

| Field | Typical values |
|---|---|
| `First Name` / `Last Name` | User identity |
| `Work Email` | Contact email |
| `Company Name` | Account name |
| `Monthly Ad Spend` | Budget bracket (`Under $5,000`, `$5,000 to $20,000`, `$20,000 to $100,000`, `Over $100,000`) |
| `Primary Goal` | Why they're inquiring |
| `CRM Platform` | What CRM they use |
| `Desired Timeframe` | Urgency signal |

**Handle form fields generically.** Don't hardcode specific field names — inspect what the form returned and adapt. The exception: if the user explicitly asks about ad spend or CRM, look for those field labels specifically.

## Traffic source classification rules

When `traffic_source (HandL)` is populated, use it directly. When it's missing (because no UTM was captured), apply this fallback logic:

1. If `gclid` or `msclkid` is present → **Paid**
2. If `fbclid` is present AND `utm_medium` contains "paid" → **Paid**; else → **Social**
3. If `utm_medium` matches `cpc`, `ppc`, `paid`, `paid_search`, `paid_social` → **Paid**
4. If `utm_medium` matches `social` → **Social**
5. If `utm_medium` matches `email`, `newsletter` → **Email** (group under Referral for top-level charts)
6. If `utm_medium` matches `referral` → **Referral**
7. If `utm_source` is present but no `utm_medium` and source is a known search engine (`google`, `bing`, `duckduckgo`, `yahoo`) → **Organic**
8. If no UTMs but `referrer` is present → classify from referrer domain
9. If no UTMs and no referrer → **Direct**

For reports, collapse "Email" into either Referral or Direct depending on audience preference. The monthly review keeps them separate; the weekly summary merges them.

## UTM hygiene scoring

For the hygiene audit report, categorize each entry:

| Status | Definition |
|---|---|
| **Fully tagged** | `utm_source` AND `utm_medium` AND `utm_campaign` all populated. |
| **Partially tagged** | Any UTM populated but at least one of source/medium/campaign missing. |
| **Untagged (paid indicator)** | No UTMs but `gclid` / `fbclid` / `msclkid` present — ad click happened but tagging failed. |
| **Untagged (referrer)** | No UTMs, no click IDs, but referrer is present — organic/referral traffic that should have been tagged via a landing-page redirect. |
| **Direct / unattributable** | No UTMs, no click IDs, no referrer. Genuinely direct traffic (or a lost attribution). |

The "Untagged (paid indicator)" group is the highest-value fix — it means the customer paid for the click and lost the attribution. Surface these entries by count AND by source URL so they can fix the broken tagging.

## Common pitfalls

- **Empty strings vs null.** The MCP sometimes returns `""` for unpopulated fields and sometimes `null`. Treat both as missing.
- **Case sensitivity.** `Google` and `google` are the same source. Lowercase everything before grouping.
- **Whitespace.** UTM values sometimes arrive with trailing spaces. Strip before grouping.
- **Duplicate entries.** The same `Entry ID` should never appear twice, but if it does, keep the most recent `Date Updated`.
- **Bot-looking entries.** Submissions with identical timestamps, nonsense names, and no UTM/referrer data are often spam. If more than 10% of entries look like spam (empty company, test@test.com patterns, identical addresses), flag this in the report rather than silently including them.
