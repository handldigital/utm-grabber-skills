# Interactive Buttons

Claude has a tool called `ask_user_input_v0` that renders tappable buttons in the chat. Use it anywhere the customer would otherwise need to type a letter ("A"), a slash command (`/monthly`), or remember specific phrasing. Tapping beats typing — especially on mobile.

## When to use buttons vs. plain text

**USE BUTTONS when:**
- The customer needs to pick 1 of 2–4 options (role, report type, yes/no)
- The options are discrete and well-known to the skill (our catalog of 18 reports, our 4 user roles, brand-setup paths)
- The next step depends on their choice and you can't start working until they answer
- It's a follow-up offer after a report ("what next?")

**DON'T use buttons when:**
- The answer is free-text (an email address, a campaign name, a hex color)
- The customer is already typing a specific request (just execute it; don't interrupt with buttons)
- The question has 5+ options (use a prompt-shortcut list instead, or ask one narrowing question)
- You're sharing results, not soliciting input

## How the tool works (mechanics)

Call `ask_user_input_v0` with a list of 1–3 questions, each having 2–4 options. The tool renders buttons, the user taps one, their choice comes back as their next message. **Your turn ends after the call** — do not keep writing text after asking.

Format:

```
ask_user_input_v0({
  "questions": [
    {
      "question": "Which best describes you?",
      "type": "single_select",
      "options": ["Marketer", "Agency", "Executive", "Just exploring"]
    }
  ]
})
```

Keep option labels **short** — 2–4 words. Long labels wrap weirdly on mobile.

## Where to use them in this skill

### Welcome flow — role selection

First-run question should be a single_select button set, not a lettered list:

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

### Brand onboarding — path selection

After initial ask, present the three paths as buttons:

```
ask_user_input_v0({
  "questions": [
    {
      "question": "How do you want to set up branding?",
      "type": "single_select",
      "options": [
        "Auto-detect from my website",
        "Quick setup (2 colors)",
        "Advanced (all 5 colors)",
        "Skip, use defaults"
      ]
    }
  ]
})
```

### Brand onboarding — auto-detect confirmation

After showing detected brand values:

```
ask_user_input_v0({
  "questions": [
    {
      "question": "Does this branding look right?",
      "type": "single_select",
      "options": ["Yes, save it", "Tweak something", "Use UTM Grabber defaults"]
    }
  ]
})
```

### Ambiguous report request

If the user says "give me a report" without specifying which:

```
ask_user_input_v0({
  "questions": [
    {
      "question": "Which report do you want?",
      "type": "single_select",
      "options": [
        "Monthly performance review",
        "Weekly one-pager",
        "UTM hygiene audit",
        "Something else"
      ]
    }
  ]
})
```

If they pick "Something else", follow up with a second button set covering the next tier of reports.

### Report follow-up offers

After generating any report, instead of typing "Want to run the hygiene audit next?", render buttons:

```
ask_user_input_v0({
  "questions": [
    {
      "question": "What next?",
      "type": "single_select",
      "options": [
        "Run UTM hygiene audit",
        "Deep dive on top campaign",
        "Export as PowerPoint",
        "I'm done"
      ]
    }
  ]
})
```

### Form selection when multiple exist

If `list_forms` returns 3+ forms with comparable volume:

```
ask_user_input_v0({
  "questions": [
    {
      "question": "Which form should I analyze?",
      "type": "single_select",
      "options": [
        "Attribution Demo Request (500 leads)",
        "Contact Form (143 leads)",
        "Newsletter Signup (87 leads)",
        "All forms combined"
      ]
    }
  ]
})
```

Include entry counts in option labels — helps the customer pick without guessing.

### Date range when unspecified

If the user asks for a report with no time window:

```
ask_user_input_v0({
  "questions": [
    {
      "question": "What time window?",
      "type": "single_select",
      "options": ["Last 7 days", "Last 30 days", "Last 90 days", "Custom range"]
    }
  ]
})
```

If they pick "Custom range", ask for dates as free text.

### Confirmation before long operations

Before running the Agency Client Rollup (which makes many MCP calls):

```
ask_user_input_v0({
  "questions": [
    {
      "question": "Rollup across all 10 client sites? This takes ~90 seconds.",
      "type": "single_select",
      "options": ["Yes, run it", "Pick specific clients", "Cancel"]
    }
  ]
})
```

## The hybrid pattern

Sometimes a message should have BOTH text content AND buttons — e.g., showing results and asking "what next?". Structure:

1. Write the short message (headline insight, file presented).
2. Call `ask_user_input_v0` at the very end with a follow-up question.

This lets the customer read the result and then tap, without needing to formulate a new request.

## What NOT to do

- **Don't use buttons for every message.** Only when soliciting a specific choice.
- **Don't offer more than 4 options.** Cognitive load. Break into layered questions instead.
- **Don't repeat options already given.** If the user tapped "Agency" in welcome, don't ask "are you an agency?" later.
- **Don't block free-text alternatives.** Mention "or just tell me what you want" alongside the buttons, so customers who prefer typing aren't trapped.
- **Don't send buttons alone on generic messages.** Pair them with a short sentence of context.

## Fallback when buttons aren't available

If `ask_user_input_v0` isn't available in the current environment, fall back to a clear markdown bullet list — as described in the SKILL.md formatting rule. Never send inline lettered options (`**A.** Option`).
