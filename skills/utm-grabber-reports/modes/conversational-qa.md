# Conversational Q&A Mode

Not a report — a mode. The customer asks a specific attribution question in plain English ("how many leads from LinkedIn last Tuesday?") and gets a one-sentence answer with optional inline chart. No deck, no PDF, no slide chrome. Just the answer.

This is the mode that will get the skill used 20× more than any report. Reports get run once a week. Questions get asked every day.

## When to use this mode

Use Q&A mode (NOT a full report) when the user's request is:

1. **Specific / narrow** — "how many", "which", "what was", "when did", "is X above Y".
2. **Short-horizon** — asking about a single metric, not a narrative or a multi-section analysis.
3. **Conversational in tone** — feels like a chat message, not a deliverable request.

Examples of Q&A triggers:
- "How many LinkedIn leads last week?"
- "What was my top source yesterday?"
- "Did Facebook outperform Google this month?"
- "Which campaign had the most HubSpot leads?"
- "When was my best day in April?"
- "Is my UTM coverage still below 80%?"

Examples that are NOT Q&A (route to a report):
- "Give me a monthly report" → Monthly Performance Review
- "Audit my UTMs" → UTM Hygiene Audit
- "Deep dive on Q1 Reactivation" → Campaign Deep Dive

## The response format

Every Q&A answer follows this structure:

```
{direct_answer_sentence}

{optional_short_explanation — 1 sentence, only if non-obvious}

{optional_inline_chart — only for count-over-time or top-N questions}

{optional_follow-up_suggestion — "Want a deeper view? Try 'campaign deep dive on X'."}
```

### Good example

**User:** How many LinkedIn leads did I get last week?

**Response:**
> 14 leads from LinkedIn last week (Mar 24 – Mar 30), vs 9 the week before — +56%.
>
> [small sparkline chart showing 7 days]
>
> Want to see which campaigns those came from? Try "top LinkedIn campaigns last week".

### Bad example (over-answers)

**User:** How many LinkedIn leads did I get last week?

**Response:**
> Looking at your data from the past week, I can see that LinkedIn has been a strong performing channel. Your LinkedIn leads totaled 14, with 9 paid-social and 5 organic social. The week-over-week change is +56% vs 9 the prior week. Additionally, LinkedIn makes up 16% of total leads this week, compared to your Google (31%) and Facebook (18%)…

NO. The question was "how many". The answer is "14". Everything else is an optional follow-up, not the answer.

## The principles

### 1. Answer first, context second

Start with the specific number or fact the user asked for. Never bury the answer under preamble.

### 2. Match the granularity of the question

- "How many X last week?" → one number
- "Which source is best?" → one source
- "How did X and Y compare?" → two numbers and the delta
- "What's my trend?" → short prose + small chart

### 3. Offer a follow-up, don't assume one

Always end with ONE suggested follow-up question the user might want to ask. Never run that follow-up automatically. This keeps control with the user.

### 4. Use small inline charts, not slides

When a chart helps, render a small SVG or inline Chart.js — 600×200 px, minimal chrome, one colour, no legend unless truly necessary. No slide frame, no cover, no footer.

### 5. No file output

Q&A answers appear inline in the conversation. Don't save to `/mnt/user-data/outputs/`. Don't call `present_files`. The answer IS the output.

## Routing from Q&A to reports

If a user asks 3+ follow-up questions on the same theme, proactively offer: "You've been digging into LinkedIn performance — want me to run the full Campaign Deep Dive on your LinkedIn campaigns instead?"

This is the bridge from exploratory Q&A to deliverable reports.

## MCP call discipline

Q&A mode should feel instant. Every MCP call is a multi-second round-trip; skip it whenever the data is already on disk.

- **Check `load_cached_superset` FIRST.** If a prior report pulled 30 days and the user asks "how many LinkedIn leads last week?", the cached 30-day pull encloses last week — filter it in Python, zero MCP calls. This is the single biggest win on Q&A speed. See `helpers.py::load_cached_superset`.
- **Pull ONLY what the question requires** when a fresh pull is needed. Q&A mode explicitly SKIPS the automatic comparison-window pull every report does. If the user asks "how many LinkedIn leads last week?" and no cache hit: pull last week only — NOT last week AND the week before. If they explicitly ask for a comparison ("this week vs last?"), pull both windows **in parallel** (same tool-use response).
- **Don't re-pull** if the user is asking variations on data already in the cache window. Date-filter in Python.
- **Shift outside the cached window** → fresh pull, and save it to cache.

Two MCP-call savings most Q&A flows hit: (a) cached-superset filter on narrow follow-ups, (b) parallel pulls when a comparison IS requested.

## Ambiguity handling

If the question is ambiguous, ask ONE clarifying question — never two, never three.

**User:** How's Google doing?

**Response:**
> Do you mean Google paid search (CPC) specifically, or all Google-sourced traffic including organic? (Paid search is 143 leads this month; total Google is 156.)

If the user doesn't answer, default to the most useful interpretation and say which assumption you made.
