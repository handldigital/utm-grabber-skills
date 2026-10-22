"""Dev tool: when Chromium can't start (Codex's macOS sandbox), the other formats still build.

    python3 scripts/dev/test_pdf_unavailable.py

Makes Playwright's Chromium launch fail the way Codex's sandbox does, asks for
HTML + PDF + PPTX in one build_report call, and checks: PdfUnavailable is raised,
its message says PDF_UNAVAILABLE and names the built files, the HTML and PPTX
exist, and no PDF was written. Exit code 1 when any check fails.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from playwright.sync_api._generated import BrowserType  # noqa: E402

from build_report import build_report  # noqa: E402
from demo_v2 import demo_summary  # noqa: E402
from engine.pdf_render import PdfUnavailable  # noqa: E402


def blocked(self, *a, **k):
    raise RuntimeError("bootstrap_check_in org.chromium.Chromium.MachPortRendezvousServer: "
                       "Permission denied (1100)")


BrowserType.launch = blocked
out = tempfile.mkdtemp()
paths = [os.path.join(out, "monthly." + x) for x in ("html", "pdf", "pptx")]
err = None
try:
    build_report(demo_summary("monthly"), paths, theme="studio")
except PdfUnavailable as e:
    err = e

checks = [
    ("PdfUnavailable raised", err is not None),
    ("message starts PDF_UNAVAILABLE", bool(err) and str(err).startswith("PDF_UNAVAILABLE")),
    ("message names what was built", bool(err) and paths[0] in str(err) and paths[2] in str(err)),
    ("HTML built", os.path.exists(paths[0])),
    ("PowerPoint built after the failed PDF", os.path.exists(paths[2])),
    ("no PDF written", not os.path.exists(paths[1])),
]
for name, ok in checks:
    print("%s  %s" % ("PASS" if ok else "FAIL", name))
print(str(err)[:400] if err else "")
sys.exit(0 if all(ok for _, ok in checks) else 1)
