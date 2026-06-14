# Prompt Shortcuts

Fast-path triggers for power users. Short slash-prefixed commands that map directly to reports or modes without the skill having to interpret natural language.

Think terminal aliases, not magic. These exist so a marketer who runs the same report every Monday doesn't have to type "give me my weekly attribution report" — they just type `/weekly`.

## The shortcuts

Each shortcut shows expected duration against a typical site (~500 leads/month). High-volume sites run proportionally slower due to chunked pulling.

| Shortcut | Duration | Maps to |
|---|---|---|
| `/monthly` | ~15s | `reports/monthly-performance-review.md` |
| `/weekly` | ~10s | `reports/weekly-executive-summary.md` |
| `/audit` | ~15s | `reports/utm-hygiene-audit.md` |
| `/campaigns` | ~12s | `reports/top-campaign-leaderboard.md` |
| `/deepdive [name]` | ~15s | `reports/campaign-deep-dive.md` |
| `/paidvsorganic` | ~12s | `reports/paid-vs-organic.md` |
| `/crm` | ~10s | `reports/source-to-crm-mapping.md` |
| `/leads` | ~8s | `reports/lead-quality-scorer.md` |
| `/anomalies` | ~10s | `reports/anomaly-detector.md` |
| `/pages` | ~12s | `reports/landing-page-performance.md` |
| `/creative` | ~12s | `reports/ad-creative-performance.md` |
| `/keywords` | ~12s | `reports/keyword-performance.md` |
| `/forms` | ~12s | `reports/form-performance.md` |
| `/forecast` | ~12s | `reports/predictive-forecast.md` |
| `/simulate [scenario]` | ~15s | `reports/budget-simulator.md` |
| `/lead [email or name]` | ~8s | `reports/lead-profile-enrichment.md` |
| `/compare [X vs Y]` | ~15s | `reports/side-by-side-comparison.md` |
| `/rollup` | ~60-90s | `reports/agency-client-rollup.md` (many MCP calls) |
| `/ask [question]` | ~5s | `modes/conversational-qa.md` |
| `/build [spec]` | ~20-30s | `modes/custom-report-builder.md` |
| `/utm [context]` | instant | `utilities/utm-template-generator.md` |
| `/pptx` | ~30s | Export most recent report as PowerPoint |
| `/brand` | instant | Show active brand profile |
| `/brand setup` | ~15-30s | Run brand onboarding (with auto-detect) |
| `/brand switch [id]` | instant | Switch active brand profile |
| `/brand edit` | interactive | Edit current profile |
| `/brand new [id] [url]` | ~15s | Create new profile (auto-detects) |
| `/brand remove [id]` | instant | Delete a profile (confirmed) |
| `/brand export all` | ~5s | Export all profiles as JSON |
| `/brand reset` | instant | Remove all profiles (confirmed) |
| `/welcome` | instant | First-run guide |
| `/help` | instant | Lists all shortcuts |

## Using the durations

When acknowledging a shortcut, include the expected duration so the customer knows not to bail at the 12-second mark:

> Running your monthly review — ~15 seconds, pulling 30 days of data now.

For the Agency Client Rollup specifically (60-90 seconds), show progress every 20 seconds.

## How shortcuts work

Parse the leading token of the user's message:

```
if message.startswith("/"):
    parts = message.split(maxsplit=1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    route_to_shortcut(command, args)
```

If the command isn't recognized, don't fail — show the `/help` list and say "I didn't recognize that shortcut. Here's the list."

## Time-range modifiers

Shortcuts accept optional time modifiers after the command:

```
/monthly                     # default: last 30 days
/monthly last-60-days        # custom window
/monthly q1-2026             # specific quarter
/weekly last-week            # the 7 days before this week
```

Parse these modifiers as date ranges using the same logic from `references/mcp-usage.md`.

## Compound shortcuts

A few shortcuts take optional context:

```
/deepdive spring demo search          # campaign name
/deepdive "Q1 Reactivation"           # quoted for names with spaces
/ask which source drives the most hubspot leads
/build hubspot leads by campaign for q1
/utm launching spring demo on linkedin
```

## Discoverability

The `/help` command lists all shortcuts. Also, when the skill produces any report, include a small footer:

> Tip: Next time, just type `/monthly` to run this instantly.

This teaches users the shortcuts organically.

## Shortcuts are suggestions, not commands

Users can always skip shortcuts and use natural language. The skill handles both equally. Shortcuts just save keystrokes for people who've adopted them.
