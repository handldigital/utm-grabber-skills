# Brand Profile

The brand profile is the customer's (or the customer's client's) visual identity: name, logo, colors, and footer preferences. It's the thing that transforms every report from "UTM Grabber generic" into "looks like my company made this."

Load this file when onboarding a new customer, handling a `/brand` slash command, or when an agency user is switching client profiles.

## The profile schema

One brand profile looks like this:

```json
{
  "profile_id": "acme",
  "company_name": "Acme Analytics",
  "logo": {
    "type": "url",
    "value": "https://acme-analytics.example/assets/logo.svg"
  },
  "website": "https://acme-analytics.example",
  "colors": {
    "primary": "#0E8C6B",
    "accent":  "#5DBFA0",
    "ink":     "#1A1A2E",
    "muted":   "#64748B",
    "surface": "#F8F9FA"
  },
  "footer_style": "co-branded",
  "notes": "Gradient brand — primary (deep green) drives bars and headlines; accent (mint green) drives callouts and highlights.",
  "created_at": "2026-04-19T10:30:00Z",
  "last_used":  "2026-04-19T10:30:00Z"
}
```

### Field definitions

| Field | Required | Notes |
|---|---|---|
| `profile_id` | yes | slug, URL-safe, unique per customer / per client. Generated from company_name if not provided. |
| `company_name` | yes | Shown on cover slide. |
| `logo.type` | yes | `url` (remote image) / `upload` (base64-inlined) / `text` (wordmark fallback) |
| `logo.value` | yes | URL, base64 string, or the text to render as a wordmark |
| `website` | optional | Used for auto-detection and CTA links |
| `colors.primary` | yes | **The workhorse color.** Drives slide headlines, chart bars, stat numbers, primary CTAs. The one that shows up most across the deck. |
| `colors.accent` | recommended | **The attention color.** Drives callouts, the thin accent rule, insight card highlights. Best when distinct from primary (e.g., brand's secondary/CTA color, gradient end-stop, complementary hue). Defaults to `#2E90FA` (UTM Grabber bright blue) if omitted. |
| `colors.ink` | optional | Dark text / cover background. Default `#0B1B34`. |
| `colors.muted` | optional | Secondary text. Default `#64748B`. |
| `colors.surface` | optional | Background cards. Default `#F5F7FB`. |
| `footer_style` | optional | `client-branded` / `co-branded` / `utm-grabber` — controls footer attribution |
| `notes` | optional | Free text brand conventions. Flagged into voice decisions. |

### Primary vs accent: why both matter

A brand with only one color applied across the report looks monochromatic and dated. The template is designed around **two brand colors working together** — primary carries the majority of visual weight (bars, headlines, big numbers), while accent punctuates the insights (callout rules, delta pills for special cases, insight-card signature elements).

When the brand has an obvious two-color identity — a gradient logo, a primary + CTA color pairing, a brand style guide with "primary" and "secondary" — capture both. When the brand is genuinely single-color, the template uses the UTM Grabber default bright blue (`#2E90FA`) for accents, which sits well against most brand primaries.

### Footer styles explained

- **`client-branded`** — Footer reads `{company_name} · Attribution Report`. Used when the client never sees UTM Grabber's name. Agency use case.
- **`co-branded`** — Footer reads `{company_name} · Powered by UTM Grabber`. Agency + white-label with attribution. Recommended default.
- **`utm-grabber`** — Footer reads `UTM Grabber · {domain}`. For direct customers who want UTM Grabber's branding.

The data-source integrity line (`Data source: UTM Grabber · {domain}...`) is separate from the footer style and always appears — it's the audit trail, not branding.

## How it's stored

Brand profiles live in Claude's built-in memory via `memory_user_edits`. Each profile is one memory line:

```
UTM Grabber brand profile [acme-corp]: {json_blob}
UTM Grabber brand profile [peak-health]: {json_blob}
UTM Grabber brand profile [default]:    {json_blob}
```

The `[profile_id]` prefix lets agencies maintain dozens of client profiles side by side.

When a report runs:

1. Skill checks memory for brand profiles.
2. If user specified `/brand {profile_id}`, load that one.
3. If they didn't specify, load `[default]`.
4. If there's no profile at all, trigger onboarding flow.

## How it flows into the template

The report template (`templates/report-shell.html`) reads the brand profile at render time and overrides its default CSS variables.

**Technique:** The template has a `<style id="brand-overrides">` tag at the top. The JS renderer populates it with the profile's colors:

```javascript
const brand = reportData.meta.brand_profile;
document.getElementById('brand-overrides').textContent = `
  :root {
    --b-primary: ${brand.colors.primary};
    --b-ink:     ${brand.colors.ink || '#0B1B34'};
    --b-accent:  ${brand.colors.accent || '#2E90FA'};
    --b-muted:   ${brand.colors.muted || '#64748B'};
    --b-surface: ${brand.colors.surface || '#F5F7FB'};
  }
`;
```

The logo replaces the wordmark on the cover slide:

```javascript
if (brand.logo.type === 'url') {
  coverLogo.innerHTML = `<img src="${brand.logo.value}" alt="${brand.company_name}" style="max-height: 60px;">`;
} else if (brand.logo.type === 'upload') {
  coverLogo.innerHTML = `<img src="data:image/png;base64,${brand.logo.value}" style="max-height: 60px;">`;
} else {
  coverLogo.innerHTML = `<span class="brand-logo">${brand.logo.value}</span>`;
}
```

The footer string is computed from `footer_style` and the profile's company name.

## When to trigger onboarding

Trigger the brand onboarding flow (`utilities/brand-onboarding.md`) the first time either of these is true:

- The customer asks for ANY report and no brand profile exists in memory (`[default]` missing).
- The customer explicitly asks to set up branding (`"set up my brand"`, `/brand setup`).

Don't trigger onboarding if the customer is just running a Q&A or asking a one-off question — those work fine with default UTM Grabber branding.

## Fallback chain

If a report is running and the brand profile is partially missing:

- Missing `company_name` → use the site domain from MCP.
- Missing any color → use UTM Grabber default.
- Missing logo → use a text wordmark derived from `company_name`.
- Missing `footer_style` → default to `co-branded`.

The report must render even if the profile is empty. Branding is additive, not required.

## Privacy note

Brand profiles contain only publicly shareable data (company name, public logo URL, brand colors). No access codes, no passwords, no PII. Safe to persist in Claude memory.


## Theme (v0.9.5+, PPTX-only as of v0.9.10)

Brand profiles support an optional `theme` field controlling the visual palette **for PPTX output only**:

- `theme: "light"` (default) — white slide backgrounds, dark ink text, tinted two-tone cards with brand-color accents. Editorial magazine feel. Works best when charts and data density matter most. Used for all HTML and PDF output regardless of this setting.
- `theme: "gradient"` — dark diagonal gradient (ink → ink mixed with 35% brand primary at 45°) slide backgrounds, white text, dark brand-tinted two-tone cards, brand colors pop bright. More dramatic, better for executive projector decks. **PPTX only.** HTML and PDF ignore this setting and render in the light editorial style, since gradient backgrounds don't translate well to print or small screens.

```json
{
  "company_name": "Acme Analytics",
  "theme": "gradient",
  "colors": {
    "primary": "#0160BF",
    "accent": "#2E90FA",
    "ink": "#0B1B34",
    "muted": "#64748B",
    "surface": "#F5F7FB"
  }
}
```

The same recipe code produces both themes — switching is a one-line change in the brand profile. Charts stay on a white canvas in both modes (chart readability trumps theme consistency). Italic-accent and brand-rule conventions are identical across themes.

When setting up a brand with `/brand`, Claude should ask about theme preference. When in doubt, default to `"light"` — it's safer for mixed-audience decks.
