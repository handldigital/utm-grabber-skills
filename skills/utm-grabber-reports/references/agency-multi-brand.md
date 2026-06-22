# Agency Multi-Brand Workflow

How agencies running UTM Grabber across many clients manage brand identity, switching, and rollups. This is a critical differentiator for the 44% of UTM Grabber customers who are agencies.

Load this file when the user mentions "clients", "agency", "white label", "rollup", or when they're creating their 2nd+ brand profile.

## The agency's attribution stack

A typical mid-size agency runs UTM Grabber on 10–50 client WordPress sites. Each client has:

- Their own WordPress site with the UTM Grabber plugin installed
- Their own MCP access code
- Their own brand (logo, colors, company name)
- Their own forms, campaigns, and reporting cadence

The agency maintains this stack centrally — one person (or a small team) runs reports across all clients every week or month. The skill has to make switching between clients effortless.

## Two structural decisions

### Decision 1: One brand profile per client, plus one for the agency itself.

```
Agency: "Vector Growth"
Clients:
  - acme-corp       (Acme Corp, red)
  - peak-health     (Peak Health, green)
  - bright-media    (Bright Media, navy)
  - urban-growth    (Urban Growth, orange)
  ...
Agency self:
  - vector-self     (Vector Growth, black)
```

`vector-self` is used only when the agency produces reports about their own work — typically the Agency Client Rollup report that shows performance across all clients.

### Decision 2: MCP connections are separate from brand profiles.

The MCP access code identifies which WordPress site to pull data from. The brand profile identifies how to style the resulting report. They're independent:

- One client could have two brands (parent co / subsidiary) using the same MCP.
- One MCP could be branded differently depending on report context.
- The agency's "self" profile uses no MCP — it's styling metadata only.

Always treat the MCP choice and the brand choice as separate decisions.

## The weekly workflow

Monday morning. Vector Growth's PM opens Claude.

### Step 1: Run rollups for the whole portfolio

```
/brand switch vector-self
Show me the weekly agency client rollup
```

The rollup report uses Vector Growth's black branding and iterates through every connected MCP, producing a portfolio view.

### Step 2: Deep dives per client

For each client that flagged anomalies or needs attention:

```
/brand switch acme-corp
/weekly
```

This switches to Acme's red branding. The weekly report pulls Acme's MCP data and renders in Acme's colors. PM sends the PDF to Acme's marketing lead.

### Step 3: Next client

```
/brand switch peak-health
/weekly
```

Same pattern. Under 30 seconds per report after the first.

## The onboarding workflow (for a new client)

When the agency adds a new client to UTM Grabber:

```
/brand new urban-growth urbangrowth.com
```

The skill:
1. Fetches urbangrowth.com via `web_fetch`
2. Auto-detects logo, primary color, company name
3. Shows the PM a preview
4. Saves the profile to memory

If the auto-detection needs tweaking:

```
/brand switch urban-growth
/brand edit
color to #E6572D
```

The whole onboarding is 60 seconds.

## Footer attribution options for agencies

The `footer_style` field on each brand profile controls what appears at the bottom of each page. Agencies should think carefully about this per client:

### `client-branded` (Vector Growth hides itself)
Footer: `Acme Corp · Attribution Report`
Use when the agency has told the client nothing about the tools behind the report. Most common in white-label arrangements where the client pays for "proprietary analytics."

### `co-branded` (default, recommended)
Footer: `Acme Corp · Powered by UTM Grabber`
Maintains attribution transparency while keeping the client's brand front-and-center. Also: "Powered by UTM Grabber" quietly markets the platform to prospective clients who see the reports.

### `utm-grabber` (direct-customer style)
Footer: `UTM Grabber · acmecorp.com`
Only for direct UTM Grabber customers, not agency-white-label scenarios.

The data-source integrity line (`Data source: UTM Grabber · {domain} · pulled {timestamp}`) always appears on every page regardless of footer style. This is the audit trail, not branding.

## Rollup branding rules

When the agency runs the **Agency Client Rollup** report, each client's section within the rollup should be visually marked with that client's primary color — a small colored bar or chip — so the PM can visually scan which client is which. The rollup's overall styling comes from the agency's self profile.

Example:

```
┌─────────────────────────────────────────┐
│ PORTFOLIO ROLLUP · Vector Growth · Apr  │
│                                         │
│ ■ Acme Corp      142 leads   +18%       │
│ ■ Peak Health     87 leads   +4%        │
│ ■ Bright Media    55 leads   −12%       │
│ ■ Urban Growth    38 leads   +40%       │
└─────────────────────────────────────────┘
```

Each `■` takes its color from that client's `colors.primary`. Makes the rollup scannable in one second.

## What the agency sees in Claude memory

After setting up 10 clients, Claude memory contains:

```
UTM Grabber brand profile [vector-self]:  {...}
UTM Grabber brand profile [acme-corp]:    {...}
UTM Grabber brand profile [peak-health]:  {...}
UTM Grabber brand profile [bright-media]: {...}
... (7 more) ...
UTM Grabber active profile: acme-corp
```

The `/brand` command with no args shows this list, making it easy to scan and switch.

## Backup and portability

Agencies should periodically export all brand profiles. One command:

```
/brand export all
```

The skill saves every profile as JSON files in `/mnt/user-data/outputs/brand-{profile_id}.json` and presents them together. The agency downloads and archives them. If they ever lose Claude's memory or switch accounts, they can re-import:

```
/brand import
(user uploads a zip of brand-*.json files)
```

## Scaling considerations

Claude's `memory_user_edits` has a 30-entry limit. That's enough for a mid-size agency but not for a 50+ client shop.

For high-volume agencies:
- Store only the most-active 25 clients in memory.
- Keep a master `brand-profiles.json` file in `/mnt/user-data/uploads/` (they upload it at session start).
- On `/brand switch {id}`, if the profile isn't in memory, check the uploaded file and hot-load it.

This isn't MVP — most agencies have <30 clients. Flag the limit if an agency hits it and offer the file-based approach.

## One common mistake to avoid

Agencies sometimes ask: "Can Claude just automatically know which brand to use based on which client's MCP I'm pulling from?"

Tempting but wrong. Claude can see the MCP's site domain but not the client-to-brand relationship — those are two different pieces of context. Always require an explicit `/brand switch` before running client-specific reports. Silent brand-matching gets one wrong at the wrong moment and sends Acme's logo to Peak Health. Explicit switching is safer.

An optional enhancement: when running a report, show the active brand in the response preamble: "Running weekly report with Acme Corp branding." This lets the PM catch mismatches before the PDF is generated.
