"""
Validate a v2 report summary against references/report-schema.md.

    from validate_v2 import validate
    errors = validate(summary)            # [] when clean

    python scripts/validate_v2.py summary.json

Checks structure (known section types, required fields, list sizes), the
writing rules (exactly one *accent* per title, no em dashes anywhere, no
'undefined'/'NaN'/'None' leaking into text) and chart data shapes.
"""
import json
import re
import sys

KNOWN = {"title-block", "stat-strip", "hero-number", "section-header", "chart", "chart-insight",
         "ranked-list", "table", "recommendations", "insight-card", "closing", "funnel", "flow",
         "sankey", "heatmap", "matrix", "comparison", "timeline", "scorecard", "callouts", "notes"}
CHART_TYPES = {"doughnut", "donut", "pie", "bar-horizontal", "bar-vertical", "bar-stacked", "bar-grouped",
               "line", "area", "line-multi", "waterfall", "bar-diverging", "scatter", "sankey", "heatmap", "funnel"}
TITLE_FIELDS = {"title-block": ["title"], "section-header": ["title"], "chart-insight": ["insight_title"],
                "insight-card": ["title"], "closing": ["title"], "funnel": ["insight_title"],
                "matrix": ["insight_title"]}
BAD_WORDS = re.compile(r"\b(undefined|NaN|None|null)\b|\[object Object\]")
_ACC = re.compile(r"\*[^*]+\*")


def _strings(obj, path="$"):
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("logo",):
                continue
            yield from _strings(v, "%s.%s" % (path, k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _strings(v, "%s[%d]" % (path, i))


def _accent_ok(text):
    return len(_ACC.findall(text or "")) == 1


def _numeric_list(v):
    return isinstance(v, list) and all(isinstance(x, (int, float)) or x is None for x in v)


def _check_chart(c, ctx, errs):
    if not isinstance(c, dict):
        errs.append("%s: chart must be an object" % ctx)
        return
    t = c.get("type")
    if t not in CHART_TYPES:
        errs.append("%s: unknown chart type %r" % (ctx, t))
        return
    if t in ("doughnut", "donut", "pie", "bar-horizontal", "bar-vertical", "line", "area", "bar-diverging"):
        if not isinstance(c.get("labels"), list) or not _numeric_list(c.get("values")):
            errs.append("%s: %s needs labels + numeric values" % (ctx, t))
        elif len(c["labels"]) != len(c["values"]):
            errs.append("%s: labels/values length mismatch" % ctx)
    if t == "bar-stacked" and not c.get("stacks"):
        errs.append("%s: bar-stacked needs stacks" % ctx)
    if t == "bar-grouped" and not c.get("groups"):
        errs.append("%s: bar-grouped needs groups" % ctx)
    if t == "line-multi":
        for s in c.get("series") or []:
            if not _numeric_list(s.get("values")):
                errs.append("%s: line-multi series %r needs numeric values" % (ctx, s.get("label")))
    if t == "waterfall" and not c.get("steps"):
        errs.append("%s: waterfall needs steps" % ctx)


def validate(summary):
    errs = []
    if not isinstance(summary, dict):
        return ["summary must be a dict"]
    m = summary.get("meta")
    if not isinstance(m, dict):
        errs.append("meta missing")
        m = {}
    for k in ("brand_profile", "skill_version", "generated_at"):
        if k not in m:
            errs.append("meta.%s missing" % k)
    secs = summary.get("sections")
    if not isinstance(secs, list) or not secs:
        return errs + ["sections missing or empty"]
    if secs[0].get("type") != "title-block":
        errs.append("first section must be title-block")
    if secs[-1].get("type") != "closing":
        errs.append("last section must be closing")
    for i, s in enumerate(secs):
        t = s.get("type")
        ctx = "sections[%d] (%s)" % (i, t)
        if t not in KNOWN:
            errs.append("%s: unknown section type" % ctx)
            continue
        for f in TITLE_FIELDS.get(t, []):
            if s.get(f) is not None and not _accent_ok(s.get(f)):
                errs.append("%s: %s needs exactly one *accent*: %r" % (ctx, f, s.get(f)))
        if t == "title-block" and not s.get("title"):
            errs.append("%s: title required" % ctx)
        if t == "stat-strip":
            st = s.get("stats") or []
            if not 2 <= len(st) <= 6:
                errs.append("%s: 2 to 6 stats (got %d)" % (ctx, len(st)))
            for j, x in enumerate(st):
                if not x.get("label") or x.get("value") in (None, ""):
                    errs.append("%s: stat %d needs label + value" % (ctx, j))
                if x.get("spark") is not None and not _numeric_list(x.get("spark")):
                    errs.append("%s: stat %d spark must be numbers" % (ctx, j))
        if t in ("chart", "chart-insight"):
            _check_chart(s.get("chart"), ctx, errs)
        if t in ("ranked-list", "table"):
            cols = s.get("columns") or []
            keys = {c.get("key") for c in cols}
            if not cols:
                errs.append("%s: columns required" % ctx)
            for j, r in enumerate(s.get("rows") or []):
                missing = [k for k in keys if k not in r]
                if missing:
                    errs.append("%s: row %d missing %s" % (ctx, j, missing))
        if t == "recommendations":
            it = s.get("items") or []
            if not 2 <= len(it) <= 6:
                errs.append("%s: 2 to 6 items (got %d)" % (ctx, len(it)))
            for j, x in enumerate(it):
                if not _accent_ok(x.get("title")):
                    errs.append("%s: item %d title needs exactly one *accent*" % (ctx, j))
        if t == "closing":
            if len(s.get("summary_stats") or []) > 4:
                errs.append("%s: at most 4 summary_stats" % ctx)
            if len(s.get("bullets") or []) > 4:
                errs.append("%s: at most 4 bullets" % ctx)
        if t == "funnel":
            st = s.get("stages") or []
            if len(st) < 2:
                errs.append("%s: funnel needs 2+ stages" % ctx)
            for x in st:
                if not isinstance(x.get("value"), (int, float)):
                    errs.append("%s: funnel stage values must be numbers" % ctx)
                    break
        if t in ("flow", "sankey"):
            if not s.get("links"):
                errs.append("%s: links required" % ctx)
        if t == "heatmap":
            rows, cols, vals = s.get("rows") or [], s.get("cols") or [], s.get("values") or []
            if len(vals) != len(rows) or any(len(r) != len(cols) for r in vals):
                errs.append("%s: values must be rows x cols" % ctx)
        if t == "matrix":
            pts = s.get("points") or []
            if not pts:
                errs.append("%s: points required" % ctx)
            groups = {p.get("group") for p in pts if p.get("group") is not None}
            if len(groups) > 3:
                errs.append("%s: at most 3 groups" % ctx)
        if t == "comparison" and not s.get("rows"):
            errs.append("%s: rows required" % ctx)
        if t == "scorecard":
            for x in s.get("items") or []:
                if x.get("status") not in ("pass", "warn", "fail", "info", "good", "bad"):
                    errs.append("%s: bad status %r" % (ctx, x.get("status")))
    for path, text in _strings(summary):
        if "—" in text:
            errs.append("em dash in %s: %r" % (path, text[:80]))
        if BAD_WORDS.search(text) and not path.endswith("customer_domain"):
            errs.append("suspicious value in %s: %r" % (path, text[:80]))
    return errs


if __name__ == "__main__":
    with open(sys.argv[1]) as f:
        e = validate(json.load(f))
    print("\n".join(e) if e else "OK")
    sys.exit(1 if e else 0)
