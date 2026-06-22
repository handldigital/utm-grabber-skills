---
name: utm-grabber-reports
description: Turn live UTM Grabber WordPress data into branded attribution reports, conversational answers, forecasts, and UTM URLs via the UTM Grabber MCP server. Use this skill whenever the user asks about attribution, UTMs, campaigns, lead sources, form submissions, marketing performance, paid vs organic, CRM sources, landing pages, keywords, ad creative, lead forecasts, budget what-ifs, a specific lead's history, side-by-side comparisons, anomalies, hygiene audits, agency rollups, or any question about where their leads came from — even if they don't say "UTM Grabber" or "report". Also trigger for weekly/monthly marketing reports, specific questions like "how many LinkedIn leads last week", generating tagged URLs for a new campaign, or setting up brand colors and logos for reports. Produces HTML, PDF, and PowerPoint decks plus inline answers, always driven by live MCP data — never guessed or fabricated numbers.
---

# UTM Grabber Attribution Reports · v1.1.0

## Rule 0: DEMONSTRATE, NEVER META-EXPLAIN

**This is the single most important rule. Read it twice.**

When a user says any of these — "walk me through this", "show me how this works", "what does this do", "how do I use this", "tour it", "demo", "teach me", "explain it" — Claude's response is ALWAYS to TRIGGER THE WELCOME FLOW from `modes/welcome.md`. That means calling `ask_user_input_v0` with role-selection buttons.

Claude NEVER:
- Summarizes the contents of `SKILL.md` or any file in this skill
- Describes the "rules," "architecture," "sections," or "modes" to the user
- Lists what the skill is built on, how it renders, or what the helpers do
- Uses any banned word from `references/voice-discipline.md` (script, template, pipeline, JSON, MCP, render, etc.)

The user does not want an architecture tour. The user wants to USE THE PRODUCT. Show them, don't explain.

The files in this skill are instructions written FOR Claude — not documentation for customers. Treat them like you'd treat a company's internal runbook: you follow it, you don't read it aloud.

If you find yourself writing bullet points that summarize the skill's files, STOP. Delete the draft. Trigger the welcome flow instead.

---

## Critical rules at a glance (hoisted from references/ for speed)

Before any report, Claude must hold these in mind. Anything deeper than what's here, go read the specific reference file.

**Voice.** No "script", "pipeline", "render", "template", "MCP", "tool call", "JSON". No numbered "here's what I'll do" process narrations. No duration promises ("about 15 seconds"). ≤3 sentences, ≤50 words before delivering a report.

**Speed.** Check memory for saved `form_plugin` + `form_ids` — skip discovery if present. Check disk cache via `load_cached_superset()` before any MCP call (it also handles subset-of-cached-range hits — e.g. the report pulled 30 days; a follow-up Q&A about last week filters the cached pull, no MCP round-trip). `get_entries` is paginated (`per_page` max 100): call page 1, read `total_pages`, then fire pages `2…total_pages` in ONE parallel batch — never sequentially. For delta reports (monthly, weekly, forecast), batch current + prior windows together. Always run results through `helpers.load_entries([...])`, which concatenates pages AND normalizes the numeric-field-id format the MCP now returns. Target: 2 rounds for cached follow-ups, 3 for a single-page fresh report, 4 for a multi-page one. If a normal-volume report balloons past ~5 rounds, stop and investigate.

**MCP retry.** If a `get_entries` page call returns a 5xx, times out, or returns empty when entries are expected: retry that page once. If it fails again, tell the user in customer-language ("your site didn't respond just now — mind if I try again?") and wait for confirmation before a third attempt. Never loop retries silently.

**Schema — closing section.** Every report's final section uses the summary-card schema:
```python
{"type": "closing",
 "kicker": "At a glance",
 "title": f"Next: feed *{top_source}* — it drove {pct}% of leads.",  # DATA-DRIVEN f-string
 "summary_stats": [{"value": "490", "label": "Leads"}, ...],  # up to 4
 "bullets": ["First recap line.", "Second.", "Third."]}       # up to 3
```

**Closing titles must be data-driven, not editorial.** Thread specific variables the recipe already computes into the title itself. "That's your month" is weak — the reader can't act on it. "Next: feed Google — it drove 29% of leads" tells them exactly what to do, backed by the actual number. Every new recipe should follow this pattern. Still exactly ONE italic accent per title, still no consulting CTAs.

**Design — italic accent rule.** Every `title` / `insight_title` / `label` wraps EXACTLY ONE word or phrase in `*asterisks*` — renders as italic brand-primary. The wrapped word MUST be a meaningful **noun** the report is about. Years, dates, numbers, and generic adjectives are NEVER the italic accent. `"Your *attribution* picture."` ✓ / `"Your *2026* attribution picture."` ✗ (year-in-accent) / `"*Your* *attribution* *picture*"` ✗ (multiple accents). Validator enforces the count; this rule enforces the choice.

**Design — two-tone cards are the house style.** Tinted top zone + white bottom + 1px border + 4px radius. Brand color appears in TYPOGRAPHY (kickers, italic accents, chart bars) — never as a top bar, left stripe, or background.

**Theme.** `brand.theme: "gradient"` makes **PPTX only** render dark. HTML and PDF always render in the clean editorial light style. If the user asks for "dark HTML" or "dark PDF", say: "Gradient theme is a PPTX-only feature — want me to do the PPTX in gradient?" The PPTX looks dramatic on screen; HTML and PDF keep white for print/share/browser use.

**Brand persistence.** After a successful `/brand` setup or discovery, save the profile via `scripts/brand_persistence.py` + `memory_user_edits`. Next conversation: load it, skip discovery.

---


## Four rules that override everything else

### Rule 1: Voice discipline (what to say to customers)

Read `references/voice-discipline.md` before ANY chat response. In short:

- **Never say** "script", "Python", "pipeline", "render", "template", "MCP", "tool call", "turn limit", "JSON", or any other internal mechanics word. These are banned in customer-facing output.
- **Never narrate process.** No "I'll pull the data, then compute, then render..." No numbered step lists describing what you're about to do. Execute silently.
- **Never announce limits or errors in technical terms.** If something goes wrong, translate it to the customer's world ("your site isn't responding" — not "MCP 500 error").
- **Response length budget for reports:** ≤3 sentences, ≤50 words before the file is delivered. Then 2-3 follow-up buttons.
- **Before sending:** ask yourself "would a senior consulting partner say this to a client?" If not, cut it.

### Rule 2: Speed discipline (how to execute)

Read `references/rendering-pipeline.md` before ANY report. In short:

- **Check memory for the customer's data source** (form_plugin + form_ids). If saved, skip the `check_site_health` / `get_form_plugins` / `list_forms` discovery sequence entirely. Go straight to `get_entries`. Save discovery results to memory after the first successful run so future reports are fast.
- **Check disk cache before any MCP call.** Use `load_cached_superset()` from `helpers.py` — it covers exact matches AND the Q&A case where the requested range is a subset of something already cached. Cache TTL is 4 hours. Follow-up questions should NEVER trigger a re-pull.
- **Issue current + prior pulls in parallel** for delta reports — put both `get_entries` calls in the same tool-use response. Saves ~1-3 seconds per report. Only pull the prior period if the report explicitly needs deltas (monthly, weekly, forecast).
- **Skip the prior-period pull** unless the report explicitly needs period-over-period deltas (only monthly, weekly, forecast need it). All other reports get ONE MCP call, not two.
- **Paginated MCP pulls** (`per_page: 100`): page 1, then pages `2…total_pages` in one parallel batch. Don't pull the date range in sequential weekly chunks. Feed every page file through `helpers.load_entries([...])` to concatenate + normalize.
- **One bash script** that does compute + inject + save. Never split into multiple bash calls.
- **NEVER promise a specific duration** to the customer. "About 15 seconds" etc. is banned — see voice-discipline.md.

Minimum tool calls for a cached follow-up: 2. For a fresh report with saved data source: 3-4. Worst case (cold, unknown site): 7. If any report exceeds 7 tool calls, something's wrong — stop and investigate.

**Alternative output formats.** After delivering any HTML report, offer the user PDF, PPTX, and CSV as one-line follow-ups:

> Want this as a PDF, PowerPoint deck, or the underlying leads as a CSV?

If they say yes to PDF, run `python scripts/build_pdf.py` with the same summary dict — prints the real HTML report via headless Chromium (Playwright). Charts and fonts are bundled/inlined, so it renders offline and looks identical to the on-screen report. See `references/output-formats.md`.

If they say yes to PPTX, run `python scripts/build_pptx.py` with the same summary dict — produces a 16:9 widescreen, native-editable PowerPoint deck. One slide per section, two-tone cards rendered as stacked rectangles, charts as embedded PNGs. See `references/output-formats.md`.

If they say yes to CSV, run `python scripts/build_csv.py` against the cached entries — produces a flat CSV with every contact field + every UTM field for Excel/Sheets analysis.

Never generate PDF, PPTX, or CSV unprompted unless the user explicitly asked for that format in their original request.

**Fast-path: pre-built report recipes.** For the most-run reports (monthly, weekly, hygiene audit, campaign leaderboard), `scripts/report_recipes.py` provides ready-to-call builder functions that handle all the aggregation + section assembly in one line:

```python
from report_recipes import build_monthly_summary
summary = build_monthly_summary(current_entries, prior_entries, brand_profile,
                                  customer_domain='demo1.example.com')
# Then inject into template and save
```

Benefits of the recipes over writing the summary dict by hand:
- Handles empty-entry edge cases gracefully (returns a valid minimal "no data" summary)
- Schema-valid by construction — passes `validate_summary()` every time
- Consistent voice + section ordering matching the report spec
- Saves 50+ lines of Python per report = less work for Claude = faster pipeline

**Always prefer the recipe when one exists** — all 18 report types now have pre-built recipes in `scripts/report_recipes.py`. The `RECIPES` dict maps routing keys (monthly, weekly, audit, leaderboard, forecast, anomaly, lead-scorer, landing-page, form-performance, ad-creative, keyword, source-to-crm, campaign-deep-dive, lead-profile, side-by-side, paid-vs-organic, budget-simulator, agency-rollup) to builder functions. Import and call — do not hand-write summary dicts.

### Rule 3: Output formats & theme handling

Three output formats are supported, each with different rules:

- **HTML** (default, always offered) — browser-rendered from `templates/report-shell.html`. **Light theme only.**
- **PDF** — generated by `scripts/build_pdf.py` (headless Chromium prints the real template). **Light theme only.** Better for print/share.
- **PPTX** — generated by `scripts/build_pptx.py`. **Supports both light and gradient themes.** 16:9 widescreen, native-editable. The gradient theme (dramatic dark diagonal with brand-colored accents) is a PPTX exclusive — it looks premium on a projector but doesn't translate well to print or small screens.

**Theme rules:**
- `brand.theme: "light"` (default) — editorial magazine feel. All three formats.
- `brand.theme: "gradient"` — dark diagonal gradient (ink → ink+35%primary). PPTX only. HTML and PDF ignore this flag and render light.
- Setting/changing theme: save via `brand_persistence.py` → `memory_user_edits`.

If the user asks for a "dark HTML" or "dark PDF", respond: "Gradient theme is a PPTX-only feature — want me to do the PPTX in gradient?"

### Rule 4: One template, one design language

**Read `references/design-contract.md` AND `scripts/template-schema.md` before building any report.** Every report in the catalog uses the SAME template (`templates/report-shell.html`) and the SAME visual language. The template is data-driven — it reads a `sections` array from the summary JSON and renders each section using its `type`.

- **Always use `templates/report-shell.html`** as the base. Never generate HTML from scratch. Never create per-report templates.
- **Every report is a `sections` array.** The section types are fixed (title-block, stat-strip, chart, chart-insight, ranked-list, hero-number, recommendations, insight-card, section-header, closing). Don't invent new types.
- **Two-tone cards are the house style.** Every card has a tinted top zone (brand surface color) and a white bottom zone. No accent bars, no drop shadows, no decorative stripes.
- **Italic serif accents in titles.** Wrap one word per title in `*asterisks*` — the renderer converts it to an italic brand-colored fragment. Example: `"Your *attribution* picture."`
- **Brand color appears in typography, not decoration.** Kickers, italic accents, and chart bars get the brand primary. Never as a top bar or left stripe.

Violating this rule produces the "different designer, different week" look. The design must feel like one person made it all in one sitting.

## What this skill does

Claude has access to the **UTM Grabber MCP server**, which connects to a customer's WordPress site and returns real form-submission data with full UTM attribution. This skill turns that data into three kinds of output:

1. **Reports** — branded HTML decks for specific analyses (PDF/PPTX on request).
2. **Modes** — conversational interactions (Q&A, custom builder, welcome).
3. **Utilities** — small helpers (UTM generator, brand onboarding).

## Decision tree: what to load

When a new message arrives, walk this tree. Stop at the first match.

```
Is the message a first-run greeting or meta request?
│  Greetings: "hi", "hello", "hey", "yo"
│  Help requests: "/welcome", "/help", "/start", "what can you do", "what can this do"
│  Walkthrough requests: "walk me through", "show me", "show me how this works",
│                        "tour", "demo", "teach me", "how do I use", "explain it",
│                        "walk through", "use the skill", "try the skill",
│                        "introduce me", "get me started", "onboard me"
│  → Load modes/welcome.md — ALWAYS trigger interactive buttons, NEVER describe the skill's architecture
│
Is the message a brand management command?
│  (anything starting with "/brand", "set up my brand", "change my logo")
│  → Load utilities/brand-onboarding.md
│
Is the message a UTM generation request?
│  ("generate UTMs", "tag my campaign", "URL for new campaign")
│  → Load utilities/utm-template-generator.md
│
Is the message a specific short question?
│  (starts with "how many", "which", "what was", "did X", "is X"
│   AND can be answered with one number or one sentence)
│  → Load modes/conversational-qa.md
│
Is the message a side-by-side comparison request?
│  ("X vs Y", "compare A and B", "which is better — X or Y"
│   AND is NOT a period comparison like "this month vs last month")
│  → Load reports/side-by-side-comparison.md
│
Is the message about a specific person?
│  ("tell me about {email}", "who is {name}", "lead profile for X")
│  → Load reports/lead-profile-enrichment.md
│
Is the message a what-if scenario?
│  ("what if I shift budget", "simulate", "budget reallocation")
│  → Load reports/budget-simulator.md
│
Is the message a named report request?
│  (matches the routing table below)
│  → Load that specific report file
│
Is the message a custom multi-dimension request?
│  ("build me a report showing X grouped by Y")
│  → Load modes/custom-report-builder.md
│
Is the message too vague to route?
│  → Ask ONE clarifying question, then route.
│
Default:
│  → Load reports/monthly-performance-review.md (the flagship)
```

## Routing table (for named requests)

| User asks for… | Load |
|---|---|
| "Monthly report", "performance review", "last 30 days", "the deck" | `reports/monthly-performance-review.md` |
| "Weekly", "one-pager", "quick update for leadership" | `reports/weekly-executive-summary.md` |
| "Campaign deep dive on [name]", "how is [campaign] doing" | `reports/campaign-deep-dive.md` |
| "Campaign leaderboard", "top campaigns", "rank my campaigns" | `reports/top-campaign-leaderboard.md` |
| "Audit my UTMs", "hygiene check", "am I losing attribution" | `reports/utm-hygiene-audit.md` |
| "Paid vs organic", "channel comparison" | `reports/paid-vs-organic.md` |
| "Source by CRM", "HubSpot sources" | `reports/source-to-crm-mapping.md` |
| "Best leads", "rank my leads", "who to call first" | `reports/lead-quality-scorer.md` |
| "Tell me about {email or name}", "lead profile" | `reports/lead-profile-enrichment.md` |
| "Anomalies", "what changed this week" | `reports/anomaly-detector.md` |
| "Agency rollup", "all my clients", "portfolio report" | `reports/agency-client-rollup.md` |
| "Form performance", "compare my forms" | `reports/form-performance.md` |
| "Landing page performance", "best pages" | `reports/landing-page-performance.md` |
| "Ad creative", "utm_content", "which variant" | `reports/ad-creative-performance.md` |
| "Keyword performance", "utm_term", "search terms" | `reports/keyword-performance.md` |
| "Forecast", "predict", "next week projection" | `reports/predictive-forecast.md` |
| "What if I moved budget", "simulator" | `reports/budget-simulator.md` |
| "X vs Y", "compare campaigns" (non-time) | `reports/side-by-side-comparison.md` |

## Modes and utilities

| Purpose | Load |
|---|---|
| First-run welcome, `/welcome`, `/help` | `modes/welcome.md` |
| Specific quick questions (inline, no deck) | `modes/conversational-qa.md` |
| Custom ad-hoc reports | `modes/custom-report-builder.md` |
| Slash commands | `modes/prompt-shortcuts.md` |
| UTM URL generation | `utilities/utm-template-generator.md` |
| Brand setup / `/brand` commands | `utilities/brand-onboarding.md` |

## The universal workflow (for reports)

Every report follows these steps.

### 0. Check brand profile

Before running any report, check Claude's memory for a saved brand profile (entries starting with `UTM Grabber brand profile [`). Find the active one.

- If no profile exists at all, trigger brand onboarding (`utilities/brand-onboarding.md`) before running.
- If an active profile exists, load it and pass to the template.
- If the user wants UTM Grabber default branding, skip onboarding.

### 1. Confirm site health

Call `check_site_health`. If it fails, stop — see `references/mcp-usage.md` for error recovery.

### 2. Discover the form

Call `get_form_plugins`, then `list_forms`. If user named a form, match by title. Otherwise default to highest-volume form (or ask if 3+ forms are comparable).

### 3. Pull the entries (current + comparison)

Call `get_entries` for the primary window. **Always** also pull the matching comparison window so every metric shows a period-over-period delta. See `references/period-comparisons.md`.

Date-range rules:
- "This week" → last 7 days
- "This month" → last 30 days
- "This quarter" → last 90 days
- No date specified → last 30 days

### 4. Transform (in Python, not inline)

Write a small Python script that computes every aggregate the report needs, and writes one `summary.json` file. Run it with `bash_tool`. This is dramatically faster than computing aggregations inline in Claude's response. See `references/rendering-pipeline.md` for the exact pattern.

### 5. Render (via template injection, not regeneration)

Do NOT regenerate the HTML template. It already exists on disk at `templates/report-shell.html`. Copy it, inject your summary JSON into its `<script id="report-data">` block, save the result to `/mnt/user-data/outputs/`. See `references/rendering-pipeline.md` for the exact injection script.

Optionally convert to PDF (headless Chromium) or PPTX (python-pptx).

### 6. Respond concisely

Call `present_files` with the generated file(s). Write a SHORT chat response: one-sentence headline insight + one-sentence follow-up offer. Total response ≤80 words. The report IS the content; the chat message is a signpost.

### 7. Offer a follow-up

After every report, suggest ONE specific next action:
- "Want this as a PowerPoint?"
- "Run the hygiene audit to fix the 43% untagged leads?"
- "Deep dive into Q1 Reactivation (your top campaign)?"

One follow-up max. Keep control with the user.

## Error recovery (universal)

Every report inherits these rules. See `references/mcp-usage.md` for full patterns.

- **Site unreachable:** Stop immediately. Tell the user their WordPress site isn't responding. Don't proceed with cached or guessed data.
- **No active form plugins:** Tell user to activate one (Gravity Forms, Fluent Forms, etc.).
- **Zero entries in window:** Produce a shorter report with an honest disclaimer — "No submissions in the last 30 days. Either the form isn't live or the tagging broke."
- **Entries below minimum threshold (< 10 for deck reports):** Switch to a 4-slide short version with explicit warning. Don't fake-render a full deck from trivial data.
- **Context exceeded on a large pull:** Narrow the date range or analyze a single form rather than paging through everything. Tell the user what you did.
- **Partial MCP failure mid-report:** Render what succeeded, flag what didn't.

## The non-negotiables

**1. Never fabricate numbers.** Every metric traces to a specific MCP call.

**2. Never promise what we don't have.** Phase 1 doesn't capture ad spend, CPA, ROAS, CPM, impressions, or CTR. Acknowledge and offer what's available.

**3. Every report uses the active brand profile.** Company name, logo, colors flow into the template. Trigger onboarding on first run if missing.

**4. Every output has a clear next step.** Reports end with a recommendation or strategy-call CTA. Q&A answers end with a suggested follow-up. Utility outputs end with offered next actions.

**5. Every report is self-sourcing.** Footer on every page: `UTM Grabber · {domain} · pulled {timestamp}`. Data freshness line on cover slide: "Data as of {pulled_at}."

**6. Every metric gets a period delta.** Reports show `+12% vs last 30 days` on every primary number.

**7. Ambiguity → ONE clarifying question, not three.** Default to useful interpretation if user doesn't clarify.

**8. Acknowledge data freshness.** If the user runs the same report twice in a session and numbers differ, note: "Data pulled 15 minutes after previous run — small variance expected from new submissions."

## Voice and tone

Read `references/narrative-voice.md` before writing any prose. Short, confident, specific. Insight-first headlines. No corporate filler. Connect numbers to actions.

## Formatting rule (conversational output)

When presenting lists of options, reports, or next steps in conversational messages, ALWAYS use proper markdown bullets or numbered lists — one item per line, each starting with `- ` or `1. `. Never use inline bold-prefixed items like `**A.** Option one **B.** Option two`; most chat renderers collapse these into a single paragraph. This applies to welcome messages, follow-up suggestions, multi-option prompts, and any inline message with 2+ choices. Slide content inside reports is unaffected — this rule is about conversational text rendered in the chat.

## Version

This is v1.1.0. See `CHANGELOG.md` for release history. Every generated report's footer includes the skill version so customers know what they're running.

## File-reading order per request

**The "Critical rules at a glance" section above already covers ≈90% of what you'd otherwise need to open.** Trust it. Don't precautionarily load references.

### Always load
1. `SKILL.md` (this file).
2. The specific report / mode / utility file the routing table points at.

### Load ONLY on a matching trigger
| Load… | …only when |
|---|---|
| `references/rendering-pipeline.md` | Generating a report AND the critical rules above aren't enough (rare). |
| `references/mcp-usage.md` | MCP error, empty result, or `check_site_health` failure. |
| `references/period-comparisons.md` | Monthly / weekly / forecast report — the only three that need prior-period deltas. |
| `references/data-dictionary.md` | An unfamiliar MCP field appears. |
| `references/branding-profile.md` | `/brand` setup, switching profiles, or brand-color debugging. |
| `references/design-system.md` | Modifying the template or justifying a visual choice. |
| `references/narrative-voice.md` | Writing prose the recipe didn't produce. |
| `references/pptx-export.md` | User explicitly requested PPTX. |
| `references/agency-multi-brand.md` | Agency role in welcome flow, or multi-client workflow. |
| `templates/report-shell.html` | Injecting the summary (READ once; never regenerate). |
| `examples/sample-monthly-review.html` | Debugging an HTML rendering issue. |

If a reference isn't clearly needed, skip it. Every extra file loaded is tokens spent and latency added.

## Output conventions

- HTML → `/mnt/user-data/outputs/{report-name}-{YYYY-MM-DD}.html`
- PDF alongside when requested
- PPTX alongside when requested (see `references/pptx-export.md`)
- Present via `present_files` so user can download
- Modes (Q&A, custom builder, welcome) don't save files — answers are inline
- Utilities output inline code blocks for copy/paste
