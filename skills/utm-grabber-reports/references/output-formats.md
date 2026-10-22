# Output formats

Every report can be delivered as HTML, PDF, PowerPoint or CSV. All formats come from the same `summary` dict, so a second format never needs a second data pull.

```python
from build_report import build_report
build_report(summary, "/mnt/user-data/outputs/monthly-2026-10-05.html", theme="studio")
build_report(summary, ["/mnt/user-data/outputs/monthly-2026-10-05.pdf",
                       "/mnt/user-data/outputs/monthly-2026-10-05.pptx"], theme="studio")
```

## HTML (default)

- One self-contained file: fonts (base64), styles and SVG charts are inline. Renders the same offline, behind firewalls, and as an email attachment. No font CDN calls.
- Dashboard layout by default: a slim header (brand, report, period, sources), the headline, the KPI band, then every chart, table and insight as a panel in a 12-column grid. The opening takeaway shares a column with the next step. Method notes fold away at the bottom. One screen shows the whole picture.
- `build_report(summary, path, layout="document")` (or `summary["meta"]["layout"] = "document"`) gives the long single-column read with a full cover, the same layout the PDF uses.
- Responsive: the grid steps down to two columns, then one, with phone-sized charts.
- Hover details on every chart mark; a "Show the numbers" table under every chart (accessible and copyable).
- Any of the 4 themes (`references/themes.md`).

## PDF

- Built by `engine/pdf_render.py`: headless Chromium prints the report's print layout.
- Letter by default, A4 with `paper="a4"` (or `meta.paper`).
- Paginated: cards, charts and recommendations never split across pages; headings never strand at a page bottom; long tables repeat their header row.
- Running footer: report name on the left, "Page X of Y" on the right; none on the cover page.
- Dark themes (Boardroom) print full-bleed dark to the page edge.
- Vector: text stays selectable, charts stay sharp at any zoom.

Offer after HTML: "Want this as a PDF to send to your team?"

### When the PDF can't be made

Some apps sandbox the commands you run. Codex on macOS blocks headless Chromium (`bootstrap_check_in ... Permission denied (1100)`), and some machines don't have Playwright. Then `build_report` raises `PdfUnavailable` (its message starts `PDF_UNAVAILABLE`) after building every other format you asked for.

- Say it in one plain sentence: "I couldn't make the PDF in this app, but the web page and the PowerPoint are ready."
- Offer the alternatives: they can open the web page and save it as a PDF from their browser's print menu, use the PowerPoint, or let this step run outside the app's sandbox (in Codex, approve running it with full access) so you can try again.
- Never build a PDF any other way (another library, a screenshot, a different layout), and never say a PDF was made when it wasn't.

## PowerPoint (PPTX)

- Built by `engine/pptx_render.py`: native, editable 16:9 deck.
- Slides: cover, "at a glance" (KPIs + the headline), then one slide per section. A section header becomes the title of the slide after it. Long tables continue onto extra slides, split evenly. Method notes sit at the foot of the closing slide, or on their own final slide when they're long.
- Native PowerPoint charts (editable data) for doughnuts, columns, stacked and grouped bars, lines, waterfalls and diverging bars. Funnels, flows, heatmaps, quadrant maps, bar lists and sparklines are drawn as vector shapes from the same geometry as the HTML.
- Native tables with in-cell bars and status pills.
- Theme fonts are embedded: PowerPoint (Mac and Windows) shows the exact typefaces. Google Slides maps them by name. Keynote ignores embedded fonts and substitutes Helvetica; layouts keep room for that so nothing overflows (`references/themes.md`).
- Speaker notes are off by default because Keynote rejects decks that contain notes pages. Set `summary["meta"]["speaker_notes"] = True` only when the user presents from PowerPoint or Google Slides and asks for talking points.

Offer after HTML: "Want this as a PowerPoint deck?" Good fits: presenting to leadership, pasting into an existing deck, handing to someone who will edit the copy.

## Live link (claude.ai)

In the Claude desktop app and Claude Code, the dashboard can go out as a private claude.ai link that updates in place: `build_report(summary, "<file>.artifact.html")`, then the Artifact tool. The live dashboard (`engine.live.build_live`) goes further and pulls fresh numbers from the viewer's own UTM Grabber connection each time it opens. Read `references/artifact-delivery.md` for publishing, sharing, scheduled refreshes and the live dashboard. Not available in claude.ai chat.

## CSV (raw data)

- `scripts/build_csv.py`: one row per lead, every contact field, every UTM field, click IDs, page context.
- UTF-8, opens in Excel and Google Sheets.

```python
from build_csv import export_entries_to_csv
export_entries_to_csv(entries, "/mnt/user-data/outputs/leads-2026-10-05.csv")
```

Offer when the user wants to slice the data themselves or hand leads to sales.

## Multi-format delivery

When a request names several formats ("HTML and PDF"), build them in one `build_report` call with a list of paths, then `present_files` with all of them.

## Legacy v1 builders

`scripts/build_pdf.py`, `scripts/build_pptx.py` and `templates/report-shell.html` still work for v1 summaries. Use them only to re-render an old v1 summary exactly as it was. New reports use `build_report.py` (the `classic` theme reproduces the v1 look).
