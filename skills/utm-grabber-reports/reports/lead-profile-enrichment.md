# Lead Profile Enrichment

## Triggers

- `/lead`
- `tell me about`
- `lead profile`
- `who is`
- `lead enrichment`

## Purpose

Everything UTM Grabber recorded about one person: how they found you, what closed them, every submission with its UTM values, what they typed into the forms, and the angle for the first sales call. Answers "who is this lead and how did they actually get here?"

## Build it

```python
from recipes_v2 import get_recipe
summary = get_recipe("lead-profile")(all_entries, "jane@acme.com", forms=forms,
                                     brand_profile=brand, customer_domain="example.com")
```

Registry keys: `lead-profile`, `lead`, `profile`, `lead-profile-enrichment`.
Signature: `build_lead_profile(all_entries, lead_email=None, brand_profile=None, customer_name=None, customer_domain="", compare_label=None, prepared_by=None, prepared_for=None, forms=None, **kwargs)`

- `all_entries`: pull a wide date range so every submission from this person is included.
- `lead_email`: matched exactly, ignoring case, across every email field.
- `forms` (optional): `[{"id", "title"}]` so submissions show form names instead of IDs.

## Section order

1. **title-block**: "{Name} found you through {channel} and filled N forms." Kicker carries the masked email.
2. **callouts** (up to 4): how they found you (first touch, or the earliest form when first touch was not captured), what closed them (the touch before the first form, with the search term or campaign), days to convert (first visit to first form, or first form to latest), submissions.
3. **insight-card** "The sales angle": the topic to open with (service, search term, campaign, timeline or budget), their stated timing and budget, repeat visits, and the lead score from the lead quality scorer rules.
4. **section-header 01 The journey** + **timeline**: the first visit (landing page, referrer domain, first-touch UTMs) and every submission with source, medium, campaign, term, content and click ID type as tags.
5. **section-header 02 The answers** + **ranked-list** of form fields: latest answer per field, email and phone masked, system and attribution fields left out.
6. **section-header 03 Next steps** + **recommendations**: open the call with the topic, record the first touch in the CRM, merge duplicate submissions, reply by email when no phone was given.
7. **closing**: "Next: call {name} about {topic}." with the number behind it.

Email not found: a short, honest report saying how many submissions were searched and what to check.

## Privacy

Emails are masked (`j***@domain.com`), phone numbers keep only the last four digits, IP addresses and user agents are never printed, referrers show the domain only.

## Voice guidance

Sales-rep ready. A person, not a row in a spreadsheet. Use their first name, quote what they searched, and keep every claim tied to a recorded touch or answer.
