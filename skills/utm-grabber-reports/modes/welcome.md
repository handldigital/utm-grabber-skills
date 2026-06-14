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

> Welcome. I turn your UTM Grabber data into branded reports, conversational answers, and ready-to-paste UTM URLs — all driven by live data from your WordPress site.

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

Stop there. Do not continue writing — the tool's docs say the user's tap IS their next message. Wait for them.

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
        "UTM hygiene audit",
        "Landing page performance",
        "Set up my brand first"
      ]
    }
  ]
})
```

### Agency

Short intro text:

> Good. Agency workflow is different — one brand profile per client, plus portfolio rollup reports. Want to start with setup or jump into a report?

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

> Good. Two reports you'll find most useful — one for weekly scanning, one for budget planning.

Then:

```
ask_user_input_v0({
  "questions": [
    {
      "question": "Which first?",
      "type": "single_select",
      "options": [
        "Weekly executive summary",
        "Lead volume forecast",
        "Monthly performance review",
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
        "Generate a branded report",
        "Answer a specific question",
        "Generate UTM URLs for campaigns"
      ]
    }
  ]
})
```

#### If they pick "See a sample report (no setup needed)"

This is **demo mode** — generate a report using the synthetic demo dataset bundled with the skill, with no MCP required. Customer sees a full-quality report without connecting their WordPress site.

Workflow:
1. Use the synthetic demo entries from `scripts/demo_data.py` (imports `get_demo_current()` and `get_demo_prior()` returning 300+ realistic entries each)
2. Build a monthly report with the stock UTM Grabber brand profile (or prompt for "Sample brand" vs. "UTM Grabber brand" — one tap)
3. Generate HTML + offer PPTX follow-up
4. After delivery, offer two buttons: "Connect my site to run this on real data" (routes to `/brand` then MCP discovery) or "Show me a different report type"

One-line intro before calling the builder:

> Here's what a monthly review looks like, built on a realistic demo dataset. Yours will look the same but with your data.

No promises about the gradient ("shall I show it in dark mode instead?" — that's fine as a follow-up). Keep demo mode fast and single-shot.

#### If they pick "Show me the full menu"

Show the 18-report list grouped into 4 categories with interactive buttons — not a wall of text.

## What NOT to do

- **Don't ask 5 onboarding questions.** One role question, then recommendations. That's it.
- **Don't show the full 17-report catalog upfront.** Overwhelming. Three recommendations per role is enough.
- **Don't demand brand setup before their first report.** Default UTM Grabber branding works fine for exploration. Offer `/brand setup` as a suggestion, never a requirement.
- **Don't auto-run a report without confirmation.** The welcome message recommends — the customer runs when ready.

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

This teaches the follow-up patterns organically without dumping all 18 reports on them.

## Trigger detection heuristic

Consider this the customer's first run if ALL of these are true:
- No saved brand profile in Claude memory with the `UTM Grabber brand profile` prefix
- No prior MCP calls in the current conversation
- The user's message is a greeting, question about capabilities, or `/welcome` / `/help`

If the user asks for a specific report or action directly, skip the welcome flow and just run what they asked — don't make them sit through onboarding they didn't request.
