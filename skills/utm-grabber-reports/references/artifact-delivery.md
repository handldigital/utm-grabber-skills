# Live links: a report as a claude.ai link that stays current

**Where this works:** sessions that have the Artifact tool, which means the Claude desktop app and Claude Code, signed in to claude.ai on a Pro, Max, Team or Enterprise plan. A claude.ai chat can't publish these links, so deliver the HTML file there as usual. If the Artifact tool isn't in your tool list, don't mention links.

## What the customer gets

A private claude.ai link to the dashboard: the HTML report in its dashboard layout, with the same look and numbers. They can bookmark it and share it from the Share button on the page, either with people in their organization or as a public link anyone can open. On Team and Enterprise plans, an Owner turns public links on first. Every refresh republishes to the same link, and pages that are already open update in place.

## When to offer it

- After an HTML report, when the Artifact tool is available, add one follow-up option: "Want this as a link you can share, that I keep up to date?"
- Do it right away when the user asks for a link, a shareable or client dashboard, "keep it updated", "live", "every Monday" or "on autopilot".

## Publish

1. Build the page without its document skeleton. Any path ending in `.artifact.html` does this:
   ```python
   build_report(summary, os.path.expanduser("~/UTM Grabber dashboards/full-funnel-acme.com.artifact.html"), theme=theme)
   ```
   Keep one stable file per report and site, so later refreshes in this conversation reuse it.
2. Publish the file with the Artifact tool. Use `icon` "chart" and a one-sentence `description` that names the report and the site.
3. Save the link in memory: "UTM Grabber dashboard link: full-funnel for acme.com, theme studio, last 30 days: <url>".
4. Tell the customer in two sentences at most: here's the link, it's private until they share it, and you can refresh it.

PowerPoint decks can't be attached to a link, so send the deck as a file.

## Refresh ("update my dashboard", scheduled runs)

1. Pull the data again with the same window rule. A rolling "last 30 days" moves forward. For a named month, ask before you switch to the next one.
2. Rebuild the same `.artifact.html` file with the same report and theme.
3. Publish to the saved link. In the same conversation, publish the same file path again. In a new conversation, read the saved link with the Artifact tool's `read` action first, then publish with that `url`.

The footer date shows when the dashboard was last updated.

## Automatic refresh

When the customer asks for a schedule, offer a scheduled task in the Claude desktop app, and create it only after they say yes. Run it weekly or daily with this prompt: "Refresh my UTM Grabber <report> dashboard for <domain> at <url>: pull the <window>, rebuild it in the <theme> look, and republish to the same link." Desktop scheduled tasks run while the Claude app is open and the computer is awake. Tell the customer that in one plain sentence.

## Live dashboard: fresh numbers every time it opens

A dedicated page that pulls leads from the viewer's own UTM Grabber connection each time it opens, and every 15 minutes while it stays open. It shows leads for Today, 7, 30 or 90 days, the change against the period before, leads per day, channel mix, top sources, top campaigns, the newest leads and top landing pages. The 30 reports stay as refreshable links; this page is the always-current view.

**Who sees live numbers:** people signed in to claude.ai with UTM Grabber connected, which means the site owner and their team. Everyone else, including anyone who opens a public link without signing in, sees the snapshot saved when you built the page. The page says which one they're looking at.

1. Pull the last 60 days of entries for the forms the customer uses (all pages), then load them with `helpers.load_entries`. That covers the 7 and 30 day views and their comparisons before live data arrives.
2. Use the connector you just pulled this site's data from. There is no default name: the page finds each viewer's connection by its display name, the owner's included, and a customer with several sites has one connector per site, each with its own name. Its tools are named `mcp__<connector>__get_entries`; `<connector>` is its ID (for example `claude_ai_Utmgrabber_MCP`). Your first guess at the display name is that ID without `claude_ai_` and with spaces for underscores ("Utmgrabber MCP").
3. Build the page with that display name:
   ```python
   from engine.live import build_live
   build_live(entries, os.path.expanduser("~/UTM Grabber dashboards/live-acme.com.artifact.html"),
              connector="Utmgrabber MCP", form_plugin="gravity-form", form_ids=[1, 3], window="7",
              theme=theme, brand_profile=brand, customer_domain="acme.com", form_label="Gravity Forms")
   ```
   `form_plugin` and `form_ids` are the same values the report pulled. `build_live` refuses to build a live page without `connector`.
4. Publish the file with the Artifact tool, passing the connector's **ID** as the server: `capabilities={"mcp": {"servers": [{"server": "claude_ai_Utmgrabber_MCP", "tools": ["get_entries"]}]}}`. That lets the page call one read-only tool, `get_entries`, on the viewer's own connection; each viewer approves it once. The publish result names the exact display name the ID resolved to. If it differs from the name you built with, build again with that name and publish the same file again. Never publish with a guessed display name in `capabilities`: a name that matches no connector is accepted, and the page then shows saved numbers only.
5. Save it in memory with the connector: "UTM Grabber live dashboard for acme.com: connector "Utmgrabber MCP", gravity-form forms 1, 3: <url>". Refreshes reuse that connector name; for another site, use that site's connector.
6. Tell the customer: "Here's your live dashboard. It pulls fresh numbers from your UTM Grabber connection every time you open it. People you share it with see live numbers when they're signed in to claude.ai with UTM Grabber connected. Everyone else sees today's numbers."

The page keeps only dates and tracking fields, never names, emails or other personal details. If the site's plan refuses a window (for example more than 30 days on a free plan), the page shows the site's own message with its link. For sales demos, `build_live(..., demo=True)` makes a clearly labeled sample page that simulates the connection and calls nothing.

## Customer phrasing

- "Here's your dashboard link. It's private to you until you share it from the Share button on the page."
- "Want me to refresh it every Monday morning, so the link always shows last week's numbers?"

Say "link" and "dashboard". Don't say publish, MCP or connector. Say "artifact" only if the customer uses the word first.
