# Leads from AI Assistants

## Triggers

- `/ai-referrals`
- `ai referrals`
- `leads from chatgpt`
- `ai search traffic`
- `which ai assistants send leads`

## Purpose

Counts the leads whose converting visit came from an AI assistant (ChatGPT, Perplexity, Gemini, Claude, Copilot, DeepSeek, Grok, Meta AI), shows which assistant sends them, which pages they land on, whether the channel is growing, and how those leads compare with Google organic. Answers "is AI search sending us customers, and which pages earn it?"

## Build it

```python
from recipes_v2 import get_recipe
summary = get_recipe("ai-referrals")(leads, prior, history=history, deal_rows=deal_rows,
                                     brand_profile=brand, customer_domain="example.com")
```

Registry keys: `ai-referrals`, `ai-assistants`, `ai-search`, `chatgpt`, `llm-referrals`.
Signature: `build_ai_referrals(leads, prior=None, history=None, deal_rows=None, brand_profile=None, customer_name=None, customer_domain="", compare_label=None, form_label=None, prepared_by=None, prepared_for=None, **kwargs)`

- `leads`: UTM Grabber entries for the period.
- `prior` (optional): the previous period. When missing, it is cut from `history` (the previous calendar month for a calendar month) if the history reaches back that far.
- `history` (optional): 90 to 180 days of leads for the weekly trend and the month-by-month growth line.
- `deal_rows` (optional): normalized CRM deals (`connectors.normalize_deal_rows`) for close rate and revenue per lead.

## Data

| Field | Plan | Used for |
|---|---|---|
| `organic_source_str (HandL)` ("OpenAI/ChatGPT", "Perplexity"...) | Premium | Main AI detection |
| `handl_ref_domain (HandL)` (chatgpt.com, perplexity.ai...) | Premium | AI detection |
| `utm_source` and `referrer` (first touch, HandL) | Premium | AI-started journeys |
| `user_agent (HandL)` | Premium | Phone share when form answers are compared |
| `utm_source (HandL)`, utm_source tags in landing page URLs | Free | Fallback detection (ChatGPT tags most links) |
| `handl_landing_page (HandL)` or `Source URL` | Free | Landing pages |

## How the numbers work

- AI lead: the converting visit's organic source, referrer domain, utm_source or landing page tag names an AI assistant (chatgpt.com, perplexity.ai, gemini.google.com, claude.ai, copilot.microsoft.com and the rest).
- Share of organic: AI leads divided by leads whose last touch was unpaid search or an AI assistant.
- AI-started journeys: first visit from an assistant, converting visit on another channel.
- Quality baseline: Google organic leads (below 10, all unpaid search, then all other leads). Deals are joined to leads once, by email. Each side needs 5 matched deals before close rate, revenue per lead and average sale are shown; otherwise form answers (phone, timeframe, company) are compared.
- Weekly trend: full 7-day windows ending on the last day of history, so a part week never looks like a drop.

## Section order

1. **title-block**: AI leads and the change against the prior period. Subtitle: top assistant and AI-started journeys.
2. **stat-strip**: AI leads (daily spark, delta), share of all leads (pts), share of organic (pts), AI-started journeys.
3. **insight-card** "The takeaway": the top assistant's share, the runners-up, month-by-month growth.
4. **section-header 01 Which assistants** + **chart-insight** (bar-horizontal by assistant, prior counts as notes).
5. **section-header 02 The trend** + **chart** (line of AI leads per week; a daily area without history).
6. **section-header 03 Landing pages** + **ranked-list**: path (mono), AI leads bar, share of AI, share of all leads, top assistant.
7. **section-header 04 Lead quality** + **comparison** (AI assistants vs Google organic) when there is something to compare.
8. **section-header Next steps** + **recommendations**: clear answers and prices on the top AI page; a quality fix when AI leads close less or buy smaller; a pricing and FAQ page when none brings leads; check what the top assistant says; credit AI-started journeys.
9. **notes**: detection rule, counts per field, share-of-organic definition, deal matching, the referrer caveat.
10. **closing**: the next step on the top AI landing page.

Short versions: fewer than 10 leads (lead list); free-plugin data (says AI detection needs UTM Grabber Premium and lists any leads found through tags such as utm_source=chatgpt.com); Premium data with no AI leads (how to earn the first ones); 1 to 9 AI leads (every AI lead listed).

## Voice guidance

Practical and current, never hype. AI referrals are small for most sites, so lead with growth and with the page that earns them. Counts are a floor: some assistant apps strip the referrer, and the notes say so. Name the assistant and the page in every recommendation.
