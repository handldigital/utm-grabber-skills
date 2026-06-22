# PowerPoint Export

Every report in this skill produces HTML + PDF by default. Customers often also want a `.pptx` so they can drop a specific slide into a larger deck, edit numbers in-place, or brand-customize further. This reference explains when and how to offer a PPTX export alongside the default outputs.

## When to offer PPTX

Automatically offer PPTX export at the end of every report that produces slide-based output (the 15 slide-deck reports — not Q&A, not the UTM Generator, not the Lead Quality Scorer's ranked-table output).

Suggestion line to append at the end of the response:

> Want this as a PowerPoint too? I can also save it as a `.pptx` — just say "export as pptx" or "give me the PowerPoint version."

Don't generate the PPTX automatically. It takes noticeably longer than the HTML/PDF path, and most customers are fine with the PDF. Offer; don't impose.

## The trigger phrases

Any of these should trigger a PPTX conversion of the most recently generated report:
- "export as pptx"
- "give me the PowerPoint"
- "PowerPoint version"
- "also save as pptx"
- "save as pptx too"
- "I need a pptx"
- "/pptx" (shortcut)

If the user asks for PPTX at the START of a request (e.g., "run the monthly review as a pptx"), generate both HTML/PDF AND PPTX together rather than producing HTML first and converting.

## How to generate it

Use the existing `pptx` skill available in the environment. Read `/mnt/skills/public/pptx/SKILL.md` before generating your first PPTX in any conversation — it has the build instructions.

The conversion is NOT "render the HTML and export as pptx." Instead, reconstruct the report as a proper PowerPoint deck using the pptx skill's native slide-building tools. This produces a real editable PPTX with native shapes, real text fields, and embedded charts — not screenshots of HTML.

### The correspondence

Each of the 10 slide types in the HTML template has a PPTX equivalent:

| HTML slide | PPTX slide |
|---|---|
| Cover | Title slide layout with custom typography |
| KPI strip + headline | 4 stat cards on the top, insight block below |
| Chart + insight (2-col) | Chart on left, text box on right |
| Full-width chart + 3 stats | Chart on top, three text boxes below |
| Two-column profile | Chart + data table |
| Comparison bars | Grouped/stacked bar chart |
| Recommendations grid | 2x2 grid of text boxes |
| Closing | Title slide with CTA |

The content is identical — same data, same narrative, same design intent — just rendered using PowerPoint-native elements instead of HTML/CSS.

## Brand fidelity

The PPTX should use the customer's active brand profile (same as the HTML does):

1. Load the active brand profile from Claude memory (same way the HTML renderer does).
2. Apply `colors.primary` to chart series, accent elements, and callout rules.
3. Apply `colors.ink` and `colors.surface` to text and backgrounds.
4. Insert the `logo` as an image on the cover and (if inline style) on every slide footer.
5. Match fonts approximately — PowerPoint doesn't have access to the same Google Fonts, so use the closest system match:
   - Instrument Serif → Cambria or Garamond
   - Geist → Segoe UI or Calibri
   - Geist Mono → Consolas or Courier New

Note the font substitution in a small line on the cover: "Fonts may differ from online version."

## Output conventions

- Save to `/mnt/user-data/outputs/{report-name}-{YYYY-MM-DD}.pptx` — same basename as the HTML and PDF, different extension.
- Present all three files via `present_files` so the customer sees HTML, PDF, and PPTX as download options.

## When PPTX doesn't make sense

Three reports are NOT good PPTX candidates:
- **Q&A answers** — too small and conversational for a deck format.
- **UTM Template Generator** — the output is a code block, not slides.
- **Lead Quality Scorer** — the output is a ranked table; export as CSV/XLSX instead of PPTX.

For these, if the user asks "can I get this as PowerPoint?", respond:

> This output isn't really a deck — it's [a single answer / a table / a code block]. Want me to export it as [Excel / plain text / copy-ready format] instead?

## Customer-facing phrasing

When offering or delivering PPTX, keep it brief:

**Offering:**
> Want this as a PowerPoint too? Just ask.

**Delivering:**
> Here's the `.pptx` version. Editable slides, your brand applied. Fonts will render in whatever your PowerPoint has installed — I've used closest matches to the online version.

Don't over-explain the font substitution or walk through the conversion — the customer cares about the output, not the mechanism.
