# Design System

This file defines the visual language of every UTM Grabber attribution report. The HTML template (`templates/report-shell.html`) already implements everything here — you should rarely have to touch CSS directly. Load this file only if you need to understand *why* the template looks the way it does, or if you're adapting it for an agency white-label use case.

## The core principle

**The design never changes based on the data.** Customer A's report and customer B's report must be visually indistinguishable except for the numbers and the cover-page brand. This consistency is the reason the report feels expensive — every customer gets the same designer output.

## Brand palette

The template uses five CSS custom properties as the entire brand system. Swap these and the whole report re-themes.

```css
:root {
  --b-primary:   #0160BF;  /* UTM Grabber blue — headlines, accents, bars */
  --b-ink:       #0B1B34;  /* near-black navy — body text, cover background */
  --b-accent:    #2E90FA;  /* bright blue — callouts, "insight" highlights, vertical rule */
  --b-muted:     #64748B;  /* slate — secondary text, axis labels */
  --b-surface:   #F5F7FB;  /* off-white — card backgrounds, chart backgrounds */
}
```

### Why these choices

- `--b-primary` is UTM Grabber's canonical blue, already used across utmgrabber.com and the plugin admin.
- `--b-ink` is warmer than pure black — prevents the "harsh terminal" feel on printed PDFs.
- `--b-accent` is a brighter sibling of primary — used sparingly for "read this" moments (callouts, insight-card rule, delta highlights). Use it for no more than one element per slide.
- `--b-muted` is the WCAG-AA grey for secondary text — legible but clearly subordinate.
- `--b-surface` is the card fill — keeps cards distinct from the page while staying print-safe.

### Chart palette (ordered)

When a chart needs multiple colours, use this exact sequence:

```
1. #0160BF  (primary — deep brand blue)
2. #2E90FA  (accent — bright brand blue)
3. #FFC857  (warm yellow)
4. #30B47A  (green)
5. #6FB1E8  (pale blue)
6. #F59E0B  (amber)
7. #0B1B34  (ink)
```

This matches the order returned by `scripts/chart_renderer.py::_brand_palette()` and the template's `getPalette()` in `report-shell.html`.

Don't skip around. A bar chart with four items uses the first four, in order.

## Typography

Two font families — one serif for titles, one sans for everything else. Both are free and available on Google Fonts.

```css
--font-display: "Instrument Serif", "Source Serif Pro", Georgia, serif;
--font-body:    "Geist", "Inter", system-ui, -apple-system, sans-serif;
--font-mono:    "Geist Mono", "JetBrains Mono", monospace;
```

### When to use which

| Use | Font |
|---|---|
| Page titles, section headlines, the "hero" number on cards | `--font-display` |
| All body copy, labels, bullet text, chart axis labels | `--font-body` |
| Numbers in tables, UTM field names, codes, dates in small footnotes | `--font-mono` |

Never mix two display fonts. Never set body copy in the serif — it looks "essay", not "report".

### Scale

```
Cover title      : 72px / 78 / tight
Slide title      : 38px / 44 / tight
Section eyebrow  : 14px / 1.2 / uppercase, letter-spacing 0.08em
Hero number      : 72px / 1 / bold / display font
Body copy        : 16px / 24 / normal / body font
Caption / footer : 12px / 16 / body font, muted colour
Mono data        : 14px / 18 / mono font
```

## Layout

Reports are built as **slides** — 16:9 pages, each 1600×900 viewport units. This matches the PPTX/PDF output naturally and prints to a 1-up PDF beautifully.

Page structure:

```
┌─────────────────────────────────────────┐
│  [accent-blue vertical rule, 10px wide] │
│                                         │
│   EYEBROW · SECTION NAME                │  ← eyebrow: --b-primary, 14px, uppercase
│                                         │
│   Slide Headline in Serif               │  ← display, 38px, --b-ink on surface
│                                         │
│   ┌───────────┐  ┌────────────────────┐ │
│   │           │  │                    │ │
│   │   CHART   │  │   INSIGHT CARD    │ │
│   │           │  │                    │ │
│   └───────────┘  └────────────────────┘ │
│                                         │
│   data source · footer line · page no.  │  ← muted, 12px
└─────────────────────────────────────────┘
```

Margins: 64px on all sides. Gutter between columns: 48px.

## Standard slide types

All eight slide types are pre-built in the template. You just fill in the slots:

1. **Cover** — ink background, accent rule, logo top-left, big title, customer/date block bottom-left, "Prepared by UTM Grabber" bottom-right.
2. **KPI strip** — 4 stat cards across the top + headline insight box below. For executive summaries.
3. **Chart + insight** — chart on the left 60%, insight card on the right 40%.
4. **Full-width chart** — chart fills the page, three stat cards below.
5. **Two-column profile** — donut or pie on the left, profile card (bars + tags) on the right.
6. **Comparison bars** — grouped or stacked bars, insight card on the right.
7. **Recommendations** — 4 numbered cards in a 2×2 grid.
8. **Closing** — ink background, "Thank you" + data source line.

The monthly review uses all eight. Most other reports use 3–5.

## Rules and anti-rules

- **Never** use more than one `--b-accent` element per slide. It's the attention colour.
- **Never** set chart bars to transparent fills. Print PDFs handle solid fills better.
- **Never** use emoji in reports. They render inconsistently across PDF engines.
- **Always** set a white background on chart containers — never transparent — so PDFs render cleanly.
- **Always** include the data-source footer on every page, not just the closing slide.
- **Always** left-align body copy. Justified text produces ugly rivers in narrow columns.

## White-labeling for agencies

An agency wants to send their client a report with the agency's brand, not UTM Grabber's. Two levers:

1. **Swap the five CSS custom properties** — entire brand re-themes instantly.
2. **Replace the logo** in the cover slide — the template has a `<img data-slot="brand-logo">` attribute for direct substitution.

The footer line stays as `UTM Grabber · {domain}` — this is a data-integrity signature, not a brand claim. Customers need to know the data came from UTM Grabber. For agency co-branding, the footer can read `Powered by UTM Grabber · {domain}` but the attribution to UTM Grabber must remain visible.

## Responsive and print

The template is optimized for 1600×900 viewport. It also:

- Scales gracefully in a desktop browser from 1280px up.
- Renders cleanly to PDF via WeasyPrint (see the pdf skill) at 16:9 landscape A4.
- Is NOT designed for mobile phones. That's intentional — attribution reports are a desktop/PDF artifact. Mobile users should receive the exec summary as an email snippet, not this report.

## Accessibility

Even though these reports are primarily PDF artifacts, accessibility matters — CFOs reading on screen readers, colour-blind marketers, printed versions photocopied to grayscale.

### Contrast
- All body text meets WCAG-AA (4.5:1) against its background. `--b-ink` on `--b-paper` clears 16:1.
- The muted grey `--b-muted` #64748B on `--b-surface` #F5F7FB clears 4.6:1. Don't muted-grey on white without testing.
- Delta pills use both colour AND symbols (`+`, `−`, `flat`) so colour-blind readers aren't dependent on hue.

### Charts
- Every chart should be legible in grayscale. Bar rankings use the ordered chart palette which has distinct lightness values — prints correctly even when colour is stripped.
- Never rely on colour alone to distinguish categories — also use position, order, or label.

### Semantics
- Slide headlines are `<h1>` / `<h2>` in the HTML. Don't use heading tags for visual styling only.
- Chart containers include `aria-label` attributes describing the chart for screen readers.
- Every chart is followed by an insight card that describes the chart in prose — screen readers and grayscale printouts both get the story.

### Alt text pattern for chart containers

```html
<div class="chart-container" role="img" aria-label="Channel mix donut chart: Paid 50%, Organic 18%, Direct 12%, Social 10%, Referral 10%. Total 500 leads.">
```

The aria-label should include the key numbers, not just the chart type.
