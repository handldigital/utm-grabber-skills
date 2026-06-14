# Brand Onboarding

Captures the customer's brand identity once, saves it to Claude's memory, and uses it to theme every future report. Also handles the `/brand` slash command for edits, switches, and resets.

Load this file whenever the customer is setting up branding for the first time, changing branding, or when an agency user is switching client brand profiles.

## The first-run flow

Triggered automatically the first time a customer asks for any report and no brand profile is saved.

Write short intro:

> You haven't set up branding yet — reports will use UTM Grabber's default theme. Want to personalize them? The fastest way is auto-detect from your website, but there are manual options too.

Then call:

```
ask_user_input_v0({
  "questions": [
    {
      "question": "How do you want to set up your brand?",
      "type": "single_select",
      "options": [
        "Auto-detect from my website",
        "Quick setup (2 colors)",
        "Advanced (all 5 colors)",
        "Skip for now"
      ]
    }
  ]
})
```

Route each choice into the corresponding path below.

If they tapped "Auto-detect from my website", ask for the URL as free text (button not applicable here):

> Paste your website URL and I'll detect your brand in about 10 seconds.

If the user pastes a URL:

1. Use `web_fetch` to retrieve the homepage HTML.
2. Parse for:
   - `<meta property="og:image">` — logo candidate
   - `<meta property="og:site_name">` or `<title>` — company name
   - `<meta name="theme-color">` — primary color hint
   - `<link rel="icon">` or favicon.ico — logo fallback
   - First `<img>` in `<header>` or class containing "logo" — logo fallback
3. **Extract colors for all 5 template variables.** Don't stop at primary. Try to identify a plausible value for each role:

   | Variable | What to look for |
   |---|---|
   | `primary` | The most-used brand color: theme-color meta, logo fill, gradient start, CSS `--primary`, `--brand`, `--color-primary`, CTA button backgrounds |
   | `accent` | The second brand color: gradient end-stop, secondary CTA, CSS `--secondary`, `--accent`, `--highlight`, callout backgrounds |
   | `ink` | Dominant body text color or dark header background. Look at computed `color` on `<body>` or `<h1>`. Usually near-black or deep navy; some brands use deep green, charcoal, or warm dark brown |
   | `muted` | Secondary / caption text color. Often the second most common text color. Usually mid-grey, but brands use sepia, desaturated versions of their primary, etc. |
   | `surface` | Card / section background color. Look for the most common "section" background that isn't pure white. Often off-white, cream, or a very-light tint of the primary |

4. Rank primary and accent by usage frequency; skip pure whites/blacks/greys unless the brand is genuinely monochrome.
5. For the three neutrals (`ink`, `muted`, `surface`): if detection is uncertain, use the UTM Grabber defaults (`#0B1B34`, `#64748B`, `#F5F7FB`). Don't force unusual neutrals onto a brand that doesn't have them — that creates ugly combinations.
6. Show the customer all detected colors with roles in a plain-text message, then use a button set for confirmation:

Show:

> Here's what I detected from acme-analytics.example:
>
> - **Company:** Acme Analytics
> - **Logo:** [url]
> - **Primary:** `#0E8C6B` — drives headlines, bars, stat numbers
> - **Accent:** `#5DBFA0` — drives callouts, rules, delta pills
> - **Ink / muted / surface:** using UTM Grabber defaults (your site didn't have distinctive values)

Then call:

```
ask_user_input_v0({
  "questions": [
    {
      "question": "Does this look right?",
      "type": "single_select",
      "options": [
        "Yes, save it",
        "Tweak the colors",
        "Customize all 5 colors",
        "Skip and use defaults"
      ]
    }
  ]
})
```

If they pick "Tweak the colors", ask via free text: "Which one should change? (e.g., 'primary to #FF0000')".
If they pick "Customize all 5 colors", enter the advanced path below.
If they say yes, save to memory via `memory_user_edits` as the `[default]` profile with all 5 color fields populated. Continue with their original report request.

1. Use `web_fetch` to retrieve the homepage HTML.
2. Parse for:
   - `<meta property="og:image">` — logo candidate
   - `<meta property="og:site_name">` or `<title>` — company name
   - `<meta name="theme-color">` — primary color hint
   - `<link rel="icon">` or favicon.ico — logo fallback
   - First `<img>` in `<header>` or class containing "logo" — logo fallback
3. **Extract colors for all 5 template variables.** Don't stop at primary. Try to identify a plausible value for each role:

   | Variable | What to look for |
   |---|---|
   | `primary` | The most-used brand color: theme-color meta, logo fill, gradient start, CSS `--primary`, `--brand`, `--color-primary`, CTA button backgrounds |
   | `accent` | The second brand color: gradient end-stop, secondary CTA, CSS `--secondary`, `--accent`, `--highlight`, callout backgrounds |
   | `ink` | Dominant body text color or dark header background. Look at computed `color` on `<body>` or `<h1>`. Usually near-black or deep navy; some brands use deep green, charcoal, or warm dark brown |
   | `muted` | Secondary / caption text color. Often the second most common text color. Usually mid-grey, but brands use sepia, desaturated versions of their primary, etc. |
   | `surface` | Card / section background color. Look for the most common "section" background that isn't pure white. Often off-white, cream, or a very-light tint of the primary |

4. Rank primary and accent by usage frequency; skip pure whites/blacks/greys unless the brand is genuinely monochrome.
5. For the three neutrals (`ink`, `muted`, `surface`): if detection is uncertain, use the UTM Grabber defaults (`#0B1B34`, `#64748B`, `#F5F7FB`). Don't force unusual neutrals onto a brand that doesn't have them — that creates ugly combinations.
6. Show the customer all detected colors with roles and ask for confirmation.

Example confirmation message (for a brand with strong identity across all 5 colors):

> Here's what I detected from acme-analytics.example:
>
> - **Company:** Acme Analytics
> - **Logo:** https://acme-analytics.example/assets/logo.svg
> - **Primary color:** `#0E8C6B` — hot pink, from the logo gradient start. Drives headlines, chart bars, and stat numbers.
> - **Accent color:** `#5DBFA0` — light pink, from the logo gradient end. Drives callouts, rules, and delta pills.
> - **Ink:** `#0B1F1A` — deep purple, used for body text. (If you'd prefer standard navy, say "use default ink".)
> - **Muted:** `#64748B` — UTM Grabber default grey (I didn't find a distinctive secondary text color on the site).
> - **Surface:** `#F0F8F5` — light pink-tinted background, used for section backgrounds.
>
> Reply "yes" to save, or tell me what to change (e.g., "use default ink" or "accent should be #000").

Example confirmation when the site only yields brand colors:

> Here's what I detected from acme.com:
>
> - **Company:** Acme Corp
> - **Logo:** https://acme.com/logo.svg
> - **Primary color:** `#FF4136` (red)
> - **Accent color:** `#FFD700` (yellow, from the CTA button)
> - **Ink, muted, surface:** using UTM Grabber defaults — your site didn't have distinctive values for these.
>
> Reply "yes" to save, or say "customize all 5 colors" if you want to override the neutrals too.

This way, customers with strong brand systems get all 5 captured, and customers with only 1-2 brand colors don't get weird results — defaults fill the gaps.

If they say yes, save to memory via `memory_user_edits` as the `[default]` profile with all 5 color fields populated (even when some come from defaults — makes the profile fully explicit and agency-portable). Continue with their original report request.

### Quick setup (2 colors)

If they tapped "Quick setup (2 colors)", ask in one free-text message:

> Quick setup — give me three things:
>
> - Company name (e.g., "Acme Corp")
> - Logo: a URL, an uploaded image, or "use my company name as text"
> - 1–2 hex colors for primary and accent (e.g., `#0160BF` and `#2E90FA`), or "default blue" for UTM Grabber's

Take their answers. If they give one color, use it for primary and accent both. If two, first is primary / second is accent. Default the other 3 color variables (ink, muted, surface). Preview and save.

### Advanced (all 5 colors)

If they tapped "Advanced" or chose the upgrade path, walk through the 5 template variables one at a time. Show the default alongside each so they know what they're replacing:

> Five color variables drive the whole report. Paste a hex code for each, or say "default" to keep the UTM Grabber value:
>
> - **Primary** — headlines, chart bars, big stat numbers. Default: `#0160BF` (UTM Grabber blue).
> - **Accent** — callouts, rules, delta pills, highlights. Default: `#2E90FA` (UTM Grabber bright blue).
> - **Ink** — body text and the cover slide background. Default: `#0B1B34` (deep navy). Change this for unusual dark tones — deep greens, charcoals, warm browns.
> - **Muted** — secondary text, captions, axis labels. Default: `#64748B` (slate grey). Change this if your brand uses sepia, desaturated primary, or similar.
> - **Surface** — card and section backgrounds. Default: `#F5F7FB` (off-white). Change to cream, light tint-of-primary, or similar if your brand has a distinctive neutral.

Take the answers. Default any color they skip. Show the full 5-color preview before saving:

> Here's your full brand:
>
> - Primary: `#FF4136` (red, custom)
> - Accent: `#FFD700` (yellow, custom)
> - Ink: `#0B1B34` (default navy)
> - Muted: `#64748B` (default grey)
> - Surface: `#F5F7FB` (default off-white)
>
> Save?

### Quick sanity check (apply to both paths)

Before saving any profile, validate:

- All 5 color values are valid 6-char hex codes (with or without `#`). Normalize to `#XXXXXX` lowercase/uppercase consistently.
- Primary and accent aren't identical (if they are, warn: "Primary and accent are the same color — reports will look flat. Want to pick a second color?").
- Ink and surface have sufficient contrast for readable text (at least 4.5:1 ratio per WCAG-AA). If they don't, warn: "Your ink color on your surface color is hard to read. Consider a darker ink."

These checks prevent the most common "my report looks weird" failure modes.

### Option C: Skip

If they say "skip" or ignore the prompt, save a minimal profile:

```json
{
  "profile_id": "default",
  "company_name": "{site domain from MCP}",
  "logo": {"type": "text", "value": "{site domain}"},
  "colors": {"primary": "#0160BF"},
  "footer_style": "utm-grabber"
}
```

Then carry on with the report they originally asked for.

Every time they run a report after a skip, include a small footer note:

> *Tip: run `/brand setup` to customize how your reports look.*

## The `/brand` slash command

Power-user command for managing brand profiles. Supports these forms:

### `/brand` (no args)
Show the current active profile and list any other saved profiles.

> **Active brand: Acme Corp** (`acme-corp`)
> Primary: `#FF4136` · Logo: acme.com/logo.svg · Footer: co-branded
>
> **Other saved profiles (3):**
> - `peak-health` (Peak Health Co)
> - `bright-media` (Bright Media)
> - `default` (UTM Grabber default)
>
> Commands: `/brand setup` · `/brand switch [id]` · `/brand edit` · `/brand reset`

### `/brand setup`
Run the onboarding flow again to create a new profile or replace the default.

### `/brand edit`
Open an inline editor for the active profile. Show the current values for all 5 colors + logo + name + footer style, and let the user change any field.

> Current profile: **UTM Grabber** (`default`)
>
> - Company: UTM Grabber
> - Logo: `text · "UTM Grabber"`
> - Primary: `#0160BF`
> - Accent: `#2E90FA`
> - Ink: `#0B1B34`
> - Muted: `#64748B`
> - Surface: `#F5F7FB`
> - Footer: `utm-grabber`
>
> What do you want to change? Say things like "primary to `#FF0000`" or "logo to [URL]" or "footer to co-branded".

Accept natural-language edits. Multiple changes in one message are fine:

> primary to #FF4136 and accent to #FFD700

Validate hex codes and contrast (see sanity check above). Confirm and save.

### `/brand switch [profile_id]`
Switch the active profile. For agencies this is the critical command.

> Switched active brand to **Peak Health Co** (`peak-health`). Next report will use their colors and logo.

If the profile_id doesn't exist, show the list of available profiles.

### `/brand new [profile_id] [website_url]`
Create a new brand profile (agency use case). Runs auto-detection on the website and saves as a new profile without replacing the active one.

> Created new profile **bright-media** from brightmedia.com. Not yet active — run `/brand switch bright-media` to use it.

### `/brand remove [profile_id]`
Delete a saved profile. Always confirm before removing:

> Remove **peak-health** profile? This cannot be undone. Reply "yes" to confirm.

### `/brand reset`
Remove ALL saved profiles and restore UTM Grabber defaults. Confirmation required.

## Agency workflow

An agency running 10 clients will typically:

1. On initial setup, create one profile per client:
   ```
   /brand new acme-corp acme.com
   /brand new peak-health peakhealth.co
   /brand new bright-media brightmedia.com
   ```
2. At the start of each client session, switch: `/brand switch acme-corp`
3. Run reports normally — every report uses Acme's branding.
4. Switch to the next client, repeat.

For an agency running the **Agency Client Rollup** report specifically, the rollup uses the agency's OWN brand (not a single client's). Typically the agency sets up `[agency-self]` as a distinct profile and switches to it before running rollups.

See `references/agency-multi-brand.md` for the full agency workflow including multi-profile rollup logic.

## Memory storage format

Each profile is saved as a separate memory entry via `memory_user_edits`:

```
UTM Grabber brand profile [default]: {"profile_id":"default","company_name":...}
UTM Grabber brand profile [acme-corp]: {...}
UTM Grabber brand profile [peak-health]: {...}
UTM Grabber active profile: acme-corp
```

The `active profile` line is a single-value pointer. When running a report, check this line to find which profile_id to load.

## File export (backup + portability)

Every time a profile is created or edited, also save a JSON file to `/mnt/user-data/outputs/brand-{profile_id}.json`. This lets the customer download the profile file as a backup OR transfer profiles between Claude accounts/workspaces. Call `present_files` with it.

Profiles can also be imported:

> Paste a brand profile JSON or upload a `.json` file, and I'll add it.

Parse uploaded JSON files, validate against the schema, save to memory.

## Auto-detection accuracy

`web_fetch`-based auto-detection isn't perfect. If it fails or produces weird results (e.g., detected "primary color" is actually a footer accent), tell the user and fall back to manual entry:

> I fetched acme.com but couldn't confidently detect a primary color. Can you paste one? Or I'll use UTM Grabber's default for now.

Never silently ship a bad auto-detection. The customer should always see and confirm what was detected before it's saved.

## What every saved profile contains

Every profile saved to memory stores all 5 color variables explicitly — even when some come from UTM Grabber defaults. This makes profiles fully portable (an agency can export a client profile and re-import it anywhere without needing the skill to re-derive defaults) and transparent (the customer can see exactly what colors their reports will use).

To render a report, the skill needs at minimum:
1. `company_name` (falls back to site domain if missing)
2. `logo` (falls back to `company_name` as a text wordmark)
3. `colors.primary` (falls back to UTM Grabber blue)
4. `colors.accent` (falls back to UTM Grabber bright blue `#2E90FA`)
5. `colors.ink`, `colors.muted`, `colors.surface` (fall back to UTM Grabber defaults)

The skill should NEVER block a report on missing branding — always render with fallbacks and invite the customer to run `/brand setup` afterward.
