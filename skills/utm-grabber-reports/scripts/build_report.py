"""
One entry point for every report, every theme, every format.

    from build_report import build_report
    build_report(summary, "/mnt/user-data/outputs/monthly-2026-10-05.html", theme="studio")
    build_report(summary, "/mnt/user-data/outputs/monthly-2026-10-05.pdf",  theme="studio")
    build_report(summary, "/mnt/user-data/outputs/monthly-2026-10-05.pptx", theme="studio")

    # several at once (same summary, no recompute):
    build_report(summary, ["out/r.html", "out/r.pdf", "out/r.pptx"], theme="boardroom")

CLI:
    python scripts/build_report.py summary.json out.html [out.pdf out.pptx] [--theme ledger] [--paper a4]
                                   [--layout document]

Theme: explicit argument > summary.meta.theme > brand_profile.theme > "studio".
HTML layout: "dashboard" (default: slim header, numbers on top, panels side by side)
or "document" (one long read, like the PDF): layout= argument > summary.meta.layout.
A path ending in .artifact.html writes the page without its document skeleton, ready to
publish as a claude.ai Artifact (references/artifact-delivery.md).
Themes: studio, boardroom, ledger, classic (the original v1 design).
The legacy v1 renderers (templates/report-shell.html, build_pdf.py, build_pptx.py)
are kept untouched and still work for v1 summaries.
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from engine.themes import THEME_INFO, pick_theme  # noqa: E402


def build_report(summary, out, theme=None, paper=None, validate=True, layout=None):
    """Render summary to one path or a list of paths (format from the extension)."""
    paths = out if isinstance(out, (list, tuple)) else [out]
    key = pick_theme(theme, summary)
    if validate:
        try:
            from validate_v2 import validate as _v
            errs = _v(summary)
            if errs:
                sys.stderr.write("report schema: %d issue(s), rendering anyway\n  %s\n" %
                                 (len(errs), "\n  ".join(errs[:8])))
        except Exception:
            pass
    done, pdf_error = [], None
    for p in paths:
        ext = os.path.splitext(p)[1].lower()
        if ext in (".html", ".htm"):
            from engine.html_render import write_html
            write_html(summary, p, key, layout)
        elif ext == ".pdf":
            from engine.pdf_render import build_pdf, PdfUnavailable
            try:
                build_pdf(summary, p, key, paper)
            except PdfUnavailable as e:      # build the other formats, then say so
                pdf_error = e
                continue
        elif ext == ".pptx":
            from engine.pptx_render import build_pptx
            build_pptx(summary, p, key)
        else:
            raise ValueError("Unsupported output %r (use .html, .pdf or .pptx)" % p)
        done.append(p)
    if pdf_error:
        raise type(pdf_error)("%s Built: %s. Tell the user the PDF couldn't be made in this app and offer the "
                              "web page (they can save it as a PDF from their browser's print menu) or the "
                              "PowerPoint. Never make a PDF any other way." % (pdf_error, ", ".join(done) or "nothing"))
    return done if isinstance(out, (list, tuple)) else done[0]


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    opts = {}
    for i, a in enumerate(argv):
        if a.startswith("--") and "=" in a:
            k, v = a[2:].split("=", 1)
            opts[k] = v
        elif a.startswith("--") and i + 1 < len(argv):
            opts[a[2:]] = argv[i + 1]
            if argv[i + 1] in args:
                args.remove(argv[i + 1])
    if len(args) < 2:
        print(__doc__)
        print("Themes: " + ", ".join("%s (%s)" % (k, v["best_for"]) for k, v in THEME_INFO.items()))
        return 1
    with open(args[0]) as f:
        summary = json.load(f)
    for p in build_report(summary, args[1:], opts.get("theme"), opts.get("paper"), layout=opts.get("layout")):
        print("Wrote " + p)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
