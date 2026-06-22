# Narrative Voice

How to write the prose in every UTM Grabber report. Load this file before writing any insight text — the "headline" captions, the "what matters" cards, the recommendations.

## The core principle

The numbers are the facts. The narrative is the insight — the one sentence that tells the customer *what the number means for them tomorrow*. A chart without a sentence is a data dump. A sentence without a chart is opinion. The report is always both.

## Voice at a glance

**We sound like:** a senior marketing analyst who has been in the trenches. Confident, specific, no jargon. Respects the reader's time.

**We do not sound like:** a marketing blog, a pitch deck, an AI assistant, a motivational poster, or a consultant trying to impress.

### Words we avoid

| Avoid | Why | Say instead |
|---|---|---|
| "leverage" | Empty verb | "use", "apply" |
| "synergize", "optimize", "ideate" | Corporate filler | "combine", "improve", "think about" |
| "unlock", "supercharge", "game-changing" | Sales copy smell | "enable", "accelerate", "material" |
| "in conclusion", "to summarize" | Structural throat-clearing | Just say the point |
| "as we can see", "the data shows" | Adds no information | Just state the finding |
| "going forward", "moving forward" | Filler | "next month", or delete |
| "unprecedented", "transformational" | Hyperbole | Quantify it |
| emoji | Breaks PDF rendering and the tone | — |

### Words we use

- **Real verbs.** "Paid search closed 252 leads" — not "there was closure activity of 252 in paid search."
- **Concrete nouns.** "Google/CPC" — not "our paid search channel."
- **Numbers in sentences.** "Q1 Reactivation drove 41 leads, the top campaign of the month."
- **Recommendations as actions.** "Rebuild lookalikes from the Q1 Reactivation audience" — not "consider exploring audience expansion."

## Section-by-section voice rules

### Headlines / slide titles

**Format:** One clear sentence, no period, display font, ~6–12 words.

Good:
- *"Paid search closes what organic starts."*
- *"Search still rules."*
- *"Your biggest UTM leak is /lp/hubspot-source-reporting."*

Bad:
- *"Channel Performance Analysis"* (label, not insight)
- *"Here's what happened this month"* (filler)
- *"UTMs"* (one word headers are lazy)

### Insight cards ("What matters", "Headline", "What it means")

**Format:** One short paragraph (2–4 sentences, ~40–80 words). Always lead with the finding, then the implication.

Structure:
1. State the finding (the number, the comparison, the shift).
2. Explain what it means in business terms.
3. (Optional) Hint at the action — saved for the Recommendations slide if major.

Example:
> Google is the single largest source with 143 leads — nearly three times Facebook or LinkedIn. Google/CPC alone accounts for 143 of the 500 monthly leads, while organic and direct continue to provide a steady mid-funnel baseline. The rest of paid search underperforms Google by 4x; shift spend accordingly.

### Recommendations

**Format:** Numbered cards, 1–4 actions. Each action has:

- A **verb-led title** (3–6 words): "Double down on paid search" — not "Paid Search Strategy Recommendation"
- A **sentence of context** — the number or behaviour driving the recommendation.
- (Optional) A **specific next step** — a URL to fix, a campaign to rebuild, a CRM field to check.

Four recommendations is the maximum. Any more and the reader treats them as a laundry list and does none of them. If you have eight ideas, pick the four that move the most revenue.

Example recommendation (well-written):
> **Double down on paid search**
> Google/CPC alone drives 143 leads — three times the next channel. Shift incremental budget from lower-yield tests (YouTube, G2) and expand the Q1 Reactivation ad group with fresh creative this week.

### Data-source footer

**Format:** Single line, mono font, muted colour, 12px.

`UTM Grabber · {domain} · {plugin} (form {form_id}) · {pulled_at}`

Never decorate the footer. No "Thank you for reading." No company slogans. Just the audit trail.

## Calibrating to the data

The tone should shift slightly based on what the data shows:

- **Healthy performance:** confident, forward-looking. "You're in a strong position; here's how to compound it."
- **Mixed performance:** balanced. "Paid is working; attribution hygiene is costing you real leads."
- **Weak performance:** direct, not alarming. "210 of your 500 leads have no source — this is the first fix."

Never catastrophize. Never flatter. A real analyst doesn't say "amazing job!" and doesn't say "you're in trouble" — they describe what's true and what to do about it.

## A few end-to-end examples

### Cover page

- Eyebrow: `ATTRIBUTION · MONTHLY REPORT`
- Title: `UTM & Traffic Source Performance Review`
- Subtitle: `{Customer / Site Name} · Last 30 Days · {start} – {end}`
- Author line: `Prepared by UTM Grabber`

### KPI strip headline (after the 4 stat cards)

> **Paid search plus paid social drove half your pipeline this month.**
>
> Google alone contributed 143 of 500 leads. Organic and direct remain steady, and referral traffic is punching above its weight in first-touch discovery. The biggest attribution gap remains tagging hygiene — 43% of leads arrived without UTMs.

### Recommendations intro

> **Four moves for next month.**
> In priority order, from highest to lowest expected impact.

### Closing slide

- Title: `Questions or want deeper analysis?`
- Subtitle: `Book a strategy call at utmgrabber.com/strategy`
- Footer: standard data-source line

## One thing to remember

Every line of prose in a UTM Grabber report is earning or losing trust. Precise, specific, and short earns it. Vague, grand, and long loses it. When in doubt, cut the sentence.
