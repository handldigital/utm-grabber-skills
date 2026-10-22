# Themes: four looks, every report, every format

Every report renders in any of four themes. The theme changes the look (type, surfaces, card style, how the brand color is used). It never changes the numbers or the story. HTML, PDF and PowerPoint all follow the theme.

| Theme | Feels like | Best for | Type |
|---|---|---|---|
| `studio` (default) | Bright and friendly. The brand color fills a slim header bar (the cover, in PDF and PowerPoint); every change reads in plain English ("Up 14% from August"). | Client-facing reports, small-business owners, agencies sending to clients | Rubik + Work Sans |
| `boardroom` | Dark and cinematic. Tall condensed numbers, glowing charts. | Presenting on a big screen, leadership meetings, quarterly reviews | Barlow + Barlow Condensed |
| `ledger` | Dense and exact. Section titles in a left rail, tabular figures that line up, compact tables. | Operators and analysts, weekly ops reviews, agency internal | IBM Plex Sans + Condensed + Mono |
| `classic` | The original v1 design, preserved: two-tone cards, italic serif numbers, uppercase mono labels. | Customers who already know the v1 look; long printed reads | Instrument Serif + Geist + Geist Mono |

Web pages use a dashboard layout in every theme: a slim header, the KPI band, then panels side by side (`references/output-formats.md`). PDF and PowerPoint keep their page and slide layouts.

## How the theme is chosen

1. The theme the user asks for in this request ("make it in Boardroom", "the dark one", "the original design").
2. `summary["meta"]["theme"]`.
3. The saved brand profile's `theme` (set during `/brand`). Old profiles: `"light"` maps to `classic`, `"gradient"` maps to `boardroom`.
4. Default: `studio`.

Natural-language mapping: "dark", "presentation", "exec", "board" = boardroom. "dense", "detailed", "analyst", "spreadsheet-y" = ledger. "original", "old", "classic", "serif", "v1" = classic. "bright", "client", "friendly", "modern" = studio.

When a user asks to "see the styles" or "show me the designs", render the same report in all four themes and present them together (one HTML each), then ask which one to save as their default.

## Brand colors in every theme

Each theme takes the brand profile's colors and derives everything else, so any brand works:

- Text in the brand color is darkened (light themes) or lightened (dark theme) until it passes WCAG AA contrast. A mustard-yellow brand still produces readable kickers.
- Chart colors start with the brand color, then add hues from a validated palette, checked for color-blind separation. Charts never show more than 6 colors; extra series fold into "Other".
- Black or gray brands get a neutral slate as their chart color instead of an invented hue.
- Studio's cover puts white or near-black text on the brand color, whichever reads better.

## Fonts in each format

- **HTML and PDF:** fonts are embedded in the file. They render the same everywhere, offline included. No font CDN is ever called.
- **PowerPoint:** fonts are embedded in the .pptx. PowerPoint for Mac and Windows shows the exact typefaces even when they are not installed.
- **Google Slides:** every theme font is a Google Font, so Slides shows the right typeface automatically.
- **Keynote:** Keynote ignores embedded fonts and substitutes Helvetica when a font is not installed. Layouts are sized with room for that, so nothing overflows; the deck just looks plainer. For the exact look in Keynote, the user installs the theme's free fonts (double-click each file in `assets/fonts/ttf/`, then Install). Offer this only if a Keynote user asks why the fonts look different.

## Rules that hold in every theme

- One `*accent*` per title. Studio and Boardroom color it with the brand; Classic sets it in italic brand color; Ledger renders it plain (its readers want numbers, not emphasis).
- Charts: bars at most 24px thick, 2px lines, hairline gridlines, no second y-axis, labels in text colors (never the series color), legends whenever there are 2+ series.
- Status colors (good, warning, bad) always come with an icon and a word, never color alone.
- Numbers auto-fit their tiles. A long value shrinks instead of clipping.
