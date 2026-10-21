"""
Dev tool: build every report in every theme and format from the demo data, and
check it.

    python scripts/dev/test_matrix.py OUT_DIR [--reports a,b] [--themes studio,ledger]
                                              [--formats html,pdf,pptx] [--snap] [--mobile]

Checks per report:
  * the recipe runs and returns a summary that passes validate_v2 (no schema or
    writing-rule violations)
  * HTML/PDF/PPTX build without exceptions; PDF page count; PPTX slide count
  * with --snap: Chromium layout checks on every HTML (desktop, and phone with
    --mobile): no console errors, no clipped text, no horizontal overflow, no
    "undefined/NaN/None" in visible text
Writes OUT_DIR/results.json and prints a table. Needs the Bash sandbox off for
PDF and --snap (headless Chromium).
"""
import json
import os
import subprocess
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, HERE)

from demo_v2 import REPORTS, demo_summary  # noqa: E402
from validate_v2 import validate  # noqa: E402
from build_report import build_report  # noqa: E402

THEMES = ["studio", "boardroom", "ledger", "classic"]


def _opt(name, default):
    for i, a in enumerate(sys.argv):
        if a == name and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return default


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    reports = _opt("--reports", ",".join(REPORTS)).split(",")
    themes = _opt("--themes", ",".join(THEMES)).split(",")
    formats = _opt("--formats", "html").split(",")
    results = {}
    htmls = []
    from recipes_v2 import RECIPES
    for r in reports:
        if r not in RECIPES:
            results[r] = {"status": "missing recipe"}
            continue
        for t in themes:
            key = "%s-%s" % (r, t)
            res = {"report": r, "theme": t}
            try:
                t0 = time.time()
                s = demo_summary(r, t)
                res["recipe_s"] = round(time.time() - t0, 2)
                errs = validate(s)
                res["schema_errors"] = errs
                res["sections"] = len(s.get("sections") or [])
                for f in formats:
                    p = os.path.join(out, "%s.%s" % (key, f))
                    t1 = time.time()
                    build_report(s, p, theme=t, validate=False)
                    res["%s_s" % f] = round(time.time() - t1, 2)
                    if f == "html":
                        htmls.append(p)
                    if f == "pdf":
                        try:
                            info = subprocess.run(["pdfinfo", p], capture_output=True, text=True).stdout
                            res["pdf_pages"] = int([l for l in info.splitlines() if l.startswith("Pages")][0].split()[-1])
                        except Exception:
                            pass
                    if f == "pptx":
                        from pptx import Presentation
                        res["slides"] = len(Presentation(p).slides)
                res["status"] = "ok" if not errs else "schema"
            except Exception as exc:
                res["status"] = "error"
                res["error"] = "%s: %s" % (type(exc).__name__, exc)
                res["trace"] = traceback.format_exc()[-1500:]
            results[key] = res
            print("%-40s %-7s %s" % (key, res["status"], (res.get("error") or "; ".join(res.get("schema_errors", [])[:2]))[:150]))
    if "--snap" in sys.argv and htmls:
        from snap import run
        import asyncio
        shots = os.path.join(out, "shots")
        chk = asyncio.run(run(shots, htmls, False))
        if "--mobile" in sys.argv:
            chk.update(asyncio.run(run(shots, htmls, True)))
        for k, v in chk.items():
            base = k[:-2] if k.endswith("-m") else k
            bad = v.get("errors") or v.get("clipped") or v.get("bad") or v.get("overflowX", 0) > 0
            results.setdefault(base, {})["snap" + ("_m" if k.endswith("-m") else "")] = "ok" if not bad else {
                kk: vv for kk, vv in v.items() if vv and kk != "height"}
            if bad:
                print("LAYOUT %-34s %s" % (k, json.dumps({kk: vv for kk, vv in v.items() if vv and kk != "height"})[:220]))
    with open(os.path.join(out, "results.json"), "w") as f:
        json.dump(results, f, indent=1, default=str)
    bad = [k for k, v in results.items() if v.get("status") != "ok"]
    print("\n%d builds, %d not ok" % (len(results), len(bad)))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
