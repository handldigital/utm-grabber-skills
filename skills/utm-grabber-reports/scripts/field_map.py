"""
Field map: which raw form field is which attribution field, per form.

get_entries returns each entry the way its form plugin stores it. Gravity Forms
entries are flat and keyed by numeric field id; WPForms, Ninja, Formidable,
Fluent, Elementor, Contact Form 7 and others nest the answers under `fields` and
date them with `date`. Field labels are whatever the site owner typed, and some
plugins send none. The same field can be spelled four ways on one site
("handl_original_ref (HandL)", "HandL ( handl_original_ref )", ...).

So the skill maps fields once per site and form, then every recipe reads the
same canonical names (references/data-dictionary.md):

    suggest(entries, field_labels)    -> a draft map from labels, keys and values
    apply(entries, field_labels, fmap) -> entries with canonical keys added
    to_memory(fmap, domain) / from_memory(lines) -> compact memory lines

CLI, for the setup step (references/mcp-usage.md, "Map the fields first"):

    python3 field_map.py PAGE_FILE [PAGE_FILE ...]    prints the draft per form
"""
import json
import re
from collections import Counter
from datetime import datetime, timezone

# Canonical name -> short code (memory lines are capped at 500 characters).
CANONICAL = {
    "Date Created": "d", "Email": "em",
    "utm_source (HandL)": "us", "utm_medium (HandL)": "um", "utm_campaign (HandL)": "uc",
    "utm_content (HandL)": "ux", "utm_term (HandL)": "ut", "traffic_source (HandL)": "ts",
    "gclid (HandL)": "gc", "fbclid (HandL)": "fb", "msclkid (HandL)": "ms", "wbraid (HandL)": "wb",
    "gbraid (HandL)": "gb", "ttclid (HandL)": "tt",
    "handl_landing_page (HandL)": "lp", "referrer (HandL)": "rf", "Source URL": "su",
    "organic_source_str (HandL)": "os", "handl_ref_domain (HandL)": "rd", "user_agent (HandL)": "ua",
    "utm_source (first touch, HandL)": "fus", "utm_medium (first touch, HandL)": "fum",
    "utm_campaign (first touch, HandL)": "fuc", "utm_content (first touch, HandL)": "fux",
    "utm_term (first touch, HandL)": "fut", "traffic_source (first touch, HandL)": "fts",
    "landing_page (first touch, HandL)": "flp", "referrer (first touch, HandL)": "frf",
    "date (first touch, HandL)": "fd",
}
_CODE = {v: k for k, v in CANONICAL.items()}

# Normalized field token -> canonical name. Tokens come from labels or keys via token().
_TOKENS = {}
for _f in ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"):
    _TOKENS[_f] = "%s (HandL)" % _f
    _TOKENS["first_" + _f] = "%s (first touch, HandL)" % _f
for _f in ("gclid", "fbclid", "msclkid", "wbraid", "gbraid", "ttclid"):
    _TOKENS[_f] = "%s (HandL)" % _f
_TOKENS.update({
    "traffic_source": "traffic_source (HandL)", "first_traffic_source": "traffic_source (first touch, HandL)",
    "handl_landing_page": "handl_landing_page (HandL)", "landing_page": "handl_landing_page (HandL)",
    "first_landing_page": "landing_page (first touch, HandL)",
    "handl_ref": "referrer (HandL)", "referrer": "referrer (HandL)",
    "handl_original_ref": "referrer (first touch, HandL)", "original_ref": "referrer (first touch, HandL)",
    "original_referrer": "referrer (first touch, HandL)", "first_referrer": "referrer (first touch, HandL)",
    "handl_url": "Source URL", "source_url": "Source URL",
    "organic_source_str": "organic_source_str (HandL)", "organic_source": "organic_source_str (HandL)",
    "handl_ref_domain": "handl_ref_domain (HandL)", "user_agent": "user_agent (HandL)",
    "first_date": "date (first touch, HandL)", "first_visit": "date (first touch, HandL)",
    "handl_first_visit": "date (first touch, HandL)",
})

# Raw keys that are entry metadata, never answers.
_META = {"id", "entry_id", "form_id", "status", "is_starred", "is_read", "ip", "source_url", "user_agent_raw",
         "created_by", "date_updated", "payment_status", "fields", "post_id", "currency", "param_keys", "item_id"}
_DATE_KEYS = ("date_created", "date", "created_at", "submitted_at", "entry_date", "created")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)


def token(name):
    """'utm_source (first touch, HandL)' -> 'first_utm_source'; 'HandL ( handl_original_ref )' -> 'handl_original_ref'."""
    s = str(name or "").strip().lower()
    first = bool(re.search(r"first[ _-]?touch", s))
    s = re.sub(r"\(\s*first[ _-]?touch\s*,?\s*(handl)?\s*\)", " ", s)
    s = re.sub(r"\(\s*handl\s*\)", " ", s)
    m = re.match(r"^\s*handl\s*\(\s*(.*?)\s*\)\s*$", s)
    if m:
        s = m.group(1)
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    if first and not s.startswith("first_"):
        s = "first_" + s
    return s


def _unwrap(v):
    """WPForms and Divi wrap each answer: {"name"/"label": ..., "value": ..., ...}. Return the answer."""
    return v.get("value") if isinstance(v, dict) and "value" in v else v


def _flat(e):
    """Top-level keys plus the plugin's nested `fields` answers, top level winning on clashes."""
    nested = e.get("fields") if isinstance(e.get("fields"), dict) else {}
    out = {str(k): _unwrap(v) for k, v in nested.items()}
    out.update({str(k): v for k, v in e.items() if k not in ("fields", "param_keys")})
    return out


def _labels_for(e, field_labels):
    """The form's field_labels, plus the names wrapped answers carry (WPForms "name", Divi "label")
    for keys the labels don't cover."""
    labels = dict((field_labels or {}).get(str(e.get("form_id", "") or ""), {}))
    nested = e.get("fields") if isinstance(e.get("fields"), dict) else {}
    for k, v in nested.items():
        if isinstance(v, dict) and "value" in v and str(k) not in labels:
            name = v.get("label") or v.get("name")
            if isinstance(name, str) and name.strip():
                labels[str(k)] = name.strip()
    return labels


def _param_keys(rows_raw):
    """{canonical: raw_key} from the plugin's own param_keys (OptimizePress and other stored forms)."""
    out = {}
    for e in rows_raw:
        pk = e.get("param_keys") if isinstance(e.get("param_keys"), dict) else {}
        for param, key in pk.items():
            c = _TOKENS.get(token(param))
            if c and key not in (None, "") and c not in out:
                out[c] = str(key)
    return out


def _filled(v):
    return v is not None and str(v).strip() != ""


def _canonical_for(raw_key, label):
    for t in (token(label), token(raw_key)):
        if t in _TOKENS:
            return _TOKENS[t]
        if "email" in t.split("_") or t.endswith("email"):
            return "Email"
    return None


def suggest(entries, field_labels=None):
    """Draft map per form from labels, keys and sample values.

    Returns {form_id: {"date": raw_key, "fields": {canonical: raw_key},
                       "unmapped": {raw_key: {"label": str, "samples": [..]}}}}.
    The AI reviews "unmapped" (and anything that looks wrong), fixes the map,
    confirms it with the customer and saves it with to_memory().
    """
    field_labels = field_labels or {}
    by_form, raw_by_form, labels_by_form = {}, {}, {}
    for e in entries:
        fid = str(e.get("form_id", "") or "")
        by_form.setdefault(fid, []).append(_flat(e))
        raw_by_form.setdefault(fid, []).append(e)
        lab = labels_by_form.setdefault(fid, dict(field_labels.get(fid, {})))
        for k, v in _labels_for(e, field_labels).items():
            lab.setdefault(k, v)
    out = {}
    for fid, rows in by_form.items():
        labels = labels_by_form[fid]
        known = _param_keys(raw_by_form[fid])     # the plugin says which field holds each parameter
        filled, samples = Counter(), {}
        for r in rows:
            for k, v in r.items():
                if _filled(v):
                    filled[k] += 1
                    if len(samples.setdefault(k, [])) < 3 and str(v)[:60] not in samples[k]:
                        samples[k].append(str(v)[:60])
                else:
                    filled[k] += 0
        date_key = next((k for k in _DATE_KEYS if filled.get(k)), None)
        cands = {}
        for k in filled:
            if k in _META or k in _DATE_KEYS:
                continue
            looks_email = bool(samples.get(k)) and all(_EMAIL_RE.match(s) for s in samples[k])
            c = _canonical_for(k, labels.get(k, k))
            if c == "Email" and samples.get(k) and not looks_email:
                c = None                      # "email_opt_in: yes" is not the address
            if c is None and looks_email:
                c = "Email"
            if c:
                cands.setdefault(c, []).append(k)
        fields = {c: k for c, k in known.items() if filled.get(k)}
        for c, keys in cands.items():
            if c in fields:
                continue
            keys.sort(key=lambda k: (-filled[k], "handl" not in str(labels.get(k, k)).lower(), k))
            fields[c] = keys[0]
        used = set(fields.values())
        unmapped = {k: {"label": str(labels.get(k, k)), "samples": samples.get(k, [])}
                    for k in filled if k not in used and k not in _META and k not in _DATE_KEYS and filled[k]}
        out[fid] = {"date": date_key, "fields": fields, "unmapped": unmapped}
    return out


def _date(v):
    """Normalize a submission date to 'YYYY-MM-DD HH:MM:SS' when the format is unambiguous."""
    s = str(v or "").strip()
    if not s:
        return ""
    if re.fullmatch(r"\d{10}(\d{3})?", s):
        ts = int(s) / (1000 if len(s) == 13 else 1)
        return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    m = re.match(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}(:\d{2})?)", s)
    if m:
        return "%s %s" % (m.group(1), m.group(2) if m.group(3) else m.group(2) + ":00")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s + " 00:00:00"
    for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y", "%B %d, %Y %H:%M", "%B %d, %Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    return s


def apply(entries, field_labels=None, fmap=None):
    """Entries with readable keys plus every canonical name the map knows.

    Keys go through field_labels as before, nested `fields` are flattened, and
    each mapped raw field is renamed in place to its canonical name, so a lead
    profile never lists "UTM Source" twice. A canonical value the entry already
    has is never overwritten, so already-named data (demo data, Gravity's own
    HandL labels) comes back unchanged. Forms missing from fmap use the suggest()
    draft.
    """
    field_labels = field_labels or {}
    fmap = dict(fmap or {})
    missing = {str(e.get("form_id", "") or "") for e in entries} - set(fmap)
    if missing:
        draft = suggest([e for e in entries if str(e.get("form_id", "") or "") in missing], field_labels)
        fmap.update(draft)
    out = []
    for e in entries:
        fid = str(e.get("form_id", "") or "")
        labels = _labels_for(e, field_labels)
        raw = _flat(e)
        named = {k: labels.get(k, k) for k in raw}
        m = fmap.get(fid) or {}
        rename = {}
        for canon, rk in (m.get("fields") or {}).items():
            rk = str(rk)
            if not _filled(raw.get(rk)) or named[rk] == canon:
                continue
            if any(named[k] == canon and _filled(raw[k]) for k in raw):
                continue                       # the entry already carries this name
            rename[rk] = canon
        ne = {}
        for k, v in raw.items():               # rename in place: same order, no duplicate answers
            nk = rename.get(k, named[k])
            if nk in ne and _filled(ne[nk]) and not _filled(v):
                continue
            ne[nk] = v
        if not _filled(ne.get("Date Created")):
            dk = m.get("date") or next((k for k in _DATE_KEYS if _filled(raw.get(k))), None)
            if dk and _filled(raw.get(dk)):
                ne["Date Created"] = _date(raw[dk])
        if fid and "Form ID" not in ne:
            ne["Form ID"] = fid
        if e.get("source_url") and "Source URL" not in ne:
            ne["Source URL"] = e["source_url"]
        out.append(ne)
    return out


MEMORY_PREFIX = "[utm-grabber-field-map]"


def to_memory(fmap, domain):
    """One compact memory line per form: '[utm-grabber-field-map] acme.com f=1 d=date_created us=3 ...'."""
    lines = []
    for fid, m in sorted(fmap.items()):
        parts = ["%s %s f=%s" % (MEMORY_PREFIX, (domain or "").lower(), fid or "-")]
        if m.get("date"):
            parts.append("d=%s" % m["date"])
        for canon, rk in sorted(m.get("fields", {}).items(), key=lambda x: CANONICAL.get(x[0], x[0])):
            if canon in CANONICAL and canon != "Date Created":
                parts.append("%s=%s" % (CANONICAL[canon], json.dumps(str(rk)) if " " in str(rk) else rk))
        lines.append(" ".join(parts))
    return lines


def from_memory(lines, domain=None):
    """Rebuild {form_id: {"date", "fields"}} from memory lines (other lines are ignored)."""
    fmap = {}
    for line in lines if isinstance(lines, (list, tuple)) else [lines]:
        line = str(line).strip()
        if not line.startswith(MEMORY_PREFIX):
            continue
        rest = line[len(MEMORY_PREFIX):].strip()
        dom, _, body = rest.partition(" ")
        if domain and dom != domain.lower():
            continue
        pairs = re.findall(r'(\w+)=("(?:[^"\\]|\\.)*"|\S+)', body)
        vals = {k: json.loads(v) if v.startswith('"') else v for k, v in pairs}
        fid = vals.pop("f", "")
        fid = "" if fid == "-" else fid
        m = {"date": vals.pop("d", None), "fields": {}}
        for code, rk in vals.items():
            if code in _CODE:
                m["fields"][_CODE[code]] = rk
        fmap[fid] = m
    return fmap


def describe(fmap):
    """A short plain-English table of the map, for confirming it with the customer."""
    rows = []
    for fid, m in sorted(fmap.items()):
        rows.append("Form %s: date from %s" % (fid or "?", m.get("date") or "(none found)"))
        for canon, rk in sorted(m.get("fields", {}).items(), key=lambda x: list(CANONICAL).index(x[0])
                                if x[0] in CANONICAL else 99):
            rows.append("  %-36s <- %s" % (canon, rk))
        for rk, info in (m.get("unmapped") or {}).items():
            rows.append("  (unmapped) %-25s label %r, e.g. %s" % (rk, info["label"], ", ".join(info["samples"])))
    return "\n".join(rows)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
    from helpers import _read_mcp_text, _extract_entries_array, _extract_field_labels
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    ents, labs = [], {}
    for fp in sys.argv[1:]:
        text = _read_mcp_text(fp)
        for fid, mp in _extract_field_labels(text).items():
            labs.setdefault(fid, {}).update(mp)
        ents.extend(_extract_entries_array(text))
    draft = suggest(ents, labs)
    print(describe(draft))
    print("\nJSON:", json.dumps({f: {"date": m["date"], "fields": m["fields"]} for f, m in draft.items()}))
