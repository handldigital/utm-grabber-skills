# UTM Template Generator

Generates correctly-formed UTM URLs for new campaigns using the customer's ACTUAL existing naming conventions — pulled from their live UTM Grabber data. Eliminates the root cause of the hygiene problem: inconsistent tagging.

This is a utility, not a report. No slides. No PDF. The output is a small block of copy-paste-ready URLs + a short convention summary.

## When to use this utility

- User asks: "generate a UTM", "create UTM links", "help me tag", "UTM for [context]", "tag my campaign", "what UTMs should I use for X".
- Also proactively offered from the UTM Hygiene Audit when the customer clearly doesn't have a tagging standard: "Want me to help standardize your UTM tagging?"

## Input

The user describes the campaign in natural language:

> "I'm launching a new LinkedIn campaign for the spring demo push, with three creative variants."

Extract:
- **Platform / source** — linkedin
- **Medium** — paid_social (inferred from LinkedIn being a paid social platform)
- **Campaign name** — spring_demo_push (slugified)
- **Variants** — three (need to generate three utm_content values)
- **Landing page** — ask if not provided

## Step 1: Infer conventions from existing data

Pull recent entries (last 90 days) and analyze existing UTM patterns:

```
For each utm_field:
  - Collect all non-empty values
  - Detect casing: lower / Title / MIXED
  - Detect separator: underscore / hyphen / space
  - Identify existing values for this source/medium/platform
```

For the demo data example, the analysis would yield:
- utm_source: lowercase (google, facebook, linkedin)
- utm_medium: lowercase with underscore (cpc, paid_social, social, email)
- utm_campaign: lowercase with underscore (spring_demo_search, q1_reactivation_search)
- utm_content: lowercase with underscore (demo_cta_variant_a, demo_cta_variant_b)

Store these as the "house style" for this customer.

## Step 2: Build the URL(s)

Starting from the landing page URL, append UTM parameters in the customer's style:

```
https://{domain}/{path}?
  utm_source={source}&
  utm_medium={medium}&
  utm_campaign={campaign}&
  utm_content={variant}&
  utm_term={keyword_if_search}
```

For multi-variant campaigns, generate one URL per variant.

## Step 3: Output

Return a short message with:

1. **The URLs** — one per line, in a code block for easy copy/paste.
2. **The convention note** — 2–3 sentences explaining what style was inferred.
3. **Optional** — offer to validate by adding the URL to a UTM Grabber tracked list.

### Example output

**User:** I'm launching a new LinkedIn campaign for the spring demo push, with three creative variants. Landing page is utmgrabber.com/spring-demo.

**Response:**

Based on your existing UTM style (lowercase, underscore-separated), here are three tagged URLs for the campaign:

```
https://utmgrabber.com/spring-demo?utm_source=linkedin&utm_medium=paid_social&utm_campaign=spring_demo_push&utm_content=variant_a

https://utmgrabber.com/spring-demo?utm_source=linkedin&utm_medium=paid_social&utm_campaign=spring_demo_push&utm_content=variant_b

https://utmgrabber.com/spring-demo?utm_source=linkedin&utm_medium=paid_social&utm_campaign=spring_demo_push&utm_content=variant_c
```

Convention used: lowercase, underscores between words, medium `paid_social` matching your other paid-social campaigns.

Want me to suggest utm_content names that describe the creative (e.g., `hero_product_shot`, `testimonial_quote`, `demo_cta`) instead of generic variant_a/b/c?

## Principles

### 1. Never invent a style

If the customer has 90 days of data with a consistent style, use it. If they're starting fresh (no prior data), use the industry default: lowercase, underscores, short descriptive names.

### 2. Warn about inconsistency

If the customer's existing data shows 3 different utm_medium values for LinkedIn (`paid_social`, `paidsocial`, `social-paid`), tell them:

> Heads up — your existing LinkedIn tagging shows three different medium values: `paid_social`, `paidsocial`, and `social-paid`. I'll use `paid_social` for these new URLs since it's the most common in your data. You may want to standardize the others to match.

### 3. Offer QR / shortened link generation as follow-up

> Want me to generate a QR code for these URLs (for print ads) or a shortened version via Bitly/your WP redirect?

This is a natural follow-up, but don't do it automatically — let the user request it.

### 4. Handle search (utm_term) specially

For paid search platforms (Google Ads, Microsoft Ads), utm_term is typically auto-populated by ValueTrack parameters (`{keyword}`) rather than hardcoded. Suggest the ValueTrack approach for search:

```
https://utmgrabber.com/demo?utm_source=google&utm_medium=cpc&utm_campaign=spring_demo_search&utm_term={keyword}&utm_content={creative}
```

Explain that `{keyword}` and `{creative}` are Google Ads ValueTrack placeholders that expand automatically.

## Validation

Before returning URLs, validate:

- No spaces in any UTM value (replace with underscore).
- No special characters that need URL encoding (sanitize to ASCII alphanumeric + underscore/hyphen).
- URLs include `https://` — never `http://`.
- Landing page URL is a valid URL format.

If the user didn't provide a landing page, ask:

> What's the landing page URL? (e.g., utmgrabber.com/spring-demo)

## Why this utility matters

The UTM Hygiene Audit diagnoses the problem. This utility prevents the problem from recurring. Together they form a loop: audit finds the mess, generator prevents future mess. Customers who adopt the generator stop producing messy data — which makes every other report in this skill more accurate.

Think of this utility as the skill's product-market-fit multiplier.
