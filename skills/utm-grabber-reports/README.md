# UTM Grabber Attribution Reports

**Ask your UTM Grabber data anything. Get designer-quality reports, specific answers, or ready-to-paste UTM URLs back in seconds.**

This is a Claude Skill that turns your live WordPress form data into branded attribution reports, conversational answers, forecasts, and tagged campaign URLs. It runs on Claude (Pro, Max, or Team) and pulls data directly from your own UTM Grabber site via the UTM Grabber MCP server.

Nothing is stored on our servers. Nothing is sent to anyone else. Your data stays between your WordPress site and your Claude.

## What you get

Install once. From then on, in any Claude conversation, you can:

### Run reports

- "Run my monthly attribution report"
- "Audit my UTM tags"
- "Give me a deep dive on the Q1 Reactivation campaign"
- "Show me my landing page performance"
- "Forecast next week's lead volume"

### Ask specific questions

- "How many LinkedIn leads last week?"
- "What was my top source yesterday?"
- "Which campaign had the most HubSpot leads?"
- "Did Facebook beat Google this month?"

### Generate tagged URLs

- "Generate UTMs for a new LinkedIn spring demo campaign with 3 variants"
- "Help me tag a newsletter link"

### Or use shortcuts

- `/monthly`, `/weekly`, `/audit`, `/campaigns`, `/forecast`, `/help`
- `/ask [question]`, `/build [spec]`, `/utm [campaign details]`

## The full report catalog

| Report | What it answers |
|---|---|
| **Monthly Performance Review** | Full deck — channel mix, top sources, campaigns, volume trend, lead profile, multi-touch, recommendations. |
| **Weekly Executive Summary** | One-pager for leadership — the week's headline number, top source, biggest shift. |
| **Top Campaign Leaderboard** | Monday-morning scan. Every campaign ranked with trend icons. No narrative. |
| **Campaign Deep Dive** | Everything about one campaign — sources, lead profile, verdict (scale / refresh / sunset). |
| **UTM Hygiene Audit** | Exactly which pages and entries are missing tags, ranked by fix priority. |
| **Paid vs Organic** | How your channels compare — volume, quality, first-touch vs last-touch. |
| **Source-to-CRM Mapping** | For each CRM, which UTM sources drive those leads. |
| **Lead Quality Scorer** | Ranks new leads by attribution + intent signals. For sales prioritization. |
| **Lead Profile Enrichment** | Single-person dossier — every touch, every UTM, sales-angle bullets. |
| **Anomaly Detector** | Surfaces unusual shifts — spikes, drops, new or disappearing sources. |
| **Agency Client Rollup** | Multi-site view for agencies running UTM Grabber across many clients. |
| **Form Performance** | Which forms on your site convert best, which are spam-heavy, which are dormant. |
| **Landing Page Performance** | Which landing pages convert and which are leaking attribution. |
| **Ad Creative Performance** | Which `utm_content` variants drive the best leads, with fatigue detection. |
| **Keyword Performance** | Which paid-search `utm_term` values drive quality leads, with intent classification. |
| **Predictive Forecast** | Next week's and next month's projected lead volume with confidence bands. |
| **Budget Simulator** | What-if modeling — shift spend between channels and see projected outcomes. |

## Plus three modes and two utilities

- **Conversational Q&A** — specific questions get specific answers, inline, no deck.
- **Custom Report Builder** — describe a unique report in plain English, get a custom deck.
- **Prompt Shortcuts** — slash commands for power users who run the same reports routinely.
- **UTM Template Generator** — generates copy-paste UTM URLs using your existing naming conventions pulled from your live data.
- **Brand Onboarding** — 10-second setup that auto-detects your logo and brand colors from your website. Every future report uses your branding automatically. Agencies can maintain one profile per client and switch with `/brand switch [client]`.

## What you need

1. A WordPress site running **UTM Grabber v3** or later.
2. An active **UTM Grabber MCP access code** (found under **Settings → UTM Grabber → AI & MCP**).
3. A **Claude account** (Pro, Max, or Team).

## Setup (one time, ~90 seconds)

### Step 1. Connect your site to Claude

1. In Claude, go to **Settings → Connectors → Add custom connector**.
2. Name: `UTM Grabber`
3. URL: `https://api.utmgrabber.com/http/mcp/utmgrabber-report`
4. Authentication: paste your access code from WordPress.

### Step 2. Install the skill

1. Download `utm-grabber-reports.skill` from your UTM Grabber account.
2. In Claude, go to **Settings → Capabilities → Skills → Upload skill**.
3. Choose the `.skill` file. Done.

### Step 3. Try it

> Run my monthly attribution report.

Or:

> /weekly

Claude pulls your data, writes the insights, renders a branded HTML + PDF.

## What's new in this release

- **Period-over-period deltas on every metric.** Every number comes with `+12% vs last 30 days` context.
- **Paid marketer depth.** Landing page, ad creative, and keyword reports for PPC managers.
- **Predictive forecasting.** Budget-grade next-week and next-month projections.
- **Conversational Q&A mode.** Ask a question, get an answer. No deck required.
- **UTM Template Generator.** Stops attribution leaks at the source by generating correctly-styled URLs based on your real data.
- **Accessibility.** WCAG-AA colors, grayscale-legible charts, screen reader support.

## Want to customise?

The skill is a folder of markdown and HTML. If you're technical, you can:

- Change brand colours in `templates/report-shell.html` — swap 5 CSS variables, the whole brand cascades.
- Adjust narrative voice in `references/narrative-voice.md`.
- Add your own report by copying any file in `reports/` as a starting point.

For agencies white-labelling reports for clients, the entire brand swaps with 5 CSS variables. See `references/design-system.md`.

## Privacy and data

- Your WordPress data flows directly from your site into your Claude conversation — never through Anthropic's or UTM Grabber's servers for storage.
- The MCP access code is rotatable from your WordPress admin at any time.
- Nothing is cached between sessions — every report is generated fresh.

## Support

- Docs: https://docs.utmgrabber.com
- Email: support@utmgrabber.com
- Live chat: utmgrabber.com
