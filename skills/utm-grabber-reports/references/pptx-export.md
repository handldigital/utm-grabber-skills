# PowerPoint export

Customers want a `.pptx` to present, to paste slides into a bigger deck, or to edit copy before sharing. The skill builds a native, editable deck from the same summary as the HTML.

## When to offer

After any report, one line: "Want this as a PowerPoint deck?" Build it unprompted only when the request asked for it ("run the monthly as a pptx", "I need slides for Monday").

Trigger phrases: "export as pptx", "PowerPoint version", "slides", "a deck", "for my presentation", `/pptx`. They apply to the most recent report; reuse its `summary` (no new data pull).

## How

```python
from build_report import build_report
build_report(summary, "/mnt/user-data/outputs/monthly-2026-10-05.pptx", theme=theme)
```

Do NOT use a generic PowerPoint skill and do NOT screenshot the HTML. The engine already builds the deck natively:

| Report section | Slide |
|---|---|
| title-block | Cover (Studio: brand-color cover; Boardroom: dark with a brand-tinted gradient; Ledger: crisp rule; Classic: serif title with mono kicker) |
| stat-strip (+ the insight right after it) | "At a glance": KPI cards with deltas and sparklines, headline as the title |
| section-header | Becomes the title of the next slide |
| chart-insight / chart | Native chart in a card, insight panel beside it |
| ranked-list | Native table with in-cell bars and pills; past 11 rows it splits evenly across extra slides |
| funnel / flow / heatmap / matrix | Vector shapes matching the HTML geometry |
| comparison / callouts / scorecard / timeline | Purpose-built slides |
| recommendations | Numbered action cards (Ledger: an action list) |
| notes | Small print at the foot of the closing slide, or its own final slide when long |
| closing | Summary slide: the next step, key numbers, recap bullets |

## Fonts

The theme's fonts are embedded in the file. PowerPoint (Mac and Windows) shows them exactly. Google Slides maps them by name (they are all Google Fonts). Keynote ignores embedded fonts and substitutes Helvetica: the deck stays tidy (layouts keep room for the wider fallback) but looks plainer. If a Keynote user asks, offer the theme's font files to install (double-click, Install).

## Speaker notes

Off by default: Keynote refuses decks that contain notes pages. If the user presents from PowerPoint or Google Slides and wants talking points, set `summary["meta"]["speaker_notes"] = True` before building.

## Output conventions

Same basename as the HTML and PDF, `.pptx` extension, in `/mnt/user-data/outputs/`. Present with `present_files`.

## Customer-facing phrasing

"Here's the deck. Every chart and number is editable." Never mention python-pptx, XML, embedding or fonts unless the user asks.
