# Changelog

All notable changes to the UTM Grabber Attribution Reports skill.

## 1.0.0 — Apr 20, 2026

**First stable release.** Brand-pure defaults, Q&A-first caching, and parallel MCP pulls cut typical report time by 1–3 seconds and take most Q&A follow-ups to zero MCP calls.

**Branding cleanup**
- Replaced the stock accent color across the skill: `#FF5A5F` (generic coral, origin unclear) → `#2E90FA` (UTM Grabber bright blue). Creates a cohesive two-tone blue palette with the existing `#0160BF` primary. Chart palette slot 6 swapped coral → `#F59E0B` amber so multi-category charts still have a warm punctuation color without duplicating blues. Updated in [report_recipes.py](scripts/report_recipes.py), [demo_report.py](scripts/demo_report.py), [build_pdf.py](scripts/build_pdf.py), both chart renderers, [report-shell.html](templates/report-shell.html), and [sample-monthly-review.html](examples/sample-monthly-review.html).
- Removed the CloseUp brand profile from [references/branding-profile.md](references/branding-profile.md) — the gradient-theme illustration now uses a fictional "Acme Analytics" with the UTM Grabber palette so no real customer brand acts as pattern-bait.
- Prose cleanup: every "coral" reference that described the accent role replaced with "accent" / "bright blue" across [design-system.md](references/design-system.md), [design-contract.md](references/design-contract.md), [period-comparisons.md](references/period-comparisons.md), [branding-profile.md](references/branding-profile.md), and [brand-onboarding.md](utilities/brand-onboarding.md).

**Speed optimizations**
- **Parallel MCP pulls for delta reports.** [rendering-pipeline.md](references/rendering-pipeline.md) and [SKILL.md](SKILL.md) now instruct Claude to issue current + prior `get_entries` **in the same tool-use response**, not sequentially. Saves ~1–3s per monthly/weekly/forecast report (≈40% of report traffic). Full-flow worst case: 7 → 6 tool calls.
- **Subset-of-cached-range filtering for Q&A.** New `load_cached_superset()` in [helpers.py](scripts/helpers.py) finds any cached pull whose date range encloses the requested window and filters by date in Python — zero MCP calls on narrow Q&A follow-ups. A cache index file (`CACHE_DIR/_index.json`) tracks range metadata; `save_cached_entries` updates it automatically. `conversational-qa.md` updated to use this as the primary cache path. This is the single biggest speed win for the Q&A flow — which per conversational-qa.md gets used "20× more than any report."
- **Cache TTL bumped 1h → 4h** via a new `CACHE_TTL_SECONDS` constant in helpers.py. UTM data isn't live-critical; longer TTL meaningfully reduces repeat MCP calls across a multi-hour session.
- **`validate=False` default in `build_pdf_from_summary`** — recipes are schema-valid by construction, so the redundant validation pass is off by default. Pass `validate=True` explicitly when building a summary by hand.
- **Demo data disk-cached** in `$TMPDIR/utm-grabber-demo-cache/`. Cycling through multiple demo reports in one session regenerates the ~490-entry synthetic dataset once, then reuses it.

**Rule + doc correctness**
- **Fixed stale PDF/PPTX ban** in [rendering-pipeline.md](references/rendering-pipeline.md:85). The doc still said *"PDF is disabled in this version"* and *"PPTX export is similarly deferred"* — leftover from v0.7. Rewritten to reflect current reality: HTML default, PDF via WeasyPrint, PPTX via python-pptx, all supported. Prevented a class of silent failures where Claude would refuse format requests that actually work.
- **Trimmed the 12-file "File-reading order per request"** in SKILL.md from a flat list implying most refs load on every request, to a 2-item "always load" tier plus a conditional trigger table. Every reference now has an explicit "load only when" condition. Reduces precautionary context loading.
- **Deleted `scripts/build-monthly-report.py`** — legacy v0.8-era reference implementation long superseded by `scripts/demo_report.py`.

**Regression**
- 108/108 builds pass (18 recipes × 2 themes × 3 formats).

## 0.9.12 — Apr 21, 2026

**Three hygiene fixes from the self-audit: dynamic version, regenerated sample, per-recipe kicker polish.**

**Fix 1: `skill_version` now reads dynamically from VERSION.md**
`scripts/report_recipes.py` had a hardcoded `skill_version="0.9.2"` as the `_meta()` default — so every report's footer was claiming v0.9.2 even though the skill was at 0.9.11. Introduced `_read_skill_version()` that reads VERSION.md at module load time; `_meta()` now falls back to that value. No hardcoded version strings remain in recipe output paths.

**Fix 2: `examples/sample-monthly-review.html` regenerated**
The file header was getting version-bumped on every release (v0.9.2 → v0.9.11) but the actual report content was frozen from an earlier build — no summary_stats, no data-driven closing title, stale stat calculations. Regenerated against `build_monthly_summary(current, prior, Sample Co brand)` on the bundled test dataset so the sample now faithfully represents current output (summary-card closing, italic-accent title, two-tone cards, etc.). Prepended a header comment noting it's a regenerated artifact — regenerate after template or recipe changes.

**Fix 3: Per-recipe closing kickers**
All 18 recipes had the same generic `"kicker": "At a glance"` above their closing titles. Replaced with recipe-specific labels so the reader can tell at a glance which report they're looking at the final page of:

| Recipe | Kicker |
|---|---|
| monthly | The month |
| weekly | The week |
| audit | The fix |
| leaderboard | The standings |
| forecast | The forecast |
| anomaly | The moves |
| lead-scorer | The pipeline |
| landing-page | The pages |
| form-performance | The forms |
| ad-creative | The creatives |
| keyword | The terms |
| source-to-crm | The mapping |
| campaign-deep-dive | The campaign |
| lead-profile | The lead |
| side-by-side | The verdict |
| paid-vs-organic | The split |
| budget-simulator | The scenario |
| agency-rollup | The book |

All 18 unique. Minor visual distinction but improves scannability across a multi-report session where someone's flipping between decks.

**Verified**
- Full regression: 108/108 builds pass across 18 recipes × 2 themes × 3 formats.
- Report footers now show v0.9.12 (dynamic version read).
- Sample HTML contains `summary_stats` and the data-driven closing title "Next: feed *Google* — it drove 29% of leads."

**Still open** (accepted, not blocking)
- A11y: aria-labels on canvas charts
- Brand auto-detection verification against real sites
- Demo mode end-to-end conversation dry-run
- `mcp_retry.py` is documentation-only (SKILL.md references the pattern; no recipe imports the module)

## 0.9.11 — Apr 21, 2026

**Closing titles are now genuinely actionable. Every recipe's sign-off tells the reader what to DO, with numbers from their actual data.**

User feedback on v0.9.10: "That's your month" / "Feed the winners" — these are not very helpful. How can we make this more actionable and useful?

Fair. The v0.9.10 titles were editorial sign-offs — they felt conclusive but said nothing specific. Rewrote all 18 as f-strings that thread the variables each recipe already computes into the title itself:

| Recipe | Before (v0.9.10) | After (v0.9.11) |
|---|---|---|
| monthly | "That's *your* month." | "Next: feed *{top_source}* — it drove {pct}% of leads." |
| weekly | "That's *your* week." | "Monday: review *{top_campaign}* — it drove volume." |
| audit | "Fix these and you *recover* attribution." | "Fix the top 3 pages — recover *{n}* leads/month." |
| leaderboard | "Feed the *winners*." | "Cut the *{cold_count} cold*. Double the top 3." |
| forecast | "Plan for the *likely* path." | "Plan for *{forecast_30d}* leads — budget at the low end ({range_low})." |
| anomaly | "Investigate *before* you react." | "Investigate *{top_mover}* — {pct:+}% vs baseline." |
| lead-scorer | "Work the *top* tier first." | "Call the top *{n}* leads this week — from {top_source}." |
| landing-page | "Replicate the *top* three." | "Replicate *{top_page}* — it's doing {n} leads." |
| form-performance | "Keep what *works*." | "Form {top} does *{pct}%* — audit the other {n}." |
| ad-creative | "Fewer, *better* ads." | "Pause the *{n}* low-volume creatives this week." |
| keyword | "Bid on *intent*, not volume." | "Bid up *'{top_keyword}'* by 10-15% for 7 days." |
| source-to-crm | "Speak each channel's *CRM* language." | "Build a *{top_crm}-specific* landing page for {top_source}." |
| campaign-deep-dive | "One campaign, *fully* seen." | "Replicate *{winning_creative}* on sister campaigns." |
| lead-profile | "Ready for *your* outreach." | "Call *{company}* — {n} touchpoint(s), qualified." |
| side-by-side | "The *better* bet, clearly." | "Shift budget toward *{winner}* — it won volume." |
| paid-vs-organic | "Invest where the *curve* bends." | "Shift 5-10% of budget toward *{dominant}* this quarter." |
| budget-simulator | "Model it, then *test* it." | "Start with a *5%* shift — measure for 14 days before scaling." |
| agency-rollup | "Your *book*, top-down." | "Call the *{n}* flagged brand(s) this week." |

**Grammar polish**
- lead-profile pluralizes: "1 touchpoint" (singular) vs "3 touchpoints" (plural)
- form-performance handles the single-form edge case: "Form 3 does *100%* — add a second form as backup" instead of "audit the other 0"

**Validated**
- All 18 recipes produce schema-valid summaries with exactly one italic accent in the closing title
- Full regression: 18 unique recipes × 2 themes × 3 formats = **108/108 builds pass**
- Gradient PPTX closing slide renders cleanly at 40pt — the longer action titles still fit without wrapping awkwardly (worst case wraps to 2 lines at widescreen aspect)
- Verified against CloseUp pink brand and UTM Grabber blue

**SKILL.md note**
The "Critical rules at a glance" section on closing schema now documents this as the standard: closing titles should be data-driven f-strings using variables from the recipe's aggregation, not generic editorial sign-offs. Future recipes should follow the same pattern.

## 0.9.10 — Apr 20, 2026

**Closing titles rewritten as editorial sign-offs + gradient theme restricted to PPTX only.**

**Closing titles: every report now signs off properly**
User: '"The headline numbers" — what's that mean? That needs to be improved.'

Fair. Every closing title was reading like a placeholder label for the stats above it. Rewrote all 18 with editorial voice — a mix of sign-offs ("That's *your* month.") and action-oriented takeaways ("Work the *top* tier first."):

| Report | Was | Now |
|---|---|---|
| monthly | "The *headline* numbers." | "That's *your* month." |
| weekly | "Your *week*." | "That's *your* week." |
| hygiene audit | "Your *hygiene*." | "Fix these and you *recover* attribution." |
| leaderboard | "The *leaderboard*." | "Feed the *winners*." |
| forecast | "Your *next 30 days*." | "Plan for the *likely* path." |
| anomaly | "What *moved*." | "Investigate *before* you react." |
| lead-scorer | "Your *pipeline*." | "Work the *top* tier first." |
| landing-page | "Your *pages*." | "Replicate the *top* three." |
| form-performance | "Your *forms*." | "Keep what *works*." |
| ad-creative | "Your *creatives*." | "Fewer, *better* ads." |
| keyword | "Your *keywords*." | "Bid on *intent*, not volume." |
| source-to-crm | "Your *CRM map*." | "Speak each channel's *CRM* language." |
| campaign-deep-dive | "The *campaign*." | "One campaign, *fully* seen." |
| lead-profile | "Their *profile*." | "Ready for *your* outreach." |
| side-by-side | "The *verdict*." | "The *better* bet, clearly." |
| paid-vs-organic | "The *split*." | "Invest where the *curve* bends." |
| budget-simulator | "The *scenario*." | "Model it, then *test* it." |
| agency-rollup | "The *portfolio*." | "Your *book*, top-down." |

All 18 still have exactly one italic accent, still validate cleanly, still fit in the closing card's title zone at 40pt.

**Gradient theme: PPTX only**
User: "The gradient should only be for the PPTX. The HTML and PDF should be the default white."

Done. Gradient theme is now a PPTX-exclusive feature:
- **HTML**: gradient CSS block removed (~90 lines). JS no longer applies `body.theme-gradient` class or computes `--b-grad-end`. HTML ignores `brand.theme` and always renders in the editorial light style.
- **PDF**: already light-only since v0.9.8, unchanged.
- **PPTX**: `brand.theme: "gradient"` still produces the dark diagonal gradient with white text and brand-color accents.

Rationale: gradient backgrounds look dramatic on a projector screen but are hard to read on small screens (mobile HTML) and completely wrong for print (PDF). PPTX is the one format where the gradient adds presentation polish without hurting readability.

Updated docs:
- `SKILL.md` Rule 3: "HTML and PDF are light-only. PPTX supports both themes."
- `SKILL.md` "Critical rules at a glance": gradient is PPTX-only.
- `references/branding-profile.md`: theme section notes PPTX-only as of v0.9.10.

Added response guidance: if a user asks for "dark HTML" or "dark PDF", Claude should say "Gradient theme is a PPTX-only feature — want me to do the PPTX in gradient?"

**Verified**
- Full regression: 18 recipes × 2 themes × 3 formats = 108/108 builds pass.
- HTML with `theme: "gradient"` in brand profile correctly renders light (verified via Playwright screenshot at 1280px viewport).
- PPTX with `theme: "gradient"` still renders gradient correctly.
- PPTX closing slide now shows "That's *your* month." above the summary stats — reads like a proper sign-off, not a label.

## 0.9.9 — Apr 20, 2026

**One-shot demo report builder + full regression harness. 108/108 builds pass across every recipe × theme × format.**

**New: `scripts/demo_report.py` — one-shot sample report generator**
Claude can now run a single command to produce a complete sample report against synthetic demo data:

```
python scripts/demo_report.py --out <path> --report <type> --theme <light|gradient>
```

- Auto-detects output format from the file extension (.html / .pptx / .pdf)
- Routes correctly through every recipe's signature — monthly/weekly (current+prior), forecast (history window), anomaly (current+baseline), campaign-deep-dive (auto-picks top campaign), lead-profile (picks a sample email), side-by-side (splits demo data in half), budget-simulator (stock scenario: shift 20% from Google to LinkedIn), agency-rollup (splits demo into 4 synthetic client brands)
- Stock "Sample Co" brand with UTM Grabber blue by default; `--brand-json path/to/brand.json` accepts a real profile
- `--theme gradient` applies to HTML and PPTX only (PDF stays light per v0.9.8)

Claude uses this in the welcome flow's "See a sample report (no setup needed)" path: one bash call, full-quality output, no MCP required.

**Regression coverage: 18 × 2 × 3 = 108 builds**
New sweep tests every unique recipe function against both themes and all three output formats. Current status: **108/108 pass.** Caught and fixed two dispatch bugs in `demo_report.py` where aliases (`/budget`, `/compare`) didn't resolve to the same special-case handling as their canonical names, and where `build_forecast_summary` (single-history signature) was being called with `(current, prior)`.

**Still open**
- A11y: aria-labels on canvas chart elements for screen readers (skipped — charts are illustrative and have text alternatives via the insight cards next to them)
- Per-recipe summary-card kicker customization (most still use default "At a glance" — minor copy polish)
- Brand profile auto-detection validation against 5 real sites (claim from v0.8.0, never independently verified)

## 0.9.8 — Apr 20, 2026

**PDF gradient reverted (user feedback). SKILL.md consolidated, demo mode added, MCP retry helper, mobile/a11y pass.**

**PDF: gradient reverted, light-only**
User: "the gradient PDF looks terrible. I think we should only have the gradient for the PPTX."

PDF now renders in clean editorial light mode regardless of `brand.theme`. The `body_class` force-empty in `build_pdf.py`, and the gradient CSS block was stripped from `pdf_styles.css`. HTML still supports gradient (works fine in a browser). PPTX still supports gradient. PDF stays editorial — better for print anyway.

A new SKILL.md rule codifies this: "If the user asks for 'dark PDF', respond: 'PDF stays light for print readability — want me to do the PPTX in gradient instead?'"

**SKILL.md consolidation**
Pulled the most-referenced rules from `references/` directly into the top of SKILL.md so Claude doesn't need to read 5-7 reference files at pipeline start. New "Critical rules at a glance" section covers:
- Voice (banned words, ≤3 sentences before report)
- Speed (memory + cache order, tool budget 2/3-4/7)
- MCP retry pattern (1500 → 750 → ask the user)
- Closing schema (summary_stats + bullets)
- Italic accent rule (exactly one per title)
- Two-tone card house style
- Theme rules (PPTX+HTML support gradient; PDF is light-only)
- Brand persistence pattern

Also fixed stale Rule 3 that still said "NEVER generate PDF" — that was true two versions ago, but PDFs have been supported since v0.8.0. Rewrote it as "Output formats & theme handling".

**Demo mode**
New `scripts/demo_data.py` produces ~370 synthetic realistic entries per 30-day window. Welcome flow's "Just exploring" path now offers "See a sample report (no setup needed)" as the first option. Claude imports `get_demo_current()` / `get_demo_prior()`, runs the monthly recipe, and delivers a full-quality report without needing the user to connect MCP.

After the demo report renders, Claude offers two next-steps: "Connect my site to run this on real data" or "Show me a different report type." Single-shot, fast, no MCP needed.

**MCP retry helper**
New `scripts/mcp_retry.py` with `PRIMARY_LIMIT=1500`, `RETRY_LIMIT=750`, `is_suspicious_empty()`, `is_truncated()`, and friendly user-facing prompt strings. Documents the retry pattern Claude should follow: try 1500 → retry 750 → ask user. No silent infinite retries. Referenced from SKILL.md's "Critical rules at a glance" section.

**Mobile + a11y pass on HTML template**
- Viewports ≤720px: stat strip collapses to 2-column (then 1-column ≤420px), recommendations grid single-column, chart-insight stacks, hero number scales, ranked list allows horizontal scroll rather than squishing
- Title scales from 76px → 40px on mobile
- Verified at 375px viewport — CloseUp report renders cleanly, stats stack, title wraps, readable at iPhone width
- A11y additions: `:focus-visible` outline in brand primary, 44x44 minimum tap targets on interactive elements, `prefers-reduced-motion` disables animations
- `@media print` forces light mode even on gradient-themed HTML — so if someone prints a gradient HTML report, it comes out readable in b&w

**Still open**
- Propagate demo_data integration into `welcome.md` routing logic (the doc change is in, but exact handling code lives in Claude's conversation flow)
- A11y deep audit (aria-labels on canvas charts for screen readers, alt text on logos)
- More recipes adopting summary-card `kicker` customization (most use default "At a glance" — could be more specific)

## 0.9.7 — Apr 20, 2026

**Gradient theme now ships across the entire output suite (PPTX + HTML + PDF) and every report recipe adopts the summary-card closing.**

**Closing propagation — 18/18 recipes**
Every recipe now emits `summary_stats` + `bullets` on the closing section, with metrics tuned to the report's subject:
- monthly: total leads · UTM coverage · per day · top source + channel mix / peak day / top source share
- weekly: weekly leads · per day · paid share · top campaign + direction vs last week / top campaign / monthly-review CTA
- audit: UTM coverage · leaks · pages to fix · paid platforms leaking + fully-tagged count / top leak cost / re-audit cadence
- leaderboard: active campaigns · top campaign leads · top 3 share · cold campaigns + winner / top-3 volume / weekly cadence
- forecast: projected · low / high / confidence range + basis / seasonality / budget scenario hint
- anomaly: anomalies count · biggest drop · biggest spike · top mover + headline anomaly / investigation reminder / daily cadence
- lead-scorer: scored · top tier · avg score · top-tier source + priority count / top source / CRM hand-off
- landing-page / form-performance / ad-creative / keyword / source-to-crm: ranked subject stats
- campaign-deep-dive / lead-profile / side-by-side / paid-vs-organic / budget-simulator / agency-rollup: subject-specific verdict stats

Each closing fits the compact summary-card layout (4 stats + 3 bullets) and renders cleanly in both light and gradient themes.

**Gradient theme in HTML**
The HTML template now supports `brand.theme: "gradient"`:
- Init JS applies `body.theme-gradient` class and computes `--b-grad-end` (ink mixed with 35% primary)
- ~80 lines of CSS targeting the actual card class names (stat-card, hero-number, chart-block.with-insight, standalone-insight, rec-card, ranked-list, closing-panel)
- Dark-aware trend pills with background tints (rising green, cooling red, steady/cold gray)
- Stat delta colors adapt: brighter greens/reds on dark so they pop
- Charts stay on white (readability — same decision as PPTX)
- `× UTM Grabber` header tag removed to match PPTX

**Gradient theme in PDF**
`build_pdf.py` + `pdf_styles.css` both updated:
- `build_pdf.py` computes gradient end color and exposes as CSS variable
- `<body class="theme-gradient">` applied when theme matches
- Appended the same gradient CSS block to `pdf_styles.css` (WeasyPrint-compatible selectors)
- Removed `× UTM Grabber` tag from PDF header
- Fixed "flat" delta label — now shows just `—` in HTML and PDF to match PPTX

**Also fixed**
- Monthly recipe sources chart-insight: `insight_kicker` was still "Concentration" — now "The winner" (matches the terminology fix from v0.9.6)

**Still open**
- SKILL.md consolidation (file-read count reduction)
- Demo mode in welcome flow
- Mobile layout audit
- A11y pass
- MCP retry logic

## 0.9.6 — Apr 20, 2026

**Typography and copy polish across both themes.** Six targeted fixes from user review.

**Fixes**
- **Contrast**: gradient mode text_body went from `#E6E8EE` → `#F0F2F5` and text_muted went from `#9AA3B8` → `#C8CDD7`. Almost-white, not gray. Body copy on insight cards now reads comfortably against the dark panel without feeling washed out.
- **Kicker size**: "MONTHLY PERFORMANCE REVIEW · LAST 30 DAYS" and every other title-slide kicker bumped 13pt → 17pt. It now anchors the hierarchy instead of getting lost above the big title.
- **Removed "× UTM Grabber" tag** from the header. Header now shows just the customer's company name (e.g. "CloseUp") with the brand-accent bar underneath. Less clutter, less branding-on-branding.
- **Flat delta**: stat cards with no change now show just `—` (em dash) instead of `— flat`. The word was redundant with the dash.
- **"HEADLINE" → "THE TAKEAWAY"** on the insight card kicker in monthly reports. "Concentration" → "The winner" on the sources insight. Punchier, more editorial voice.
- **Body text size bumps**: insight-card body 16pt → 19pt, chart-insight body 14pt → 17pt. "Google alone contributed 142 leads — 29% of the total" now reads like a real editorial callout instead of a caption.

All six fixes apply to both light and gradient themes — no branch in the code, just single-source updates to the typography/text layer.

**Still open from earlier releases** (unchanged this ship)
- Gradient in HTML/PDF — PPTX-only for now
- Other recipes (beyond monthly) adopting summary-card closing
- SKILL.md consolidation, mobile audit, a11y pass, MCP retry logic, demo mode — none started

## 0.9.5 — Apr 20, 2026

**Two big UX wins from user feedback: the closing slide is now useful, and the deck can render in a dramatic dark gradient theme.**

**Closing slide redesigned as a summary card (not a CTA)**
User: "people will not book a call with UTM Grabber for consulting. it should just be a summary card."

Fixed. The closing slide is now an "AT A GLANCE" recap panel:
- Compact tinted panel sized to leave real clearance for the footer (no more clashing borders)
- Brand-primary kicker with short accent rule
- Smaller title (40pt — this isn't the hero anymore) with italic accent
- Row of 4 summary stat cards showing the key metrics of the report (leads, coverage, per-day rate, top source)
- 3 bullet recap lines with brand-colored dots (mix shares, peak day, top source attribution)
- Monthly recipe now passes all this data through the new `summary_stats` + `bullets` fields on the closing section

Other recipes can be updated to take advantage of the new schema — they'll currently fall back to showing their old title-only closing. Progressive migration, not a breaking change.

**Optional gradient theme — dark mode with brand color pop**
User: "I'm finding this boring looking. a lot of white. i think we should actually have a gradient background with white text and accent colors based on their branding."

Added. New brand-profile field: `theme: "gradient"` (default remains `"light"`).

When gradient:
- Every slide gets a dark diagonal gradient background (ink → ink+35%primary at 45°)
- XML-injected gradient via `lxml` on the slide's `<p:bg>` element — renders correctly in PowerPoint, Keynote, LibreOffice, Google Slides
- All text flips to white/light-gray with brand primary for accents
- Two-tone cards become dark-tinted rectangles (`#1A2340` top, `#0F1830` bottom, `#2A3550` border) — same visual language, inverted palette
- Charts stay on a white canvas (readability > consistency here — charts on dark backgrounds are harder to parse)
- Brand primary + accent colors stay exactly as defined — they naturally pop on dark

Tested with CloseUp's pink (#F70071) — the deck looks genuinely premium. Every slide type renders correctly: title, stat-strip, section-header, chart-insight, recommendations, closing. Light mode continues to work unchanged.

**Added**
- `scripts/build_pptx.py` — `_theme_colors()`, `_is_gradient_theme()`, `_set_gradient_bg()`, `_apply_theme_background()` helpers
- `scripts/build_pptx.py` — `_add_two_tone_card()` signature now accepts `brand=None` for theme-aware card colors
- `references/branding-profile.md` — theme section documenting both options
- Every renderer now calls `_theme_colors(brand)` and uses `tc['text_headline']` / `tc['text_body']` / `tc['text_muted']` throughout

**Also fixed**
- 9 places in the code where `tc = _theme_colors(brand)` was getting collapsed onto the same line as the next statement (newline bug from an earlier regex pass)
- Main builder loop now calls `_apply_theme_background(slide, brand)` at slide creation (was missing — that's why the first gradient preview showed white backgrounds)

**Still open**
- Gradient theme in HTML/PDF — currently PPTX-only. Would need CSS variables and potentially a dark chart palette in `chart_renderer.py`.
- SKILL.md consolidation (not started)
- Mobile layout audit (not started)
- A11y pass (not started)
- Retry logic for MCP calls (not started)
- Demo mode for welcome flow (not started)

## 0.9.4 — Apr 20, 2026

**Full recipe coverage (18/18) + PPTX design cleanup.**

User feedback: v0.9.3 still had decorative watermarks (big "C" and big "02/03") that looked like empty filler, plus 2-line recommendation titles overflowed their cards, plus body text was still small. This release cleans all three, and hits full recipe coverage across the report catalog.

**PPTX design — less decoration, more hierarchy**
- Removed the big pale company-initial watermark from the title slide. The kicker, huge italic title, and brand-color decorative rule do the work on their own. The slide now reads as editorial, not decorated.
- Removed the giant pale section-number watermark ("01", "02") from section-header slides. Replaced with an **integrated, meaningful kicker line**: an italic serif number + mono-caps kicker on one line ("*02* · SOURCES") above the big title. The number adds context without dominating.
- Recommendations card: tint zone grown from 42% → 58% so 2-line titles fit cleanly in the tinted area. Label/title positions retuned. Body text bumped 15pt → 17pt for better readability.

**Recipe coverage: 18/18 (was 8/18)**
Added 10 new recipes to `scripts/report_recipes.py`:
- `build_form_performance_summary(current, brand)` — ranks forms by submission count
- `build_ad_creative_summary(current, brand)` — by utm_content within paid channels
- `build_keyword_summary(current, brand)` — by utm_term within paid search
- `build_source_to_crm_summary(current, brand)` — source × CRM cross-tab with stacked bars
- `build_campaign_deep_dive_summary(current, campaign_name, brand)` — single-campaign profile
- `build_lead_profile_summary(all_entries, email, brand)` — touchpoint history for one lead, emails masked
- `build_side_by_side_summary(a_entries, a_label, b_entries, b_label, brand)` — verdict table
- `build_paid_vs_organic_summary(current, brand)` — classification, trajectory, mix
- `build_budget_simulator_summary(current, scenario, brand)` — linear what-if model
- `build_agency_rollup_summary(brand_data_list, brand)` — portfolio view across brand profiles

**RECIPES dict now has 32 keys covering 18 functions** (common aliases route to the same function — e.g., `/forms`, `/form-performance`, `/form` all map to `build_form_performance_summary`).

Every recipe:
- Handles empty-entries gracefully with a helpful "no data" report
- Passes `validate_summary()` schema validation
- Follows the same output structure (title → stats → optional chart → ranked-list → insight → recommendations → closing)
- Saves Claude from hand-writing 50-100 lines of Python per run

**Still open (honest status)**
- SKILL.md absorbing key rules from `references/*` (reduces initial file-read count). Not started.
- Mobile-responsive HTML audit. Not started.
- A11y pass. Not started.
- HTML build script auto-validation (PDF/PPTX already have it; main HTML pipeline doesn't). Not started.
- Retry logic for flaky MCP calls. Not started.
- Demo mode for welcome flow. Not started.

## 0.9.3 — Apr 20, 2026

**PPTX font sizes bumped for presentation reading + brand profile persistence + 2 more recipes.**

**PPTX readability**
User feedback: v0.9.2 fonts were too small to read from the back of a conference room. This release systematically bumps every text size in PPTX output:
- Stat values: 60pt → 72pt (tested at 96pt first — too big, wrapped numbers)
- Hero number: 140pt → 160pt
- Section header kickers: 13pt → 15pt
- Insight card titles: 22pt → 26pt (chart-insight), 32pt (standalone)
- Recommendations titles: 20pt → 22pt
- Body text in insight cards: 12pt → 14pt
- Recommendations body: 12pt → 15pt
- Ranked list cells: 10-11pt → 12-13pt
- Footer: 8pt → 10pt
- Stat labels: 10pt → 13pt
- Card heights grown to 3.8" (stat strip) and 3.0" (recommendations) to accommodate larger titles without pushing content into the footer.
- 31 individual font-size bumps total, plus geometry adjustments for card fit.

**Brand profile persistence (new)**
New `scripts/brand_persistence.py` module. Brand profiles — company name, colors, customer_domain, form_plugin, form_ids — now persist across conversations via `memory_user_edits`:
- `serialize_brand_profile(profile)` → compact JSON string (<500 chars)
- `deserialize_brand_profile(memory_line)` → parses back into a dict
- `find_profile_in_memories(memory_lines, customer_domain=...)` → scan helper
Claude's workflow: on first `/brand` setup or first successful discovery, serialize + `memory_user_edits(command='add', ...)`. On subsequent conversations, `memory_user_edits(command='view')` + `find_profile_in_memories()` → skip discovery entirely. Real speed win: 10-20 seconds saved per new conversation.

**New recipes**
- `build_lead_scorer_summary(current, brand)` — scores every lead 0-100 based on declared monthly ad spend, CRM, timeframe urgency, source quality, and company context. Returns top 10 ranked table with masked emails for privacy. Sales-team-ready output.
- `build_landing_page_summary(current, brand)` — ranks pages by lead count with top source attribution per page. Answers "which pages convert from which sources?"
- Added to `RECIPES` router dict under multiple aliases (`lead-scorer`, `lead-quality`, `score-leads`, `landing-page`, `landing-pages`).

**Inventory: 8 of 18 reports now have pre-built recipes**
- ✓ monthly, weekly, hygiene audit, campaign leaderboard, forecast, anomaly, lead-quality-scorer, landing-page-performance
- ✗ Still need: form-performance, ad-creative, keyword, source-to-CRM, campaign-deep-dive, lead-profile, side-by-side, paid-vs-organic, budget-simulator, agency-rollup

**Still open from prior versions**
- SKILL.md absorbing key rules from `references/*` to reduce file-read count (not started)
- Mobile-responsive HTML audit (not started)
- A11y pass (not started)
- Retry logic for flaky MCP calls (not started)
- Demo mode for welcome flow (not started)

## 0.9.2 — Apr 20, 2026

**PPTX brand enforcement + speed wins via pre-built recipes.**

After user testing v0.9.0 against CloseUp (pink brand), found PPTX slides looked bare — brand color only appeared in italic accents and stat labels, not in the slide chrome. This release adds proper brand expression throughout PPTX and introduces report recipes that eliminate the need for Claude to hand-write summary dicts per report.

**PPTX branding (visible on every slide)**
- Header: small brand-primary accent bar next to company name, plus a faint hairline rule stretching across the slide. Same accent repeats on the footer.
- Title slide: big pale brand-color **company initial** as a typographic watermark in the top-right corner (pale pink "C" for CloseUp, pale blue "U" for UTM Grabber). Plus a short brand-color decorative rule under the title.
- Section-header slides: giant pale brand-color section numeral ("01", "02", "03") filling the right side of the slide. Brand-primary kicker and short accent rule on the left.
- Closing slide: brand-tinted background panel wrapping the farewell, with a short brand-color horizontal rule above the centered title.
- Stat cards: enlarged from 2.5" → 3.4" tall, numbers from 60pt → 80pt. Cards now fill the 16:9 canvas properly instead of floating in empty space.
- New `_pale_rgb()` helper computes a white-mixed version of the brand primary for watermark elements (default 92% white mix = subtle tint).

**Report recipes — the speed win**
- New `scripts/report_recipes.py` module. Pre-built summary builders for the six most-run reports:
  - `build_monthly_summary(current, prior, brand)` → 12 sections, period-over-period deltas
  - `build_weekly_summary(current, prior, brand)` → 7 sections, brisk Monday-morning format
  - `build_hygiene_audit(current, brand)` → 9 sections, automated leak classification (gclid/fbclid/msclkid + referrer)
  - `build_campaign_leaderboard(current, brand)` → 7 sections, heuristic trend states
  - `build_forecast_summary(history, brand)` → 6 sections, baseline projection with ±12% confidence range
  - `build_anomaly_summary(current, baseline, brand)` → 6 sections, per-source deviation detection
- Every recipe handles **empty-entries gracefully** — returns a valid "no data yet" summary with helpful "check your tracking" messaging instead of crashing.
- Every recipe is **schema-valid by construction** — passes `validate_summary()` in 100% of cases tested against the 490-entry demo data.
- `RECIPES` dict + `get_recipe(name)` helper for dynamic lookup.
- **Token savings**: Claude previously wrote 50+ lines of Python to assemble a summary dict. Now it calls one function. Faster pipeline, less model work, fewer chances for bugs.

**Auto-validation**
- `scripts/build_pdf.py` and `scripts/build_pptx.py` now call `validate_summary()` before writing output. Any schema issues print as warnings to stderr but don't block generation (graceful degradation). Opt-out via `validate=False` parameter.

**Docs**
- `SKILL.md` Rule 2 now documents report recipes as the fast-path and instructs Claude to use recipes when available, hand-build when not.

**Coming next**
- Recipes for the remaining 12 report types (landing-page, form, ad-creative, keyword, source-to-CRM, campaign deep-dive, lead-profile, side-by-side, paid-vs-organic, budget-simulator, agency-rollup, lead-quality-scorer)
- Brand profile persistence via `memory_user_edits` so `/brand` config survives across conversations
- Mobile layout audit + a11y pass

## 0.9.1 — Apr 20, 2026

**Checkpoint 4: all 18 report specs migrated to the v0.8 section-based architecture.**

Until this release, only `monthly-performance-review.md` and `utm-hygiene-audit.md` had been rewritten to reference the section schema; the other 16 still described old slide-deck layouts. That mismatch meant Claude would sometimes read a report spec and try to generate HTML in the old per-report style, defeating the unified design language. v0.9.1 closes the gap.

**Migrated specs (16 new, 2 previously complete)**
- `weekly-executive-summary.md` — the 7-day one-pager
- `predictive-forecast.md` — 30-day projection with confidence range
- `anomaly-detector.md` — channel-level surprise detection
- `lead-quality-scorer.md` — declared-intent ranking for sales
- `top-campaign-leaderboard.md` — winners and sleepers
- `landing-page-performance.md` — ranked by URL with source mix
- `form-performance.md` — multi-form submission comparison
- `ad-creative-performance.md` — utm_content winners per channel
- `keyword-performance.md` — utm_term ranked by leads
- `source-to-crm-mapping.md` — B2B source × CRM cross-tab
- `campaign-deep-dive.md` — single-campaign full profile
- `lead-profile-enrichment.md` — single-lead attribution history
- `side-by-side-comparison.md` — two-entity verdict
- `paid-vs-organic.md` — the fundamental split
- `budget-simulator.md` — reallocation what-if modeling
- `agency-client-rollup.md` — portfolio view across brands

**Consistent structure**
Every spec now follows the same pattern: Triggers → Purpose → Before-you-build checklist → Data needs → Prior-period requirement (explicit yes/no) → Section order (with example content for each section) → Voice guidance → What-never-changes invariants. Claude can skim any spec in under 10 seconds and know how to build it correctly.

**Added**
- `reports/README.md` — catalog index grouped by report type (period-over-period, audits, leaderboards, deep dives, comparisons, agency). Lists every spec and its place in the system.

**Effect on behavior**
- Claude now picks the right section types for every report in the catalog instead of inventing layouts.
- Prior-period pulls are correctly scoped: only monthly, weekly, and forecast require them. 15 other reports now explicitly skip that MCP call — saves 5-15 seconds per report.
- Voice guidance is report-appropriate: forecasts get humble-about-prediction tone, side-by-sides get judicial verdict tone, lead profiles get sales-rep-ready tone, etc.

**What's next**
- Real-world testing against live customer WordPress sites (you).
- Mobile layout testing + a11y audit (still deferred).
- Brand auto-detection validation against 5 real sites.

## 0.9.0 — Apr 20, 2026

**Checkpoint 3: native PowerPoint export. The client-facing deck format Haktan asked for.**

**Added**
- **PPTX generator** via `scripts/build_pptx.py` using python-pptx. Produces a 16:9 widescreen native PowerPoint deck from the same `summary` dict that drives HTML and PDF. One slide per section. All 10 section types supported: title-block, stat-strip, hero-number, section-header, chart, chart-insight, ranked-list, recommendations, insight-card, closing.
- **Two-tone cards in PowerPoint** — rendered as stacked rectangles (tinted top + white bottom, hairline border) that match the HTML design language pixel-for-pixel on the design tokens. Fully native-editable: every text frame and shape can be selected, moved, or rewritten in PowerPoint/Keynote/Google Slides.
- **Italic *word* accents** in PowerPoint — rendered as italic text runs in the brand primary color, same as HTML and PDF. Title parsing supports any number of accents in any position.
- **PNG chart renderer** (`scripts/chart_renderer_png.py`) — mirrors the SVG renderer but outputs high-DPI (200 DPI) PNG bytes for reliable embedding in PowerPoint. All 7 chart types supported.
- **Headers and footers on every slide** — company name + "× UTM Grabber" tag at the top, data source + version + date + slide N/total at the bottom. Matches HTML/PDF structure.
- Tested end-to-end against 490-entry demo data. Build time: under 1 second. Output size: ~140 KB for a 10-slide deck. Verified by rendering to PDF via LibreOffice and visually inspecting every slide — title, stat-strip, section header, chart-insight, bar-horizontal chart, hero number, insight card, recommendations 2x2, closing all rendered correctly with correct typography, colors, and spacing.

**Changed**
- `SKILL.md` Rule 2 expanded to offer PPTX as a third post-report format alongside PDF and CSV: *"Want this as a PDF, PowerPoint deck, or the underlying leads as a CSV?"*
- `references/output-formats.md` PPTX section rewritten from "coming" placeholder to full documentation — when to offer, how to build, what to expect.

**Known**
- Fonts embed gracefully but Georgia/Calibri fallbacks apply if the client doesn't have Instrument Serif or Geist installed. Visual fidelity is ~90% with fallback fonts; 100% with the proper fonts.
- Chart rendering uses matplotlib (not PowerPoint's native charts) — this is intentional. Native PowerPoint charts can't match the brand-tuned styling, and PNG embedding is reliable across all PowerPoint versions.

**Coming next**
- v0.9.1: Migration of 16 remaining report specs to v0.8 section-based schema (mostly mechanical — the specs currently describe old slide-deck layouts).

## 0.8.2 — Apr 20, 2026

**Checkpoint 2: native PDF + CSV export. Client-ready output formats.**

**Added**
- **Native PDF generation** via `scripts/build_pdf.py`. Uses WeasyPrint (no browser required) and matplotlib for pre-rendered SVG charts. Produces a print-quality vector PDF that matches the HTML design 1:1 — same two-tone cards, same italic serif accents, same brand colors, same typography. Tested end-to-end against 490-entry demo data; 3-page output under 50KB.
- **CSV export** via `scripts/build_csv.py`. Flattens raw MCP entries into an Excel/Sheets-compatible CSV with 20+ standard columns: identity (email, name, company, phone), attribution (utm_source/medium/campaign/content/term, traffic_source), click IDs (gclid, fbclid, msclkid), page context (source URL, landing page, original referrer), lead-quality form fields, and technical details. Column order optimized for marketer workflows.
- **Matplotlib chart renderer** (`scripts/chart_renderer.py`) — renders all 7 v0.8 chart types (doughnut, bar-horizontal/vertical/stacked/grouped, line, area) to SVG strings for embedding in PDFs. Uses the same brand palette as Chart.js. Graceful error placeholder on malformed chart specs.
- **Bundled fonts** in `assets/fonts/` — Instrument Serif (regular + italic), Geist (regular + medium), Geist Mono. No network dependency at PDF render time; deterministic output anywhere.
- **`scripts/pdf_styles.css`** — dedicated print stylesheet, JS-free, table-based layouts for WeasyPrint compatibility.
- **`references/output-formats.md`** — documentation of when to offer each format and how each is built.

**Changed**
- `SKILL.md` Rule 2 now describes PDF/CSV as one-line follow-up offers after any HTML report: *"Want this as a PDF to send to your team? Or the underlying leads as a CSV?"*
- PDF and CSV share the same `summary` dict and cached entries as the HTML — no extra MCP calls to produce secondary formats.

**Coming next**
- v0.9.0: PPTX export (16:9 widescreen, mostly editable, all 10 section types)
- v0.9.1: Migration of 16 remaining report specs to v0.8 section schema

## 0.8.1 — Apr 20, 2026

**Rolling update.** Added mid-release after user testing found two issues: Claude was saying "about 15 seconds" in its acknowledgment message while actual runtime was 2-3 minutes (false promise), and reports were slower than necessary because Claude was re-running MCP discovery on every report.

**Fixed**
- Removed all hardcoded time promises from acknowledgment templates in `rendering-pipeline.md` and `voice-discipline.md`. Added explicit **banned pattern** against duration claims — "about 10 seconds", "this will take a minute", etc. are now forbidden. Actual runtime varies with MCP latency and data volume; any estimate is often wrong and erodes trust.
- Acknowledgment phrase is now short and time-neutral: "Pulling your last 30 days now.", "On it — one sec.", "Running the monthly review." — no seconds/minutes.

**Added (speed optimizations — significant real-world impact)**
- **Data-source memory**: After the first successful MCP discovery, Claude saves `customer_domain + form_plugin + form_ids` to memory via `memory_user_edits`. Subsequent reports skip the `check_site_health → get_form_plugins → list_forms` sequence entirely and go straight to `get_entries`. Saves 10-20 seconds per report.
- **Cache-check-before-MCP rule**: `rendering-pipeline.md` now explicitly requires calling `load_cached_entries()` from `helpers.py` before any MCP pull. Follow-up questions within the 1-hour TTL reuse cached data.
- **Skip prior-period pull for non-delta reports**: Only monthly, weekly, and forecast need period-over-period comparison. All other reports (leaderboard, audit, lead profile, etc.) now get ONE MCP call, not two.
- `SKILL.md` Rule 2 rewritten to surface these speed optimizations prominently, with explicit tool-call budgets: minimum 2 for cached follow-ups, 3-4 for fresh reports with saved data source, 7 worst case.

**Hotfix: v0.8.0 shipped with a critical behavioral bug — when users asked phrases like "walk me through this" or "use the skill", Claude read SKILL.md and summarized its contents as prose (breaking voice discipline and defeating the interactive welcome flow). This release fixes that plus adds Checkpoint 1 improvements.**

**Fixed (hotfix)**
- `SKILL.md` now opens with **Rule 0: DEMONSTRATE, NEVER META-EXPLAIN** — an explicit instruction that walkthrough/tour/demo/how-do-I-use requests ALWAYS trigger the welcome flow with interactive buttons, never a prose explanation.
- Welcome triggers expanded to include: "walk me through", "walk through", "show me", "show me how this works", "tour", "demo", "demo me", "teach me", "how do I use", "explain it", "introduce me", "get me started", "onboard me", "use the skill", "try the skill".
- `references/voice-discipline.md` adds a Rule 0 reinforcement section with banned response patterns ("Here's how X is put together:", "The four rules that...", "Under the hood...") and a required response script.
- `modes/welcome.md` opens with explicit "When to load this file" + "What NEVER to do when triggered" + "What TO do when triggered" so Claude can't reinterpret the flow.

**Added (Checkpoint 1 — compound wins)**
- `scripts/validate_schema.py` — schema validator that loads any summary JSON and verifies every required field, correct type, and sensible structure. Catches the class of bugs that plagued v0.7.x in 30 seconds. Can be run standalone (`python validate_schema.py summary.json`) or imported as `validate_summary(dict) -> list[str]`.
- **Session-level MCP caching** — `helpers.py` now exposes `cache_path`, `load_cached_entries`, and `save_cached_entries`. Follow-up questions in the same conversation reuse cached entries instead of re-pulling. Default cache TTL: 1 hour. Cache location: `/home/claude/cache/mcp-entries/`.
- **Polished print CSS** — `templates/report-shell.html` `@media print` block completely rewritten. Type scale, page-break hints, header repetition on multi-page tables, and letter-size `@page` margins. Browser `Print → Save as PDF` now produces a near-native quality PDF. This is the "Path A" PDF solution — next checkpoint brings Path B (WeasyPrint native).

**Coming next**
- v0.8.2: CSV export alongside every report + WeasyPrint native PDF generation
- v0.9.0: PPTX export (16:9 widescreen, mostly editable, 10 section types)
- v0.9.1: Migration of all 16 remaining report specs to the v0.8 section schema

## 0.8.0 — Apr 20, 2026

**Major release: unified data-driven template + two-tone design language.**

Real-user testing in v0.7.x exposed that every report was generating its own HTML from scratch, producing inconsistent designs (purple gradient covers in one report, white editorial in another, "SECTION 1 / 02/05" pagination in a third). Plus the original template was "standard SaaS" — rounded cards with left-accent bars that looked AI-generated. This release rewrites both the architecture AND the visual language.

**Architecture: one template, section-based rendering**
- `templates/report-shell.html` rewritten as a data-driven renderer. Reads a `sections` array from the embedded summary JSON and iterates, rendering each section by type.
- 10 section types cover every report shape: `title-block`, `stat-strip`, `section-header`, `hero-number`, `chart`, `chart-insight`, `ranked-list`, `recommendations`, `insight-card`, `closing`.
- Every chart call is wrapped in try/catch — one missing/malformed section can't break subsequent ones.
- Chart types supported: `doughnut`, `bar-horizontal`, `bar-vertical`, `bar-stacked`, `bar-grouped`, `line`, `area`.
- New `scripts/template-schema.md` documents every section type and its data shape.

**Design language: two-tone cards**
- Every card (stat, insight, recommendation, hero) is split into two zones: tinted brand-surface top + white bottom with a hairline divider. No accent bars, no drop shadows, no decoration.
- Numbers are italic Instrument Serif. Titles have one word per title wrapped in `*asterisks*` to render as an italic brand-colored fragment.
- Hairline borders (1px) on every card. 4px corner radius on outer cards.
- Brand color appears in TYPOGRAPHY (kickers, italic accents, chart bars) — never as a stripe or background.
- Delta indicators use Unicode arrows (▲ ▼) with no pill backgrounds.

**Consistency fixes**
- Previous "purple gradient cover" issue fixed — no gradients anywhere.
- Previous column-alignment issue in ranked-list fixed — table uses fixed column widths with proper `align-right`.
- Previous "standard SaaS left-accent card" replaced with the two-tone language.

**Docs**
- `references/design-contract.md` rewritten for v0.8.0 — describes the two-tone house style, italic-accent rule, color token system, forbidden patterns.
- `scripts/template-schema.md` new — full section-type reference with example JSON for each.
- All 18 report specs in `reports/` retain the "Design Contract mandatory" header from v0.7.5. The underlying architecture they reference is now the section schema rather than slide-deck layouts.

**Brand neutrality**
- All references to specific customer brands removed from the skill files. Examples in docs use a fictional "Acme Analytics" placeholder. The skill defaults to UTM Grabber's own blue palette on fresh install — users run `/brand` to configure their own.

**Known deferred work**
- The 18 individual report specs in `reports/` describe their layouts in the old slide-deck terminology. Monthly review and hygiene audit have been validated end-to-end against the new section schema (see `scripts/build-monthly-report.py`). The other 16 specs will be migrated to the section schema in subsequent patches, one report per iteration.

## 0.7.5 — Apr 20, 2026

**Design consistency enforcement. User ran `/audit` and got a report with a purple gradient cover, "SECTION 1 / 02/05" pagination, and bold sans-serif headlines — a completely different design language from the monthly review's editorial style. Root cause: only the monthly report explicitly referenced the shared template. The other 17 reports had no hard requirement to use it, so Claude generated fresh HTML with its own design choices each time.**

**Added**
- `references/design-contract.md` — 10 locked rules covering cover treatment, typography, color palette, section headers, card patterns, footer, and "what to do when in doubt." Explicitly forbids purple gradients, "SECTION N" labels, "02/05" pagination, decorative fonts, and any per-report design drift.

**Changed**
- All 18 report markdown files now open with a MANDATORY Design Contract section requiring: (1) read the contract, (2) use `templates/report-shell.html` — don't generate HTML from scratch, (3) don't invent new slide types or color schemes per report.
- `SKILL.md` now opens with FOUR rules (was two): voice, speed, no-PDF, and design consistency. Design rule is as prominent as voice/speed.

**Known limitation (fixed in v0.8.0)**
- The shared template currently has monthly-deck-specific slide structures hardcoded (eyebrows like "Executive Summary", titles like "The 30-day snapshot"). Reports with different content shapes (audit = hygiene score + leaky URLs, weekly = 1-page summary, forecast = confidence-band chart) will need the template refactored to be fully data-driven in v0.8.0. Until then, reports must adapt their content to fit the existing slide types — which still produces consistent visual language but may feel forced for some report types.

## 0.7.4 — Apr 20, 2026

**Third real-user fix. v0.7.3 had try/catch safety but the summary still missed several template-required fields (channel_mix_narrative, source_bullets, source_headline, campaign_headline, multi_touch_narrative, lead_quality.crms, lead_quality.primary_goal, lead_quality.profile_line, paid_pct/utm_coverage_pct as numerics). Charts that referenced these silently skipped, leaving blank slides.**

**Fixed**
- Full schema audit of the template — every field the template expects is now documented and produced.
- `lead_quality.crms` (plural, with `{name, count}`) vs `lead_quality.spend` (with `{label, value}`) vs `lead_quality.primary_goal` (with `{labels, values}`) inconsistencies are now documented and respected.
- `totals.paid_pct` and `totals.utm_coverage_pct` are now numeric (template builds the string versions). Previously setting `_str` directly caused template to overwrite with `undefined%`.
- Added `scripts/template-schema.md` as the canonical reference for what the template expects.
- Added `scripts/build-monthly-report.py` as a working reference implementation that produced the demo rendering correctly.

## 0.7.3 — Apr 20, 2026

**Second real-user-test fix. v0.7.2 rendered the cover correctly but broke on slide 2 with "Cannot read properties of undefined (reading 'sources')" — the chart rendering code was accessing data sections the summary didn't include, and the first access failure killed all subsequent charts.**

**Fixed**
- Each `new Chart(...)` call in the template is now wrapped in try/catch. A missing data section logs a warning but no longer prevents other charts from rendering.
- Added `compute_channel_breakdown` helper to `scripts/helpers.py` so the source × medium matrix is always computed from real data.

**Notes**
- Verified end-to-end with real 490-lead data from the demo site. All 7 charts render, all data sections populate, brand colors apply, console is clean.

## 0.7.2 — Apr 20, 2026

**Emergency patch. v0.7.0 and v0.7.1 shipped a subtle injection bug that produced blank reports: empty stat cards, no charts, no brand colors. Root cause was a too-loose regex that matched mentions of the data tag inside HTML comments, then silently deleted large sections of the template including the `<style id="brand-overrides">` tag. Without that tag, the template's JavaScript errored out with "Cannot read properties of null (reading 'textContent')" and stopped populating anything.**

**Fixed**
- Template injection regex now requires `type="application/json"` on the target tag — prevents matching comments or documentation mentions.
- Verified end-to-end against the live demo site: 490 leads pulled, summary computed, template rendered, all data slots populated, all charts drawn correctly.

**Notes**
- HTML-only output continues (PDF still hard-banned until v0.8.0 does the template rewrite that makes PDF work).
- Voice and speed rules from v0.7.0 remain in effect.

## 0.7.1 — Apr 19, 2026

**Emergency patch. Real-user testing produced broken PDFs (empty stat cards, missing charts, no branding). Root cause: the HTML template relies on JavaScript to populate values, render charts, and apply brand colors — and WeasyPrint does not run JavaScript. The PDF was rendering the pre-load shell.**

**Changed**
- **PDF generation is now hard-banned in v0.7.x.** The skill produces HTML only. If a customer asks for PDF, Claude directs them to browser print-to-PDF instead.
- `SKILL.md` now has three rules at the top: voice discipline, speed discipline, and "never generate PDF". PDF rule is explicit with recovery language.
- `references/rendering-pipeline.md` removes the matplotlib SVG / print-variant pipeline entirely — it was producing unreliable output.

**Planned for v0.8.0**
- Rewrite template rendering to be fully Python-side (no JavaScript dependency), so HTML is self-contained and PDF conversion works identically. Will enable proper native PDF export.

## 0.7.0 — Apr 19, 2026

**This is a voice + speed discipline release. Real user testing showed the skill was still narrating technical process ("I'll run the Python script...") and using too many tool-call rounds, hitting turn limits and forcing users to tap "Continue". Both are fixed with forcing rules.**

**Added**
- `references/voice-discipline.md` — strict voice rules with banned words list, banned patterns, and before/after examples. Marks "Python", "script", "render", "pipeline", "MCP", "tool-use limit", "JSON" etc. as never-to-appear in customer-facing chat output. Explicit response length budget (≤3 sentences / ≤50 words per report delivery).

**Changed**
- `references/rendering-pipeline.md` rewritten around a **4-tool-call ceiling per report**: 1 MCP pull, 1 Python execution (combines transform + inject + save), 1 present_files. Previous pipeline had Claude split compute and inject into 2 separate bash calls — now combined into a single script.
- Default MCP strategy is now **single-shot** (`limit: 1500`), not weekly-chunked. Chunking only fires as a silent fallback if truncation is detected.
- PDF generation is no longer automatic. HTML only by default — PDF becomes an explicit follow-up button.
- `SKILL.md` now opens with TWO prominent rules (voice discipline + speed discipline) before anything else. Previous version had speed as one of many sections, which Claude was skimming past.
- Error messages are now translated to customer language at the point of delivery — "your site isn't responding" instead of "MCP 500 error".

**Fixed**
- Process narration in chat responses ("I'll pull the data, then compute the aggregations, then render...") — banned explicitly.
- Technical vocabulary leaking into customer messages — banned with an explicit word list.
- Multi-round tool orchestration causing turn-limit "Continue" prompts — collapsed into single-script execution.

## 0.6.0 — Apr 19, 2026

**Added**
- Interactive buttons throughout the skill via `ask_user_input_v0` — welcome role selection, brand setup path, auto-detect confirmation, report picker, follow-up offers, form selection, date range, and rollup confirmation. No more typing letters or remembering slash commands for the most common flows.
- `references/interactive-buttons.md` — comprehensive guide for when/how to use buttons vs plain text, with 8 concrete use cases.
- `scripts/helpers.py` — 350+ lines of pre-built Python aggregation functions: `classify_traffic_source`, `compute_hygiene`, `compute_period_delta`, `compute_channel_mix`, `compute_source_leaderboard`, `compute_campaign_leaderboard`, `compute_daily_volume`, `compute_multi_touch`, `compute_form_field_distribution`, `normalize_url`, `format_delta_pill`, `format_date_range`, `load_entries_from_mcp_result`. Every report imports these instead of re-implementing.
- Conversation-scoped disk cache at `/home/claude/cache/` — subsequent reports in the same session reuse data from the first pull, 30-50% speedup for multi-report workflows.
- Static SVG chart generation via matplotlib for PDF exports — Chart.js canvases are replaced with SVG in a "print-variant" HTML before WeasyPrint conversion. PDFs now have real charts, not blank boxes.
- SAMPLE watermark on the example HTML — large diagonal "SAMPLE · DEMO DATA" overlay prevents customers from mistaking the demo for their actual report. Gated by `meta.is_sample: true` flag (not present in real runs).
- Expected duration hints in `modes/prompt-shortcuts.md` — every shortcut shows wall-clock time so customers don't bail mid-render.

**Changed**
- MCP pulling now uses chunked weekly windows by default (5× `limit: 500` for a monthly report) instead of `limit: 0`. Works on any site size, never blows context, retry-friendly per chunk.
- Q&A mode explicitly SKIPS the automatic comparison-window pull. Saves 2-3 seconds per question. Only pulls comparison when user explicitly asks for a time comparison.
- Brand onboarding restructured around 4 path buttons (auto-detect / quick / advanced / skip) instead of sequential free-text prompts.
- Welcome mode now uses 2 rounds of buttons (role → report picker) instead of lettered text lists that collapsed into paragraphs.
- Universal workflow in `SKILL.md` updated with explicit Python-transform step and fast-path template injection.

**Fixed**
- PDF chart rendering — WeasyPrint doesn't execute JS, so Chart.js canvases were blank. Now pre-rendered as matplotlib SVGs and injected into print-variant HTML.
- Lettered option lists (`**A.** Option`) collapsing into single paragraphs in Claude chat UI. Replaced throughout with proper button tool or markdown bullets.

## 0.5.1 — Apr 19, 2026

**Fixed**
- Rendering speed: reports now use a fast-path pipeline that computes aggregations in Python via `bash_tool` and injects data into the existing HTML template instead of regenerating the template inline. Reduces Claude's output from ~40KB to ~500 tokens per report. Full 10-slide monthly review now renders in ~15 seconds instead of hitting output-length limits.

**Added**
- `references/rendering-pipeline.md` — explicit fast-path rendering instructions with Python script templates.
- Chat response length budget (≤4 sentences, ≤80 words) to prevent chat duplicating slide content.
- Prominent speed rule at top of `SKILL.md` so Claude reads it before any report.

**Changed**
- Universal workflow: added step 4 (transform via Python) and step 6 (respond concisely) as distinct steps.
- Template is now READ from disk, not regenerated. Only the `<script id="report-data">` block gets replaced.

## 0.5.0 — Apr 19, 2026

**Added**
- Welcome / first-run experience (`modes/welcome.md`) with role-based recommendations (marketer, agency, exec, explorer).
- Side-by-Side Comparison report (`reports/side-by-side-comparison.md`) for non-time-based comparisons (form vs form, campaign vs campaign, etc.).
- PowerPoint export support across all reports (`references/pptx-export.md`).
- VERSION.md + CHANGELOG.md for version tracking.
- Decision tree in `SKILL.md` for faster report routing.
- Error recovery sections in every report file with consistent "what if data is thin / MCP fails" language.
- Data freshness line on cover slide and visible in all reports.

**Changed**
- Template: version + pulled_at timestamp now shown on every cover slide.
- All reports now reference `references/mcp-usage.md` explicitly for error handling.

## 0.4.0 — Apr 19, 2026

**Changed**
- Design pass: removed AI-generic patterns (colored top bars on stat cards, solid ink header band, coral-circle numbered recommendations).
- Editorial stat strip: unified card with hairline dividers, label-on-top / big-serif-number / delta-pill pattern.
- Slide header: title on paper with short coral accent rule (replaces ink rectangle).
- Insight cards: subtle outlined card with underlined eyebrow (no more left-border pattern).
- Recommendation cards: "ACTION 01" editorial label pattern (no more coral circles).
- Footer: dedicated zone with hairline top border, proper padding, two-line layout.
- Chart captions: increased padding, proper sizing (12px), normal flow instead of absolute-positioned.

**Fixed**
- Footer text no longer overflows slide edges.
- Coral vertical rule stops above footer zone instead of cutting through it.
- Chart captions have breathing room from chart body.
- Canvas rendering after flex-column changes — wrapped in positioned `chart-wrap` div for proper Chart.js sizing.
- Type scale: rolled back oversized body copy (27px → 15-16px), labels (17px → 12-13px), tag pills (27px → 12px).

## 0.3.0 — Apr 19, 2026

**Added**
- Brand onboarding flow (`utilities/brand-onboarding.md`) with `web_fetch`-based auto-detection from customer websites.
- Brand profile reference (`references/branding-profile.md`) — persistent profiles stored in Claude memory.
- Agency multi-brand workflow (`references/agency-multi-brand.md`) — one profile per client, `/brand switch` for rapid context change.
- `/brand` slash command family: `setup`, `switch`, `edit`, `new`, `remove`, `export`, `reset`.
- Budget Simulator report (`reports/budget-simulator.md`) — what-if modeling with mandatory caveats about diminishing returns.
- Lead Profile Enrichment report (`reports/lead-profile-enrichment.md`) — single-person dossier with journey + sales-angle bullets.

**Changed**
- Template now reads `meta.brand_profile` and dynamically applies customer's colors, logo, and footer style.
- Footer string splits into brand line + data-source audit line.
- Three footer styles supported: `client-branded`, `co-branded`, `utm-grabber`.

## 0.2.0 — Apr 19, 2026

**Added**
- Form Performance Report.
- Top Campaign Leaderboard.
- Landing Page Performance.
- Ad Creative Performance (`utm_content` analysis).
- Keyword Performance (`utm_term` analysis with intent classification).
- Predictive Forecast (trailing average + linear trend, confidence bands).
- Conversational Q&A mode.
- Custom Report Builder mode.
- Prompt Shortcuts (`/monthly`, `/weekly`, `/audit`, etc.).
- Period-over-period comparisons (universal, every metric).
- Accessibility: WCAG-AA contrast, grayscale-legible charts, aria labels on chart containers.

## 0.1.0 — Apr 19, 2026

**Initial release**
- 10 reports: Monthly Performance Review, Weekly Executive Summary, Campaign Deep Dive, UTM Hygiene Audit, Paid vs Organic, Source-to-CRM Mapping, Lead Quality Scorer, Anomaly Detector, Agency Client Rollup.
- UTM Template Generator utility.
- Brand-locked HTML template with Chart.js.
- Reference files: design system, data dictionary, MCP usage, narrative voice.
