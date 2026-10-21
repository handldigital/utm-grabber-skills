# Welcome / First-Run Experience

## When to load this file

Triggered by ANY of these, at any point in a conversation:

- **Greetings**: "hi", "hello", "hey", "yo"
- **Help requests**: `/welcome`, `/help`, `/start`, "what can you do", "what can this do", "help"
- **Walkthrough / demo requests**: "walk me through", "walk through", "show me", "show me how this works", "tour", "demo", "demo me", "teach me", "how do I use", "explain it", "introduce me", "get me started", "onboard me", "use the skill", "try the skill"
- **Implicit first-run**: no saved brand profile, no prior reports in the conversation, no memory of prior interactions

## What NEVER to do when triggered

When triggered, Claude must NOT:
- Summarize the skill's files, modes, rules, or architecture
- Write prose explaining how the skill works internally
- Use any banned word from `references/voice-discipline.md`
- Produce numbered/bulleted lists describing Reports / Modes / Utilities / Templates
- Describe the "four rules" or any internal structure

## What TO do when triggered

1. Write the short intro in the "Welcome message" section below (or its role-specific variant)
2. Call `ask_user_input_v0` with the role-selection buttons
3. STOP WRITING. The user's tap is their next message.

The goal is always: one short intro sentence + interactive buttons. Never a file tour.

## The goal

Lower the "first report" friction. A customer should produce their first usable output within 90 seconds of their first message. That means one welcome message + one role-clarifying question + one recommended report, not a tour.

## The welcome message

Show this on first-run. Pair a short written intro with an `ask_user_input_v0` button set for the role choice.

### Step 1: Short intro + role buttons

Write this short intro:

> Welcome. I turn your UTM Grabber data into branded reports (web page, PDF or PowerPoint, in four looks), quick answers, and ready-to-paste UTM URLs, all from live data on your WordPress site. Connect your ad, analytics or CRM tools too and I'll show which ads actually brought customers.

Then call `ask_user_input_v0`:

```
ask_user_input_v0({
  "questions": [
    {
      "question": "Which best describes you?",
      "type": "single_select",
      "options": [
        "Marketer / PPC manager",
        "Agency with multiple clients",
        "Executive or founder",
        "Just exploring"
      ]
    }
  ]
})
```

Stop there. Do not continue writing : the tool's docs say the user's tap IS their next message. Wait for them.

### Step 2: Role-specific response + report picker buttons

Based on which role they tapped, respond with a short intro and ANOTHER button set for the recommended reports.

Wait for their answer. Don't overwhelm them with the catalog upfront.

## Role-specific paths

### Marketer / PPC manager

Short intro text:

> Good. Three reports I'd run first in your shoes. Pick one and I'll run it now, or tell me what you're curious about.

Then call:

```
ask_user_input_v0({
  "questions": [
    {
      "question": "Which report first?",
      "type": "single_select",
      "options": [
        "Monthly performance review",
        "Which ads brought customers (uses my ad accounts)",
        "UTM hygiene audit",
        "Set up my brand first"
      ]
    }
  ]
})
```

### Agency

Short intro text:

> Good. Agency workflow is different : one brand profile per client, plus portfolio rollup reports. Want to start with setup or jump into a report?

Then call:

```
ask_user_input_v0({
  "questions": [
    {
      "question": "What first?",
      "type": "single_select",
      "options": [
        "Set up first client's brand",
        "Run portfolio rollup",
        "Run report for one client",
        "Walk me through agency workflow"
      ]
    }
  ]
})
```

Route each choice:
- "Set up first client's brand" → `utilities/brand-onboarding.md`, `/brand new` flow
- "Run portfolio rollup" → `reports/agency-client-rollup.md`
- "Run report for one client" → ask which client, then which report
- "Walk me through agency workflow" → load `references/agency-multi-brand.md` and summarize in 5 bullets

### Executive / founder

Short intro:

> Good. Two reports you'll find most useful : one for weekly scanning, one for budget planning.

Then:

```
ask_user_input_v0({
  "questions": [
    {
      "question": "Which first?",
      "type": "single_select",
      "options": [
        "Weekly executive summary",
        "Full funnel: visits to revenue",
        "Quarterly business review",
        "Ask me a quick question instead"
      ]
    }
  ]
})
```

### Just exploring

Short intro:

> Three things I do. Pick what sounds interesting and I'll show you.

Then:

```
ask_user_input_v0({
  "questions": [
    {
      "question": "What do you want to see?",
      "type": "single_select",
      "options": [
        "See a sample report (no setup needed)",
        "See the four report looks",
        "Answer a specific question",
        "Generate UTM URLs for campaigns"
      ]
    }
  ]
})
```

#### If they pick "See a sample report (no setup needed)"

This is **demo mode**: a full-quality report built on the bundled multi-platform demo dataset (a fictional dental clinic with leads, Google and Meta Ads spend, analytics visits and CRM deals). No site connection needed.

```python
import sys; sys.path.insert(0, "/mnt/skills/user/utm-grabber-reports/scripts")
from demo_v2 import build_demo
paths = build_demo("monthly", "/mnt/user-data/outputs/sample-monthly.html", theme="studio")
```

One-line intro before delivering:

> Here's a monthly review built on a realistic sample business. Yours looks the same, with your data.

After delivery, offer buttons: "See it in another look", "Show the cross-platform version" (`build_demo("full-funnel", ...)`), "Connect my site to run this on real data".

#### If they pick "See the four report looks"

Render the same sample report in all four themes (`studio`, `boardroom`, `ledger`, `classic`) and present the four files together:

```python
from demo_v2 import build_demo
for t in ("studio", "boardroom", "ledger", "classic"):
    build_demo("monthly", "/mnt/user-data/outputs/sample-monthly-%s.html" % t, theme=t)
```

Then: "Which look should your reports use?" (buttons). Save the pick as the brand profile's `theme`.

#### If they pick "Show me the full menu"

Show the 30 reports grouped into 4 categories with interactive buttons, not a wall of text: Core performance (monthly, weekly, daily pulse, quarterly review, leaderboard, deep dive, paid vs organic, anomalies, forecast, compare, agency rollup), Leads and tracking (audit, lead scorer, lead profile, forms, landing pages, sources per CRM, lead timing), Paid media and revenue (ad creative, keywords, budget what-if, revenue by source, AI assistant referrals, customer journeys), Cross-platform (full funnel, which ads brought customers, platforms vs reality, traffic that never converts, close rate by first touch, wasted spend).

## What NOT to do

- **Don't ask 5 onboarding questions.** One role question, then recommendations. That's it.
- **Don't show the full 17-report catalog upfront.** Overwhelming. Three recommendations per role is enough.
- **Don't demand brand setup before their first report.** Default UTM Grabber branding works fine for exploration. Offer `/brand setup` as a suggestion, never a requirement.
- **Don't auto-run a report without confirmation.** The welcome message recommends : the customer runs when ready.

## After the first report

Once the customer has successfully run their first report, offer next steps as buttons:

Write the usual short headline sentence about what the report showed, then call:

```
ask_user_input_v0({
  "questions": [
    {
      "question": "What next?",
      "type": "single_select",
      "options": [
        "Set up my brand (30 seconds)",
        "Run another report",
        "Export this as PowerPoint",
        "I'm done for now"
      ]
    }
  ]
})
```

This teaches the follow-up patterns organically without dumping all 30 reports on them.

## Trigger detection heuristic

Consider this the customer's first run if ALL of these are true:
- No saved brand profile in Claude memory with the `UTM Grabber brand profile` prefix
- No prior MCP calls in the current conversation
- The user's message is a greeting, question about capabilities, or `/welcome` / `/help`

If the user asks for a specific report or action directly, skip the welcome flow and just run what they asked : don't make them sit through onboarding they didn't request.
