"""Dev tool: every report reads the same numbers from the raw shapes form plugins send.

    python3 scripts/dev/test_field_map.py [--reports monthly,qbr] [--shapes gravity,wpforms]

Turns the named demo leads into raw get_entries pages, loads them back with
load_entries, builds every report and compares each summary with the one built
from the named demo data. Shapes (references/mcp-usage.md, "Map the fields first"):

  gravity    flat, numeric field ids + Field labels. First touch spelled the way the
             plugin sends it (first_utm_source (HandL)...), and the original referrer
             spelled differently on each form.
  wpforms    {date, form_id, fields: {...}} with owner-typed labels ("UTM Source",
             "First UTM Source", "Original Referrer", "Your Email"). Each answer is
             wrapped the way WPForms stores it: {"name", "value", "id", "type"}.
  divi       {date, form_id, fields: {...}} with no Field labels, each answer wrapped
             as {"value": ...} (the Divi adapter reads processed_fields_values[k]["value"]).
  store      the plugin's own submission store (OptimizePress): no labels and
             meaningless keys, plus the plugin's param_keys {"utm_source": "x_07", ...}
             saying which field holds each tracked parameter. No saved map.
  elementor  {date, form_id, fields: {...}} with no Field labels: the keys are the
             names (utm_source, first_utm_source, handl_original_ref, your-email).
  opaque     no labels and meaningless keys (f_3a, f_9c...). The draft can't read
             these, so the test passes the field map the AI would save after
             confirming it with the customer.

Also unit-checks token(), the email guard and the memory round trip.
Exit code 1 when any check fails.
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, HERE)

import demo_data_v2  # noqa: E402
import field_map  # noqa: E402
from demo_v2 import REPORTS, demo_summary  # noqa: E402
from helpers import load_entries  # noqa: E402

FAIL = []


def check(name, ok, detail=""):
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name, ("  (%s)" % detail) if detail else ""))
    if not ok:
        FAIL.append(name)


# ---- unit checks ------------------------------------------------------------------
for spelling in ("handl_original_ref (HandL)", "HandL ( handl_original_ref )", "Handl_original_ref",
                 "handl_original_ref"):
    check("token reads %r as the original referrer" % spelling,
          field_map._TOKENS.get(field_map.token(spelling)) == "referrer (first touch, HandL)")
check("token reads first-touch labels", field_map.token("utm_source (first touch, HandL)") == "first_utm_source"
      and field_map.token("first_utm_source (HandL)") == "first_utm_source")
opt = field_map.suggest([{"form_id": "1", "date": "2026-10-01 10:00:00",
                          "fields": {"email_opt_in": "yes", "contact": "a@b.co"}}])["1"]["fields"]
check("an email opt-in checkbox is not the email field", opt.get("Email") == "contact", opt)
fm = {"7": {"date": "date", "fields": {"utm_source (first touch, HandL)": "f 9", "Email": "e1"}}}
lines = field_map.to_memory(fm, "Acme.com")
check("memory lines fit in 500 characters", all(len(x) <= 500 for x in lines), [len(x) for x in lines])
check("memory round trip", field_map.from_memory(lines, "acme.com") == fm, lines)

# ---- raw shapes -------------------------------------------------------------------
HANDL = [k for k in field_map.CANONICAL if k not in ("Date Created", "Email", "Source URL")]
REF = {"1": "handl_original_ref (HandL)", "2": "HandL ( handl_original_ref )", "3": "Handl_original_ref"}
GRAVITY_LABEL = {
    "utm_source (first touch, HandL)": "first_utm_source (HandL)",
    "utm_medium (first touch, HandL)": "first_utm_medium (HandL)",
    "utm_campaign (first touch, HandL)": "first_utm_campaign (HandL)",
    "traffic_source (first touch, HandL)": "first_traffic_source (HandL)",
    "landing_page (first touch, HandL)": "first_landing_page (HandL)",
}
WPFORMS_LABEL = {
    "utm_source (HandL)": "UTM Source", "utm_medium (HandL)": "UTM Medium", "utm_campaign (HandL)": "utm_campaign",
    "utm_content (HandL)": "UTM Content", "utm_term (HandL)": "utm term", "gclid (HandL)": "GCLID",
    "fbclid (HandL)": "fbclid", "msclkid (HandL)": "MSCLKID", "wbraid (HandL)": "wbraid",
    "traffic_source (HandL)": "Traffic Source", "handl_landing_page (HandL)": "Landing Page",
    "organic_source_str (HandL)": "organic_source_str", "handl_ref_domain (HandL)": "handl_ref_domain",
    "user_agent (HandL)": "User Agent", "utm_source (first touch, HandL)": "First UTM Source",
    "utm_medium (first touch, HandL)": "First UTM Medium", "utm_campaign (first touch, HandL)": "First UTM Campaign",
    "traffic_source (first touch, HandL)": "First Traffic Source",
    "landing_page (first touch, HandL)": "First Landing Page", "referrer (first touch, HandL)": "Original Referrer",
    "Source URL": "handl_url", "Email": "Your Email",
}
ELEMENTOR_KEY = {
    "handl_landing_page (HandL)": "handl_landing_page", "referrer (first touch, HandL)": "handl_original_ref",
    "landing_page (first touch, HandL)": "first_landing_page", "Source URL": "handl_url", "Email": "your-email",
}
for k in HANDL:
    base = k.replace(" (first touch, HandL)", "").replace(" (HandL)", "")
    ELEMENTOR_KEY.setdefault(k, ("first_" + base) if "first touch" in k else base)


# store shape: meaningless keys; the plugin's param_keys name the tracked parameters (not the email)
STORE_KEY = {k: "x_%02x" % (i + 1) for i, k in enumerate(HANDL)}
STORE_KEY["Email"] = "x_em"
STORE_PARAMS = {ELEMENTOR_KEY[k]: STORE_KEY[k] for k in HANDL if k in ELEMENTOR_KEY}


def raw_entry(e, shape, ids):
    fid = str(e.get("Form ID") or "1")
    date = e.get("Date Created", "")
    if shape == "gravity":
        r = {"form_id": fid, "date_created": date}
        for k, v in e.items():
            if k in ("Form ID", "Date Created"):
                continue
            if k == "Source URL":
                r["source_url"] = v
                continue
            label = REF.get(fid, k) if k == "referrer (first touch, HandL)" else GRAVITY_LABEL.get(k, k)
            r[ids.setdefault((fid, label), str(len([x for x in ids if x[0] == fid]) + 1))] = v
        return r
    fields = {}
    for k, v in e.items():
        if k in ("Form ID", "Date Created"):
            continue
        if shape == "wpforms":
            label = WPFORMS_LABEL.get(k, k)
            num = ids.setdefault((fid, label), str(len([x for x in ids if x[0] == fid]) + 1))
            fields[num] = {"name": label, "value": v, "id": int(num), "type": "hidden"}
        elif shape == "elementor":
            fields[ELEMENTOR_KEY.get(k, k)] = v
        elif shape == "divi":
            fields[ELEMENTOR_KEY.get(k, k)] = {"value": v}
        elif shape == "store":
            fields[STORE_KEY.get(k, k)] = v
        else:                                    # opaque: HandL fields and email get meaningless keys
            fields[("f_%02x" % (HANDL.index(k) + 16)) if k in HANDL else ("e_addr" if k == "Email" else k)] = v
    row = {"form_id": fid, "date": date, "fields": fields}
    if shape == "store":
        row["param_keys"] = STORE_PARAMS
    return row


def opaque_map(form_ids):
    m = {"date": "date", "fields": {k: "f_%02x" % (HANDL.index(k) + 16) for k in HANDL}}
    m["fields"]["Email"] = "e_addr"
    return {fid: m for fid in form_ids}


def page_files(raw, labels, tmp, shape):
    paths = []
    for i in range(0, len(raw), 400):
        p = os.path.join(tmp, "%s-%d.txt" % (shape, i // 400))
        with open(p, "w") as f:
            if labels:
                f.write("Field labels: %s\n" % json.dumps(labels))
            f.write("Page %d of %d (400 per page, %d total matching entries).\nEntries: %s\n"
                    % (i // 400 + 1, (len(raw) + 399) // 400, len(raw), json.dumps(raw[i:i + 400])))
        paths.append(p)
    return paths


ORIG = demo_data_v2.get_dataset
SHAPE = {"name": None}
_CACHE = {}


def raw_dataset(name):
    ds = dict(ORIG(name))
    shape = SHAPE["name"]
    if not shape:
        return ds
    key = (name, shape)
    if key not in _CACHE:
        uniq, order = {}, []
        for k in ("leads", "leads_prior", "leads_history"):
            for e in ds.get(k) or []:
                if id(e) not in uniq:
                    uniq[id(e)] = e
                    order.append(id(e))
        ids = {}
        raw = [raw_entry(uniq[i], shape, ids) for i in order]
        labels = {}
        for (fid, label), num in ids.items():
            labels.setdefault(fid, {})[num] = label
        tmp = tempfile.mkdtemp()
        fmap = opaque_map({r["form_id"] for r in raw}) if shape == "opaque" else None
        loaded = load_entries(page_files(raw, labels, tmp, shape), field_map=fmap)
        _CACHE[key] = dict(zip(order, loaded))
    conv = _CACHE[key]
    for k in ("leads", "leads_prior", "leads_history"):
        if ds.get(k):
            ds[k] = [conv[id(e)] for e in ds[k]]
    return ds


demo_data_v2.get_dataset = raw_dataset


def scrub(o):
    if isinstance(o, dict):
        return {k: scrub(v) for k, v in o.items() if k not in ("generated_at", "built_at")}
    if isinstance(o, list):
        return [scrub(v) for v in o]
    return o


def opt(name, default):
    for i, a in enumerate(sys.argv):
        if a == name and i + 1 < len(sys.argv):
            return sys.argv[i + 1].split(",")
    return default


reports = opt("--reports", REPORTS)
shapes = opt("--shapes", ["gravity", "wpforms", "elementor", "divi", "store", "opaque"])
SHAPE["name"] = None
want = {r: json.dumps(scrub(demo_summary(r)), sort_keys=True, default=str) for r in reports}
for shape in shapes:
    SHAPE["name"] = shape
    bad = []
    for r in reports:
        got = json.dumps(scrub(demo_summary(r)), sort_keys=True, default=str)
        if got != want[r]:
            bad.append(r)
    check("%s shape: %d reports match the named data" % (shape, len(reports)), not bad,
          "differ: " + ", ".join(bad) if bad else "")
SHAPE["name"] = None

print("\n%s" % ("All checks passed" if not FAIL else "%d check(s) failed" % len(FAIL)))
sys.exit(1 if FAIL else 0)
