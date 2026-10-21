"""
Leads and forms v2 recipes: tracking audit, lead quality scorer, single-lead
profile and form performance.

Same pattern as core.py:
  1. Guard empty input -> common.empty_report(). Fewer than 10 leads to work with
     -> a short, honest version that says why.
  2. Compute every number from the inputs (never invent one).
  3. Outcome-first headline with exactly one *accent*.
  4. Sections in reading order; each answers one question.
  5. Recommendations come from thresholds in the data, highest impact first.
  6. The closing title is a concrete next step with the number behind it.

Privacy: emails are always masked (j***@domain.com), phone numbers keep only
their last four digits, IP addresses and user agents are never printed.
"""
import datetime as _dt
import re
from collections import Counter, defaultdict

from .common import (daily_counts, delta, empty_report, entry_dt, first_touch, get_field, last_touch, lead_campaign,
                     lead_content, lead_platform, lead_source_medium, lead_term, n, norm_key, pct, period_label,
                     pretty, share, stat)
from .common import lead_email as _lead_email
from .paid_media import (MIN_LEADS, URGENT_WORDS, _brand_forms, _change_badge, _click_platform, _days,
                         _delta_cell, _has_phrase, _in_period, _kick, _md, _norm_text, _plural, _safe, _setup,
                         _short, _src_name, _untagged, _vs, _weekly, _weeks, classify_intent, landing_of, page_path)
from helpers import compute_hygiene  # noqa: E402  (common puts scripts/ on sys.path)

PAID_MEDIUMS = {"cpc", "ppc", "paid", "paid_search", "paidsearch", "sem", "paid_social", "paidsocial",
                "social_paid", "paid-social", "cpm", "display"}
NON_CAMPAIGN_MEDIUMS = {"organic", "referral", "direct", "none", "(none)", "seo", "organic_search", "(not set)"}
META_SOURCES = {"facebook", "fb", "instagram", "ig", "meta", "messenger"}
SHORT_CHECK = {"coverage": "UTM coverage on campaign traffic", "lost": "paid clicks without UTMs",
               "gclid": "Google click ID capture", "fbclid": "Meta click ID capture",
               "case": "one spelling per value", "typo": "campaign name typos", "pages": "landing pages losing tags"}


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------
def _mask(em):
    """'jane.doe@acme.com' -> 'j***@acme.com'."""
    em = str(em or "").strip()
    if "@" not in em:
        return "–"
    local, dom = em.split("@", 1)
    return "%s***@%s" % (local[:1] or "*", _safe(dom.lower(), 40))


def _mask_phone(v):
    digits = re.sub(r"\D", "", str(v or ""))
    return "***-***-%s" % digits[-4:] if len(digits) >= 7 else "–"


def _when(dt):
    """datetime -> 'Sep 3, 12:09pm' (time only when the data has one)."""
    s = "%s %d" % (dt.strftime("%b"), dt.day)
    if dt.hour or dt.minute or dt.second:
        s += ", %d:%02d%s" % (dt.hour % 12 or 12, dt.minute, "am" if dt.hour < 12 else "pm")
    return s


def _ref_domain(url):
    u = re.sub(r"^[a-z][a-z0-9+.-]*://", "", str(url or "").strip(), flags=re.I)
    return u.split("/")[0].split("?")[0].lower().replace("www.", "")


_SYSTEM = re.compile(r"handl|utm_|clid|braid|ip address|^ip$|user.?agent|source.?url|^date|^form.?(id|title|name)|^entry.?id|"
                     r"^id$|^status$|is starred|is read|post.?id|created by|^currency|^payment|transaction|"
                     r"landing.?page|referrer|traffic.?source|^source$|^medium$|^campaign$", re.I)


def _fields(e):
    """Form fields a person typed (no attribution, system or numeric-id keys), in entry order."""
    out = []
    for k, v in e.items():
        if not isinstance(k, str) or k.strip().isdigit() or _SYSTEM.search(k):
            continue
        out.append((k, "" if v is None else str(v).strip()))
    return out


def _find(e, patterns):
    """(key, value) of the first form field whose name contains any pattern."""
    for k, v in _fields(e):
        kl = k.lower()
        if any(p in kl for p in patterns):
            return k, v
    return None, ""


def _person(e):
    first = get_field(e, "First Name", "first_name", "First name", "Name (First)")
    last = get_field(e, "Last Name", "last_name", "Last name", "Name (Last)")
    full = " ".join(x for x in (first, last) if x)
    if not full:
        full = get_field(e, "Name", "Full Name", "Your Name", "name", "full_name")
    return _safe(full, 32)


def _source_tag(e):
    src, med = lead_source_medium(e)
    if src or med:
        return _safe("%s / %s" % (src or "(none)", med or "(none)"), 30)
    return last_touch(e).lower()


def _is_campaign_traffic(e):
    """Leads that should carry a campaign tag: ad clicks, and any medium other than organic/referral/direct."""
    if _click_platform(e):
        return True
    src, med = lead_source_medium(e)
    if not (src or med or lead_campaign(e)):
        return False
    if med in NON_CAMPAIGN_MEDIUMS:
        return False
    if not med and (src in ("google", "bing", "duckduckgo", "yahoo", "ecosia", "brave") or "." in src):
        return False   # search engines, and sites that auto-tag only utm_source (chatgpt.com, perplexity.ai)
    return True


# ---------------------------------------------------------------------------
# TRACKING AUDIT (UTM hygiene)
# ---------------------------------------------------------------------------
def _lev(a, b, cap=2):
    """Levenshtein distance, giving up (cap + 1) once it is past cap."""
    if a == b:
        return 0
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        best = cur[0]
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            best = min(best, cur[j])
        if best > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def _typo_pairs(counter, limit=150):
    """Campaign names one or two edits apart. Numbered series (q1/q2) and short deliberate
    variants (_us/_uk, _a/_b) are left out."""
    keys = [k for k, _ in counter.most_common(limit)]
    out = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = keys[i], keys[j]
            if min(len(a), len(b)) < 6 or abs(len(a) - len(b)) > 2:
                continue
            if re.sub(r"\d", "", a) == re.sub(r"\d", "", b):
                continue
            ta, tb = a.split("_"), b.split("_")
            if len(ta) == len(tb):
                diff = [(x, y) for x, y in zip(ta, tb) if x != y]
                if len(diff) == 1 and max(len(diff[0][0]), len(diff[0][1])) <= 3:
                    continue
            d = _lev(a, b)
            if 1 <= d <= 2:
                out.append((a, b, d))
    return out


def _typo_names(counter):
    """{suspect: (target, edits)}: each name that is a typo apart from a campaign with more leads
    (or, on a tie, its alphabetical neighbor). A suspect keeps its biggest neighbor."""
    out = {}
    for a, b, d in _typo_pairs(counter):
        small, big = (a, b) if (counter[a], b) < (counter[b], a) else (b, a)
        if small in out and counter[out[small][0]] >= counter[big]:
            continue
        out[small] = (big, d)
    return out


def build_audit(current, prior=None, brand_profile=None, customer_name=None, customer_domain="",
                compare_label=None, prepared_by=None, prepared_for=None, **_):
    """Tracking health: how many leads arrive fully tagged, and the specific leaks to fix first."""
    prior, start, end, m = _setup(current, prior, brand_profile, customer_name, customer_domain,
                                  compare_label, prepared_by, prepared_for)
    name = "Tracking audit"
    if not current:
        return empty_report(name, m)
    period = period_label(start, end)
    kicker = _kick(name, period)
    days = _days(start, end)
    when = _in_period(start, end)
    has_prior = bool(prior)
    total = len(current)
    m["sources"] = [{"name": "UTM Grabber", "detail": "%s leads audited" % n(total)}]

    hyg = {id(e): compute_hygiene(e) for e in current}
    cats = Counter(hyg.values())
    full = cats["fully_tagged"]
    cov = share(full, total)
    cov_p = share(sum(1 for e in prior if compute_hygiene(e) == "fully_tagged"), len(prior)) if prior else None
    untagged = [e for e in current if _untagged(e)]
    lost = [e for e in current if hyg[id(e)] == "untagged_paid"]
    has_ref = any(get_field(e, "referrer (first touch, HandL)", "referrer") for e in current)

    # ---- checks, in fix-priority order of the scorecard
    checks = []
    camp_t = [e for e in current if _is_campaign_traffic(e)]
    camp_full = sum(1 for e in camp_t if hyg[id(e)] == "fully_tagged")
    miss = Counter()
    for e in camp_t:
        if hyg[id(e)] != "fully_tagged":
            src, med = lead_source_medium(e)
            for f, v in (("utm_source", src), ("utm_medium", med), ("utm_campaign", lead_campaign(e))):
                if not v:
                    miss[f] += 1
    if camp_t:
        r = share(camp_full, len(camp_t))
        det = "%s of %s leads from ads, email and social carried source, medium and campaign." % (n(camp_full), n(len(camp_t)))
        if miss:
            f, k = miss.most_common(1)[0]
            det += " Most often missing: %s (%s)." % (f, _plural(k, "lead"))
        checks.append({"key": "coverage", "label": "Full UTM coverage on campaign traffic", "value": pct(r),
                       "status": "pass" if r >= 90 else ("warn" if r >= 70 else "fail"), "detail": det, "rate": r})
    else:
        checks.append({"key": "coverage", "label": "Full UTM coverage on campaign traffic", "value": "–",
                       "status": "info", "detail": "No lead came from an ad, email or social campaign in this period."})

    click_leads = [e for e in current if _click_platform(e)]
    lost_plat = Counter(_click_platform(e) for e in lost)
    lost_pages = Counter(landing_of(e)[0] or "(no page)" for e in lost)
    if lost:
        lp, lc = lost_plat.most_common(1)[0]
        det = "%s had a %s click ID but no UTMs, most often on %s." % (
            _plural(len(lost), "lead"), lp, _safe(lost_pages.most_common(1)[0][0], 40))
        st = "warn" if share(len(lost), len(click_leads)) < 5 else "fail"
    else:
        det = ("Every lead with an ad click ID also carried UTMs." if click_leads else
               "No lead carried an ad click ID in this period.")
        st = "pass" if click_leads else "info"
    checks.append({"key": "lost", "label": "Paid clicks that lost their UTMs", "value": n(len(lost)), "status": st,
                   "detail": det})

    def _cap_check(key, label, pool, has_id, platform, fix):
        if not pool:
            return {"key": key, "label": label, "value": "–", "status": "info",
                    "detail": "No %s leads in this period." % platform}
        k = sum(1 for e in pool if has_id(e))
        r = share(k, len(pool))
        det = "%s of %s %s leads carried it." % (n(k), n(len(pool)), platform)
        if r < 90:
            det += " " + fix
        return {"key": key, "label": label, "value": pct(r), "status": "pass" if r >= 90 else ("warn" if r >= 60 else "fail"),
                "detail": det, "rate": r, "pool": len(pool), "missing": len(pool) - k}

    g_pool = [e for e in current if lead_source_medium(e)[0] == "google" and lead_source_medium(e)[1] in PAID_MEDIUMS]
    checks.append(_cap_check("gclid", "Google click ID on Google Ads leads", g_pool,
                             lambda e: get_field(e, "gclid (HandL)", "gclid", "wbraid (HandL)", "gbraid (HandL)"),
                             "Google Ads", "Turn on auto-tagging in Google Ads and keep the gclid field on your forms."))
    f_pool = [e for e in current if lead_source_medium(e)[0] in META_SOURCES and lead_source_medium(e)[1] in PAID_MEDIUMS]
    checks.append(_cap_check("fbclid", "Meta click ID on Meta Ads leads", f_pool,
                             lambda e: get_field(e, "fbclid (HandL)", "fbclid"), "Meta Ads",
                             "Check redirects on your landing pages and keep the fbclid field on your forms."))

    variants = []
    for field, getter in (("utm_source", lambda e: get_field(e, "utm_source (HandL)", "utm_source")),
                          ("utm_medium", lambda e: get_field(e, "utm_medium (HandL)", "utm_medium")),
                          ("utm_campaign", lead_campaign)):
        g = defaultdict(Counter)
        for e in current:
            v = getter(e)
            if v:
                g[norm_key(v)][v] += 1
        for k, c in g.items():
            if len(c) > 1:
                variants.append((field, c))
    split_leads = sum(sum(c.values()) - c.most_common(1)[0][1] for _, c in variants)
    if variants:
        field, c = max(variants, key=lambda x: sum(x[1].values()))
        sp = [s for s, _ in c.most_common(3)]
        det = "%s are counted as different values in %s. Analytics tools split them, so each looks smaller than it is." % (
            " and ".join("\"%s\"" % _safe(s, 24) for s in sp), field)
        st = "fail" if share(split_leads, total) >= 10 else "warn"
    else:
        det, st = "Every source, medium and campaign is spelled one way.", "pass"
    checks.append({"key": "case", "label": "One spelling per source, medium and campaign", "value": n(len(variants)),
                   "status": st, "detail": det})

    camp_c = Counter(norm_key(lead_campaign(e)) for e in current if lead_campaign(e))
    typos = _typo_names(camp_c)
    typo_leads = sum(camp_c[k] for k in typos)
    if typos:
        a = max(typos, key=lambda k: (camp_c[k], k))
        b = typos[a][0]
        det = "%s split %s off their real campaign. Biggest: \"%s\" next to \"%s\" (%s and %s)." % (
            _plural(len(typos), "misspelled name"), _plural(typo_leads, "lead"), _safe(a, 30), _safe(b, 30),
            _plural(camp_c[a], "lead"), _plural(camp_c[b], "lead"))
        st = "fail" if share(typo_leads, total) >= 5 else "warn"
    else:
        det, st = "No campaign name is a typo away from another.", "pass"
    checks.append({"key": "typo", "label": "Campaign names that look like typos", "value": n(len(typos)),
                   "status": st, "detail": det})

    pages = defaultdict(list)
    for e in current:
        p = landing_of(e)[0]
        if p:
            pages[p].append(e)
    bad_pages = sorted([p for p, v in pages.items() if len(v) >= 3 and share(sum(1 for e in v if _untagged(e)), len(v)) >= 50],
                       key=lambda p: -sum(1 for e in pages[p] if _untagged(e)))
    if bad_pages:
        det = "Half or more of the leads on %s arrived with no UTMs." % " and ".join(_safe(p, 36) for p in bad_pages[:2])
        st = "warn" if len(bad_pages) <= 2 else "fail"
    elif pages:
        det, st = "No landing page lost tags on half or more of its leads.", "pass"
    else:
        det, st = "No lead recorded a landing page.", "info"
    checks.append({"key": "pages", "label": "Landing pages losing tags", "value": n(len(bad_pages)), "status": st,
                   "detail": det})

    applicable = [c for c in checks if c["status"] != "info"]
    passed = [c for c in applicable if c["status"] == "pass"]
    to_fix = [c for c in applicable if c["status"] in ("fail", "warn")]
    fails = [c for c in applicable if c["status"] == "fail"]

    # ---- title
    if lost:
        headline = "%s from paid clicks arrived with no *UTMs* %s." % (_plural(len(lost), "lead"), when)
    elif to_fix:
        headline = "*%s* of your leads arrived fully tagged, with %s to fix." % (pct(cov), _plural(len(to_fix), "check"))
    elif cov >= 60 and len(applicable) >= 4:
        headline = "Every tracking *check* passed %s." % when
    else:
        headline = "*%s* of your leads arrived fully tagged." % pct(cov)
    sub = "%s of %s checks passed%s." % (n(len(passed)), n(len(applicable)),
                                          "; %s did not apply" % n(len(checks) - len(applicable))
                                          if len(checks) > len(applicable) else "")
    if to_fix:
        worst = (fails or to_fix)[0]
        sub += " Fix first: %s." % SHORT_CHECK[worst["key"]]
    elif len(applicable) < 4:
        sub += " The other checks had nothing to measure: no ad clicks, campaign traffic or landing pages were recorded."
    else:
        rest = [e for e in current if hyg[id(e)] != "fully_tagged"]
        organic = sum(1 for e in rest if not _is_campaign_traffic(e))
        sub += " %s of leads arrived fully tagged; %s of the other %s were organic, referral or direct visits, " \
               "which never carry a campaign." % (pct(cov), n(organic), n(len(rest)))
    secs = [{"type": "title-block", "kicker": kicker, "title": headline, "subtitle": sub,
             "meta_bits": [b for b in [customer_domain, "%s leads audited" % n(total), "%d days" % days if days else ""] if b]}]

    weeks = _weeks(start, end)
    spark = None
    if len(weeks) >= 3:
        tot_w = _weekly(current, weeks)
        full_w = _weekly([e for e in current if hyg[id(e)] == "fully_tagged"], weeks)
        spark = [round(share(f, t), 1) for f, t in zip(full_w, tot_w)]
    hero = {"type": "hero-number", "kicker": "Tracking health score", "value": pct(cov),
            "label": "of %s arrived fully tagged: source, medium and campaign. %s had no UTMs at all." % (
                _plural(total, "lead"), n(len(untagged)))}
    if has_prior and cov_p is not None:
        hero.update({k: v for k, v in delta(cov, cov_p, kind="pts").items() if k != "good"})
    if spark:
        hero["spark"] = spark
    secs.append(hero)
    if total < MIN_LEADS:
        secs[0]["title"] = "Spot check: %s of %s leads arrived fully *tagged*." % (n(full), n(total))
        return {"meta": m, "sections": secs + [
            {"type": "scorecard", "title": "Tracking *health*",
             "items": [{"label": c["label"], "value": c["value"], "status": c["status"], "detail": c["detail"]}
                       for c in checks]},
            {"type": "insight-card", "kicker": "Why this report is short", "title": "Treat this as a *spot check*.",
             "body": ["With %s, one lead moves every percentage by %s." % (_plural(total, "lead"), pct(100.0 / total)),
                      "The checks still point at real problems; rerun the full audit at %d leads or more." % MIN_LEADS]},
            {"type": "closing", "kicker": "Next step",
             "title": "Next: rerun this *audit* once you pass %d leads." % MIN_LEADS}]}
    secs.append({"type": "stat-strip", "stats": [
        stat("Leads audited", n(total)),
        stat("No UTMs at all", n(len(untagged)), good="down", note="%s of leads" % pct(share(len(untagged), total))),
        stat("Paid clicks untagged", n(len(lost)), good="down", note="had a click ID, no UTMs"),
        stat("Checks passed", "%d of %d" % (len(passed), len(applicable)))]})

    # ---- 01 checks
    secs.append({"type": "section-header", "number": "01", "kicker": "The checks",
                 "title": "Seven checks on your *tracking*.",
                 "dek": "Each one names a specific leak and how many leads it touched."})
    secs.append({"type": "scorecard", "title": "Tracking *health*",
                 "items": [{"label": c["label"], "value": c["value"], "status": c["status"], "detail": c["detail"]}
                           for c in checks]})

    # ---- 02 where tags go missing
    secs.append({"type": "section-header", "number": "02", "kicker": "Where tags go missing",
                 "title": "How each *lead* arrived.",
                 "dek": "Every lead sorted into one tagging state."})
    if has_ref:
        labels = ["Fully tagged", "Partly tagged", "Ad click, no UTMs", "Referrer, no UTMs", "No UTMs, no referrer"]
        vals = [cats["fully_tagged"], cats["partially_tagged"], cats["untagged_paid"], cats["untagged_referrer"],
                cats["direct"]]
        notes_ = ["all three UTMs", "one or two missing", "click ID, no tags", "from another site", "typed in or lost"]
    else:
        labels = ["Fully tagged", "Partly tagged", "Ad click, no UTMs", "No UTMs"]
        vals = [cats["fully_tagged"], cats["partially_tagged"], cats["untagged_paid"],
                cats["untagged_referrer"] + cats["direct"]]
        notes_ = ["all three UTMs", "one or two missing", "click ID, no tags", "no click ID"]
    gap_i = max(range(1, len(vals)), key=lambda i: vals[i])
    body = []
    if gap_i == 1:
        part = [e for e in current if hyg[id(e)] == "partially_tagged"]
        mm = Counter()
        for e in part:
            src, med = lead_source_medium(e)
            for f, v in (("utm_source", src), ("utm_medium", med), ("utm_campaign", lead_campaign(e))):
                if not v:
                    mm[f] += 1
        f, k = mm.most_common(1)[0] if mm else ("utm_campaign", 0)
        organic = sum(1 for e in part if not _is_campaign_traffic(e))
        ititle = "*Partly tagged* leads are the biggest gap: %s." % pct(share(vals[1], total))
        body.append("Most of them lack %s (%s)." % (f, _plural(k, "lead")))
        if organic:
            body.append("%s are organic, referral or direct visits, which never carry a campaign. Judge the rest." %
                        n(organic))
    else:
        ititle = "*%s* of leads arrived with no UTMs." % pct(share(vals[gap_i], total))
        body.append("Some are typed-in visits; others lost their tags through redirects or untagged links.")
    if lost:
        body.append("%s came from a paid click with no tags: the costliest leak, because you paid for the click." %
                    _plural(len(lost), "lead"))
    secs.append({"type": "chart-insight",
                 "chart": {"type": "bar-horizontal", "labels": labels, "values": vals, "x_title": "Leads",
                           "highlight": gap_i if vals[gap_i] else 0, "notes": notes_, "total": total},
                 "caption": "Every lead %s, by tagging state" % when,
                 "insight_kicker": "The biggest gap", "insight_title": ititle, "insight_body": body[:3]})

    leak_pages = sorted([p for p in pages if sum(1 for e in pages[p] if _untagged(e)) >= 2
                         or any(_click_platform(e) for e in pages[p] if _untagged(e))],
                        key=lambda p: (-sum(1 for e in pages[p] if _untagged(e)), p))
    if leak_pages:
        rows = []
        for i, p in enumerate(leak_pages[:10]):
            v = pages[p]
            u = [e for e in v if _untagged(e)]
            lo = [e for e in u if _click_platform(e)]
            refs = Counter(_ref_domain(get_field(e, "referrer (first touch, HandL)", "referrer")) for e in u
                           if get_field(e, "referrer (first touch, HandL)", "referrer"))
            if lo:
                fix = "Add UTMs to %s ad URLs" % Counter(_click_platform(e) for e in lo).most_common(1)[0][0]
            elif refs:
                fix = "Tag links from %s" % _safe(refs.most_common(1)[0][0], 28)
            else:
                fix = "Tag the links and redirects into this page"
            rows.append({"rank": str(i + 1), "page": _safe(p, 56), "untagged": {"value": len(u), "label": n(len(u))},
                         "share": pct(share(len(u), len(v))), "lost": n(len(lo)), "fix": fix})
        secs.append({"type": "ranked-list", "title": "Pages losing the most *tags*",
                     "columns": [{"key": "rank", "label": "#", "type": "rank"},
                                 {"key": "page", "label": "Landing page", "type": "source"},
                                 {"key": "untagged", "label": "No UTMs", "type": "bar"},
                                 {"key": "share", "label": "Of page", "type": "pct", "align": "right"},
                                 {"key": "lost", "label": "Ad clicks", "type": "number", "align": "right"},
                                 {"key": "fix", "label": "Likely fix", "type": "text"}],
                     "rows": rows,
                     "caption": "Ad clicks: leads with a click ID and no UTMs. Pages are each lead's landing page."})
    part_camp = [e for e in camp_t if hyg[id(e)] == "partially_tagged"]
    if part_camp:
        g = defaultdict(list)
        for e in part_camp:
            src, med = lead_source_medium(e)
            g[_safe("%s / %s" % (src or "(none)", med or "(none)"), 30)].append(e)
        rows = []
        for i, (k, v) in enumerate(sorted(g.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:8]):
            mm = Counter()
            for e in v:
                src, med = lead_source_medium(e)
                for f, val in (("utm_source", src), ("utm_medium", med), ("utm_campaign", lead_campaign(e))):
                    if not val:
                        mm[f] += 1
            rows.append({"rank": str(i + 1), "src": k, "leads": {"value": len(v), "label": n(len(v))},
                         "missing": ", ".join(f for f, _ in mm.most_common()) or "–"})
        secs.append({"type": "ranked-list", "title": "Campaign traffic missing part of its *tags*",
                     "columns": [{"key": "rank", "label": "#", "type": "rank"},
                                 {"key": "src", "label": "Source / medium", "type": "source"},
                                 {"key": "leads", "label": "Leads", "type": "bar"},
                                 {"key": "missing", "label": "Missing", "type": "text"}],
                     "rows": rows, "caption": "Ads, email and social only. Organic, referral and direct visits are left out."})

    # ---- 03 fix order
    recs = []
    by_key = {c["key"]: c for c in checks}
    if lost:
        lp = lost_plat.most_common(1)[0][0]
        recs.append({"label": "This week", "title": "Add UTMs to *%s* ad URLs" % lp,
                     "body": "%s arrived from a paid click with no UTMs, most often on %s. Add utm_source, utm_medium "
                             "and utm_campaign to the final URL or tracking template." % (
                                 _plural(len(lost), "lead"), _safe(lost_pages.most_common(1)[0][0], 36)),
                     "impact": "High", "effort": "Low", "metric": "%s to recover" % _plural(len(lost), "lead")})
    c = by_key["gclid"]
    if c["status"] in ("fail", "warn"):
        recs.append({"label": "This week", "title": "Capture the *gclid* on every Google lead",
                     "body": "%s of %s Google Ads leads had no gclid, so Google can't match them to clicks. Turn on "
                             "auto-tagging and keep the gclid field on your forms." % (n(c["missing"]), n(c["pool"])),
                     "impact": "High", "effort": "Low"})
    c = by_key["fbclid"]
    if c["status"] in ("fail", "warn"):
        recs.append({"label": "This week", "title": "Capture the *fbclid* on Meta leads",
                     "body": "%s of %s Meta Ads leads had no fbclid. Check redirects on the landing page and keep "
                             "the fbclid field on your forms." % (n(c["missing"]), n(c["pool"])),
                     "impact": "Medium", "effort": "Low"})
    c = by_key["coverage"]
    if c["status"] in ("fail", "warn") and miss:
        f, k = miss.most_common(1)[0]
        recs.append({"label": "This month", "title": "Add *%s* to every campaign link" % f,
                     "body": "%s from ads, email and social arrived without it. Build links with a UTM builder "
                             "and one naming sheet." % _plural(k, "lead"),
                     "impact": "Medium", "effort": "Low"})
    if bad_pages:
        recs.append({"label": "This month", "title": "Tag the links into *%s*" % _safe(bad_pages[0], 36),
                     "body": "Half or more of its leads arrive with no UTMs. Find the ads, emails and posts that "
                             "point here and add tags.", "impact": "Medium", "effort": "Low"})
    if variants:
        field, cc = max(variants, key=lambda x: sum(x[1].values()))
        main_ = cc.most_common(1)[0][0]
        recs.append({"label": "This month", "title": "Use one spelling for *%s*" % _safe(main_.lower(), 30),
                     "body": "%s are split across %s spellings in %s. Pick lowercase and update the links." % (
                         _plural(sum(cc.values()), "lead"), n(len(cc)), field),
                     "impact": "Medium", "effort": "Low"})
    if typos:
        drop = max(typos, key=lambda k: (camp_c[k], k))
        keep, _d = typos[drop]
        others = len(typos) - 1
        recs.append({"label": "This month", "title": "Merge *%s* into %s" % (_safe(drop, 30), _safe(keep, 30)),
                     "body": "The names are %s apart and probably one campaign. Fix the link that uses it%s." % (
                         _plural(_d, "letter"), ("; %s more like it split %s" % (
                             _plural(others, "name"), _plural(typo_leads - camp_c[drop], "lead"))) if others else ""),
                     "impact": "Medium" if share(typo_leads, total) >= 5 else "Low", "effort": "Low"})
    recs = recs[:4]
    if len(recs) < 1:
        recs.append({"label": "Ongoing", "title": "Keep one *naming sheet* for every link",
                     "body": "Write down the allowed sources, mediums and campaign names, and build every link from it.",
                     "impact": "Low", "effort": "Low"})
    recs.append({"label": "Next month", "title": "Rerun this *audit* after the fixes",
                 "body": "Coverage was %s %s. Run the audit again in two weeks to confirm the fixes held." % (pct(cov), when),
                 "impact": "Low", "effort": "Low"})
    secs.append({"type": "section-header", "number": "03", "kicker": "Fix order", "title": "What to fix *first*."})
    secs.append({"type": "recommendations", "items": recs})
    notes = ["Fully tagged: utm_source, utm_medium and utm_campaign all present. Partly tagged: one or two of them.",
             "Campaign traffic means ad clicks plus any medium other than organic, referral or direct; organic visits "
             "never carry a campaign, so they are left out of the coverage check.",
             "Click ID checks: Google Ads leads are google with a paid medium; Meta Ads leads are facebook or instagram "
             "with a paid medium. Pass is 90% or more.",
             "Spelling check groups values that match once case and punctuation are ignored. Typo check flags campaign "
             "names one or two letters away from a bigger campaign, skipping numbered series and short variants like "
             "_us and _uk.",
             "Sites that add only utm_source on their own (chatgpt.com, perplexity.ai) count as referrals, not campaign traffic."]
    if not has_ref:
        notes.append("Referrers were not in this data, so leads with no UTMs can't be split into referred and direct visits.")
    if has_prior:
        notes.append("The score's change compares %s with %s." % (period, m["compare_label"]))
    secs.append({"type": "notes", "items": notes})

    if lost:
        close = "Next: add UTMs to *%s* ad URLs. %s arrived untagged." % (lost_plat.most_common(1)[0][0],
                                                                         _plural(len(lost), "paid click"))
    elif recs and to_fix:
        t = recs[0]["title"]
        close = "Next: %s. %s of %s checks passed." % (t[0].lower() + t[1:], n(len(passed)), n(len(applicable)))
    elif cov >= 60 and len(applicable) >= 4:
        close = "Next: keep your *tagging* rules as they are. All %s checks passed." % n(len(applicable))
    else:
        close = "Next: tag your ads and links with *UTMs*. Only %s of leads arrived fully tagged." % pct(cov)
    secs.append({"type": "closing", "kicker": "The audit in one line", "title": close,
                 "summary_stats": [{"value": pct(cov), "label": "Fully tagged"},
                                   {"value": n(len(untagged)), "label": "No UTMs"},
                                   {"value": n(len(lost)), "label": "Paid clicks untagged"},
                                   {"value": "%d of %d" % (len(passed), len(applicable)), "label": "Checks passed"}],
                 "bullets": ["%s of %s leads arrived fully tagged." % (n(full), n(total))] +
                            ["%s: %s." % ("Fix first" if i == 0 else "Then", SHORT_CHECK[c["key"]])
                             for i, c in enumerate((fails or to_fix)[:2])]})
    return {"meta": m, "sections": secs}


# ---------------------------------------------------------------------------
# LEAD QUALITY SCORER
# ---------------------------------------------------------------------------
HOT, WARM = 50, 25
BUDGET_KEYS = ("budget", "spend", "investment")
TIMEFRAME_KEYS = ("timeframe", "time frame", "timeline", "when do you", "start date", "urgency", "how soon")
SOFT_TIME_KEYS = ("preferred time", "best time", "availability", "appointment time")   # only "now" answers count
SERVICE_KEYS = ("service", "interested in", "interest", "treatment", "product", "looking for", "need help")
COMPANY_KEYS = ("company", "business name", "organization", "organisation")
PHONE_KEYS = ("phone", "mobile", "cell", "tel")
INTENT_PAGES = ("pricing", "price", "cost", "quote", "contact", "book", "appointment", "demo", "schedule",
                "consult", "emergency", "compare", "-vs-")
_TIMEFRAME_TIERS = ((20, "now", ("now", "immediately", "asap", "as soon as possible", "today", "this week", "urgent",
                                 "emergency", "right away")),
                    (14, "this month", ("this month", "30 days", "next month", "two weeks", "2 weeks", "few weeks",
                                        "soon")),
                    (8, "this quarter", ("60 days", "90 days", "quarter", "3 months", "three months", "few months")))
_EMPTY_ANSWERS = {"", "other", "not sure", "none", "n/a", "na", "-", "no", "0"}


def _budget_value(v):
    s = str(v or "").lower().replace(",", "")
    nums = []
    for mm in re.finditer(r"(\d+(?:\.\d+)?)\s*([km])?\b", s):
        x = float(mm.group(1))
        if mm.group(2) == "k":
            x *= 1e3
        elif mm.group(2) == "m":
            x *= 1e6
        nums.append(x)
    if not nums:
        return None
    if re.search(r"<|under|less than|up to|below", s):
        return max(nums) - 1
    return min(nums)


def _budget_text(raw, x):
    """'$25,000-$100,000/mo' -> '$25K+'; '<$1,000/mo' -> 'under $1,000'."""
    from .common import money as _money
    if x is None:
        return _safe(raw, 16)
    if re.search(r"<|under|less than|up to|below", str(raw).lower()):
        return "under %s" % _money(x + 1)
    return "%s+" % _money(x)


def _budget_points(x):
    if x is None:
        return 0
    if x >= 25000:
        return 25
    if x >= 5000:
        return 18
    if x >= 1000:
        return 10
    return 5 if x > 0 else 0


def _timing_text(v):
    t = _safe(v, 40).lower()
    t = re.sub(r"\bas soon as possible\b", "asap", t)
    return t if len(t) <= 16 else t[:15].rstrip() + "\u2026"


def _timeframe_points(v):
    t = _norm_text(v)
    if not t or t in _EMPTY_ANSWERS:
        return 0
    for pts, _label_, words in _TIMEFRAME_TIERS:
        if any(_has_phrase(t, w) for w in words):
            return pts
    return 2


def _ctx(entries, brand_forms):
    """Dataset-level facts the scorer needs: repeat counts and which signals exist at all."""
    reps = Counter(_lead_email(e) for e in entries if _lead_email(e))
    has = {"budget": any(_find(e, BUDGET_KEYS)[0] for e in entries[:300]),
           "timeframe": any(_find(e, TIMEFRAME_KEYS)[0] or _find(e, SOFT_TIME_KEYS)[0] for e in entries[:300]),
           "strict_timeframe": any(_find(e, TIMEFRAME_KEYS)[0] for e in entries[:300]),
           "service": any(_find(e, SERVICE_KEYS)[0] for e in entries[:300]),
           "company": any(_find(e, COMPANY_KEYS)[0] for e in entries[:300]),
           "phone": any(_find(e, PHONE_KEYS)[0] for e in entries[:300]),
           "term": any(lead_term(e) for e in entries),
           "first_touch": any(get_field(e, "landing_page (first touch, HandL)") for e in entries)}
    return {"reps": reps, "brand": brand_forms, "has": has}


def score_lead(e, ctx):
    """(score 0-100, [(points, reason, signal)]) from transparent, additive rules."""
    pts = []
    if lead_platform(e) in ("Google Ads", "Microsoft Ads"):
        pts.append((10, "Paid search", "paid"))
    term = lead_term(e)
    if term:
        it = classify_intent(term, ctx["brand"], [])
        if it == "Brand":
            pts.append((15, "Brand search", "brand"))
        elif it == "Problem or urgent":
            pts.append((15, "Urgent search", "urgent"))
    k, v = _find(e, BUDGET_KEYS)
    if k:
        bv = _budget_value(v)
        b = _budget_points(bv)
        if b:
            pts.append((b, "Budget %s" % _budget_text(v, bv), "budget"))
    k, v = _find(e, TIMEFRAME_KEYS)
    if k:
        t = _timeframe_points(v)
        if t:
            pts.append((t, "Timing: %s" % _timing_text(v), "timeframe"))
    else:
        k, v = _find(e, SOFT_TIME_KEYS)
        if k and _timeframe_points(v) == 20:
            pts.append((15, "Timing: %s" % _timing_text(v), "timeframe"))
    k, v = _find(e, SERVICE_KEYS)
    if k and _norm_text(v) not in _EMPTY_ANSWERS:
        if any(_has_phrase(_norm_text(v), w) for w in URGENT_WORDS):
            pts.append((15, "Urgent: %s" % _safe(v, 16).lower(), "urgent_need"))
        else:
            pts.append((10, "Wants %s" % _safe(v, 18).lower(), "service"))
    k, v = _find(e, PHONE_KEYS)
    if k and len(re.sub(r"\D", "", v)) >= 7:
        pts.append((5, "Phone given", "phone"))
    k, v = _find(e, COMPANY_KEYS)
    if k and _norm_text(v) not in _EMPTY_ANSWERS:
        pts.append((5, "Company given", "company"))
    em = _lead_email(e)
    if em and ctx["reps"].get(em, 0) >= 2:
        pts.append((15, "%d forms" % ctx["reps"][em], "repeat"))
    first_p = page_path(get_field(e, "landing_page (first touch, HandL)"))
    form_p = page_path(get_field(e, "Source URL", "source_url"))
    pages = [p for p in (first_p, landing_of(e)[0], form_p) if p]
    hit = next((p for p in pages if any(w in p for w in INTENT_PAGES)), None)
    if hit:
        pts.append((10, "Saw %s" % _safe(hit, 18), "page"))
    if first_p and form_p and first_p != form_p:
        pts.append((5, "Browsed first", "browsed"))
    return min(100, sum(p[0] for p in pts)), pts


SIGNAL_NAMES = {"urgent_need": "an urgent need on the form", "paid": "a paid search click", "brand": "a search for your name", "urgent": "an urgent search",
                "budget": "a stated budget", "timeframe": "a timeframe", "service": "a named service",
                "phone": "a phone number", "company": "a company name", "repeat": "more than one form",
                "page": "a pricing, contact or booking page visit", "browsed": "browsing before the form"}


def _ts(e):
    d = entry_dt(e)
    return (d - _dt.datetime(1970, 1, 1)).total_seconds() if d else 0.0


def _tier(s):
    if s >= HOT:
        return {"label": "Hot", "tone": "good"}
    if s >= WARM:
        return {"label": "Warm", "tone": "warn"}
    return {"label": "Cold", "tone": "neutral"}


def _device(e):
    ua = get_field(e, "user_agent (HandL)", "User Agent", "user_agent", "Device", "device", "device (HandL)").lower()
    if not ua:
        return None
    if any(k in ua for k in ("iphone", "android", "mobile", "ipod")):
        return "Mobile"
    if "ipad" in ua or "tablet" in ua:
        return "Tablet"
    return "Desktop"


def _who(e):
    who = _person(e) or _safe(get_field(e, "Company Name", "Company", "company"), 32)
    if who:
        return who
    if _lead_email(e):
        return _mask(_lead_email(e))
    eid = get_field(e, "Entry ID", "entry_id", "id")
    return ("Entry %s" % _safe(eid, 12)) if eid else "An unnamed lead"


def build_lead_scorer(current, prior=None, brand_profile=None, customer_name=None, customer_domain="",
                      compare_label=None, prepared_by=None, prepared_for=None, brand_terms=None, **_):
    """Rank every lead by transparent buying signals so sales knows who to call first."""
    prior, start, end, m = _setup(current, prior, brand_profile, customer_name, customer_domain,
                                  compare_label, prepared_by, prepared_for)
    name = "Lead quality scorer"
    if not current:
        return empty_report(name, m)
    period = period_label(start, end)
    kicker = _kick(name, period)
    days = _days(start, end)
    when = _in_period(start, end)
    m["sources"] = [{"name": "UTM Grabber", "detail": "%s submissions" % n(len(current))}]
    bforms = _brand_forms(m.get("customer_name"), customer_domain, brand_terms)
    ctx = _ctx(current, bforms)
    best = {}
    for i, e in enumerate(current):
        s, why = score_lead(e, ctx)
        key = _lead_email(e) or ("#%d" % i)
        if key not in best or (s, _ts(e)) > (best[key][0], _ts(best[key][2])):
            best[key] = (s, why, e)
    scored = sorted(best.values(), key=lambda x: (-x[0], -_ts(x[2])))
    total = len(scored)
    subs = len(current)
    hot = [x for x in scored if x[0] >= HOT]
    warm = [x for x in scored if WARM <= x[0] < HOT]
    cold = [x for x in scored if x[0] < WARM]
    avg = sum(x[0] for x in scored) / float(total)
    top = scored[0]

    def reasons(why, k=2, sep=" · "):
        rs = [r for _, r, _k in sorted(why, key=lambda x: -x[0])[:k]]
        if sep != " · ":
            rs = rs[:1] + [r[0].lower() + r[1:] for r in rs[1:]]
        return sep.join(rs) or "No buying signals"

    def row(i, x):
        s, why, e = x
        return {"who": _who(e), "email": _mask(_lead_email(e)), "src": _source_tag(e),
                "score": {"value": s, "label": n(s)}, "tier": _tier(s), "why": reasons(why)}

    cols = [{"key": "who", "label": "Lead", "type": "name"},
            {"key": "email", "label": "Email", "type": "source"},
            {"key": "src", "label": "Source", "type": "source"},
            {"key": "score", "label": "Score", "type": "bar", "max": 100},
            {"key": "tier", "label": "Tier", "type": "badge"},
            {"key": "why", "label": "Top reasons", "type": "text"}]
    absent = [lab for key, lab in (("budget", "budget"), ("timeframe", "timeframe"), ("service", "service"),
                                   ("phone", "phone"), ("term", "search terms")) if not ctx["has"][key]]
    rules = ["Paid search click (Google or Microsoft Ads) +10. Searched your name +15. Urgent or price words in the "
             "search term +15.",
             "Budget answer: +25 for $25,000 or more, +18 from $5,000, +10 from $1,000, +5 below that.",
             "Timeframe: +20 now or this week, +14 this month, +8 this quarter, +2 any other answer. A preferred-time "
             "answer like \"as soon as possible\" +15.",
             "Named a service +10, or +15 when it is urgent (emergency, pain, broken...). Left a phone number +5. "
             "Gave a company +5. Filled 2 or more forms +15.",
             "Visited a pricing, contact, booking, demo or comparison page +10. First landed on a different page than "
             "the form +5.",
             "Scores add up and cap at 100. Hot is %d or more, Warm %d to %d, Cold under %d." % (HOT, WARM, HOT - 1, WARM)]
    if absent:
        rules.append("Not in this data, so never scored: %s." % ", ".join(absent))
    if any(_device(e) for e in current[:200]):
        rules.append("Device is shown in the insight but not scored: it says how someone browsed, not how ready they are.")

    if total < MIN_LEADS:
        table = {"type": "ranked-list", "title": "Who to call *first*", "columns": cols,
                 "rows": [row(i, x) for i, x in enumerate(scored[:15])]}
        return {"meta": m, "sections": [
            {"type": "title-block", "kicker": kicker,
             "title": "Scored %s: *%s* is the one to call first." % (_plural(total, "lead"), _who(top[2])),
             "subtitle": "With %s the tiers are a rough guide, but the order still uses every signal we found." %
                         _plural(total, "lead"),
             "meta_bits": [b for b in [customer_domain, _plural(total, "lead"), "%d days" % days if days else ""] if b]},
            {"type": "stat-strip", "stats": [stat("Leads scored", n(total)), stat("Hot", n(len(hot))),
                                             stat("Top score", n(top[0]))]},
            table,
            {"type": "notes", "title": "How the score works", "items": rules},
            {"type": "closing", "kicker": "Next step",
             "title": "Next: call *%s*. Score %s: %s." % (_who(top[2]), n(top[0]), reasons(top[1], 2, ", ").lower()
                                                           if top[1] else "the best of this small batch")}]}

    prior_hot = None
    if prior:
        pctx = _ctx(prior, bforms)
        pbest = {}
        for i, e in enumerate(prior):
            key = _lead_email(e) or ("#%d" % i)
            pbest[key] = max(pbest.get(key, 0), score_lead(e, pctx)[0])
        prior_hot = sum(1 for v in pbest.values() if v >= HOT)
    _, daily = daily_counts(current, start, end)

    # ---- title
    if hot:
        headline = "%s scored *Hot*: call them first." % _plural(len(hot), "lead") if len(hot) > 1 else \
            "One lead scored *Hot*: call them first."
    else:
        headline = "No lead scored Hot yet; *%s* is the best to call." % _who(top[2])
    secs = [{"type": "title-block", "kicker": kicker, "title": headline,
             "subtitle": "%s %s%s: %s hot, %s warm and %s cold. The average score was %s of 100." % (
                 _plural(total, "lead"), when,
                 (" from %s" % _plural(subs, "submission")) if subs != total else "",
                 n(len(hot)), n(len(warm)), n(len(cold)), n(round(avg))),
             "meta_bits": [b for b in [customer_domain, "%s scored" % _plural(total, "lead"),
                                       "Hot = %d+" % HOT, "%d days" % days if days else ""] if b]}]
    secs.append({"type": "stat-strip", "stats": [
        stat("Leads scored", n(total), spark=daily,
             note=("from %s" % _plural(subs, "submission")) if subs != total else "one row per person"),
        stat("Hot", n(len(hot)), len(hot), prior_hot, note="%s of leads" % pct(share(len(hot), total))),
        stat("Warm", n(len(warm)), note="%s of leads" % pct(share(len(warm), total))),
        stat("Average score", n(round(avg)), note="out of 100")]})

    # ---- who to call first
    s0, why0, e0 = top
    d0 = entry_dt(e0)
    body = ["%s. Came from %s%s." % (reasons(why0, 3, ", "), _source_tag(e0), (" on " + _when(d0)) if d0 else "")]
    nxt = scored[1:3]
    if nxt:
        body.append("Then %s." % " and ".join("%s (%s)" % (_who(x[2]), n(x[0])) for x in nxt))
    devs = [_device(x[2]) for x in hot]
    if hot and any(devs):
        mob = sum(1 for d in devs if d == "Mobile")
        body.append("%s of the %s hot leads used a phone: call or text them rather than email." % (
            n(mob), n(len(hot))))
    secs.append({"type": "insight-card", "kicker": "Who to call first", "tone": "good" if s0 >= HOT else "neutral",
                 "title": "Call *%s* first: score %s." % (_who(e0), n(s0)), "body": body[:3]})

    # ---- 01 call list
    secs.append({"type": "section-header", "number": "01", "kicker": "Call list",
                 "title": "Your top *leads*, best first.",
                 "dek": "Scores add up buying signals from the form and the visit. Emails are masked."})
    secs.append({"type": "ranked-list", "title": "Top %d by *score*" % min(15, total), "columns": cols,
                 "rows": [row(i, x) for i, x in enumerate(scored[:15])],
                 "caption": "One row per person, using their best submission. Ties go to the most recent lead."})

    # ---- 02 distribution
    bins = [0] * 10
    for s, _w, _e in scored:
        bins[min(9, s // 10)] += 1
    labels = ["%d-%d" % (i * 10, i * 10 + 9) for i in range(9)] + ["90-100"]
    src_hot = Counter(_source_tag(x[2]) for x in hot)
    src_all = Counter(_source_tag(x[2]) for x in scored)
    hot_rate = share(len(hot), total)
    best_src = None
    for src_, c in src_all.most_common():
        if c >= 5 and src_hot.get(src_, 0) and share(src_hot[src_], c) >= 1.5 * max(hot_rate, 1):
            if best_src is None or share(src_hot[src_], c) > share(src_hot[best_src], src_all[best_src]):
                best_src = src_
    pool_sig = hot or scored[:max(1, total // 5)]
    sig_top, sig_all = Counter(), Counter()
    for _s, why, _e in pool_sig:
        for key in {k_ for _p, _r, k_ in why}:
            sig_top[key] += 1
    for _s, why, _e in scored:
        for key in {k_ for _p, _r, k_ in why}:
            sig_all[key] += 1
    lift = [(share(sig_top[k_], len(pool_sig)) / max(0.1, share(c_, total)), k_) for k_, c_ in sig_all.items()
            if share(sig_top[k_], len(pool_sig)) >= 30]
    ib = []
    if lift:
        _l, k_ = max(lift)
        ib.append("What sets %s apart: %s (%s of them, vs %s of all leads)." % (
            "hot leads" if hot else "your best leads", SIGNAL_NAMES[k_], pct(share(sig_top[k_], len(pool_sig))),
            pct(share(sig_all[k_], total))))
    if best_src:
        ib.append("%s leads score best: %s of them are hot, vs %s overall." % (
            best_src, pct(share(src_hot[best_src], src_all[best_src])), pct(hot_rate)))
    if cold:
        asks = [q for q, ok in (("a budget", ctx["has"]["budget"]), ("a timeframe", ctx["has"]["strict_timeframe"])) if ok]
        blank = sum(1 for _s, _w, e in cold
                    if (not ctx["has"]["budget"] or _budget_value(_find(e, BUDGET_KEYS)[1]) is None)
                    and (not ctx["has"]["strict_timeframe"] or not _timeframe_points(_find(e, TIMEFRAME_KEYS)[1])))
        if asks and share(blank, len(cold)) > 50:
            ib.append("%s of leads scored under %d; %s of them left %s blank." % (
                pct(share(len(cold), total)), WARM, pct(share(blank, len(cold))),
                " and ".join(q.replace("a ", "the ", 1) + " question" for q in asks)))
        else:
            ib.append("%s of leads scored under %d." % (pct(share(len(cold), total)), WARM))
    secs.append({"type": "section-header", "number": "02", "kicker": "Score spread",
                 "title": "How your *leads* stack up."})
    secs.append({"type": "chart-insight",
                 "chart": {"type": "bar-vertical", "labels": labels, "values": bins, "show_values": True},
                 "caption": "Leads per score band. Hot is %d or more, Warm %d to %d, Cold under %d." % (
                     HOT, WARM, HOT - 1, WARM),
                 "insight_kicker": "The pattern",
                 "insight_title": "*%s* of leads scored Hot." % pct(hot_rate) if hot else
                 "No lead reached *Hot* this period.",
                 "insight_body": ib[:3]})

    # ---- 03 next steps
    recs = []
    if hot:
        names = [_who(x[2]) for x in hot[:3]]
        recs.append({"label": "Today", "title": "Call the *%s* first" % (_plural(len(hot), "hot lead")),
                     "body": "Start with %s. They scored %s." % (", ".join(names[:-1]) + (" and " + names[-1] if len(names) > 1 else names[0]),
                                                                ", ".join(n(x[0]) for x in hot[:3])),
                     "impact": "High", "effort": "Low"})
    else:
        names = [_who(x[2]) for x in scored[:3]]
        recs.append({"label": "Today", "title": "Call your top *three* leads",
                     "body": "No lead reached %d, but %s scored highest." % (HOT, ", ".join(names)),
                     "impact": "High", "effort": "Low"})
    if warm:
        recs.append({"label": "This week", "title": "Send the *warm* tier a next step",
                     "body": "%s scored %d to %d. Send a case study and a booking link, then call the ones who click." % (
                         _plural(len(warm), "lead"), WARM, HOT - 1), "impact": "Medium", "effort": "Low"})
    if best_src:
        recs.append({"label": "This month", "title": "Put more behind *%s*" % best_src,
                     "body": "%s of its %s are hot, vs %s across all leads." % (
                         pct(share(src_hot[best_src], src_all[best_src])), _plural(src_all[best_src], "lead"), pct(hot_rate)),
                     "impact": "Medium", "effort": "Medium"})
    gap = None
    if not ctx["has"]["timeframe"]:
        gap = ("Ask *how soon* they need you",
               "Your forms don't ask about timing, so the score can't tell a this-week lead from a someday lead.")
    elif not ctx["has"]["budget"] and ctx["has"]["company"]:
        gap = ("Ask for *budget* on your forms", "Your forms don't ask for a budget, so scores lean on attribution alone.")
    elif ctx["has"]["budget"]:
        answered = sum(1 for _s, _w, e in scored if _budget_value(_find(e, BUDGET_KEYS)[1]) is not None)
        if share(answered, total) < 60:
            gap = ("Make the *budget* question required",
                   "Only %s of leads answered it, so many scores run low for lack of data." % pct(share(answered, total)))
    if gap:
        recs.append({"label": "This month", "title": gap[0], "body": gap[1], "impact": "Medium", "effort": "Low"})
    secs.append({"type": "section-header", "number": "03", "kicker": "Next steps", "title": "Who to call, and *when*."})
    secs.append({"type": "recommendations", "items": recs[:4]})
    secs.append({"type": "notes", "title": "How the score works", "items": rules})
    close = ("Next: call *%s* today. %s more hot leads are waiting." % (_who(e0), n(len(hot) - 1)) if len(hot) > 1 else
             "Next: call *%s* today. Score %s of 100." % (_who(e0), n(s0)))
    secs.append({"type": "closing", "kicker": "The call list in one line", "title": close,
                 "summary_stats": [{"value": n(total), "label": "Leads scored"}, {"value": n(len(hot)), "label": "Hot"},
                                   {"value": n(len(warm)), "label": "Warm"}, {"value": n(round(avg)), "label": "Average score"}],
                 "bullets": ["Call first: %s (%s)." % (_who(e0), n(s0)),
                             "%s of leads scored Hot." % pct(hot_rate)] +
                            (["%s leads score best." % best_src] if best_src else [])})
    return {"meta": m, "sections": secs}


# ---------------------------------------------------------------------------
# LEAD PROFILE
# ---------------------------------------------------------------------------
_FIRST_VISIT_KEYS = ("first_visit (HandL)", "first visit (HandL)", "first_visit", "First Visit",
                     "date (first touch, HandL)", "first_touch_date", "handl_first_visit (HandL)")
_CHANNEL_PHRASE = {"Referral": "a referral", "Organic": "organic search", "Social": "social media",
                   "Paid": "a paid ad", "Direct": "a direct visit"}
_SHORT_PLAT = {"Google Ads": "Google ad", "Meta Ads": "Meta ad", "Microsoft Ads": "Microsoft ad",
               "LinkedIn Ads": "LinkedIn ad", "TikTok Ads": "TikTok ad"}


def _parse_dt(s):
    s = str(s or "").strip().replace("T", " ").replace("Z", "")
    for f, k in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d %H:%M", 16), ("%Y-%m-%d", 10)):
        try:
            return _dt.datetime.strptime(s[:k], f)
        except ValueError:
            continue
    return None


def _form_name(e, forms_map):
    fid = get_field(e, "Form ID", "form_id")
    if fid and fid in forms_map:
        return forms_map[fid]
    title = get_field(e, "Form Title", "form_title")
    if title:
        return _safe(title, 40)
    return ("form %s" % _safe(fid, 12)) if fid else "a form"


def _forms_map(forms):
    out = {}
    for f in forms or []:
        if not isinstance(f, dict):
            continue
        fid = str(f.get("id") or f.get("form_id") or f.get("ID") or "").strip()
        if fid:
            out[fid] = _safe(f.get("title") or f.get("name") or f.get("form_title") or ("Form %s" % fid), 40)
    return out


def build_lead_profile(all_entries, lead_email=None, brand_profile=None, customer_name=None, customer_domain="",
                       compare_label=None, prepared_by=None, prepared_for=None, forms=None, **_):
    """Everything UTM Grabber knows about one lead: the journey, the answers, and the sales angle."""
    all_entries = all_entries or []
    _p, start, end, m = _setup(all_entries, None, brand_profile, customer_name, customer_domain, compare_label,
                               prepared_by, prepared_for)
    m.pop("compare_label", None)
    target = str(lead_email or "").strip().lower()
    masked = _mask(target)
    name = "Lead profile"
    kicker = _kick(name, masked)
    if not all_entries:
        return empty_report(name, m)
    if not target:
        return {"meta": m, "sections": [
            {"type": "title-block", "kicker": name, "title": "Give us an *email* to build a profile.",
             "meta_bits": [b for b in [customer_domain, "%s available" % _plural(len(all_entries), "submission")] if b]},
            {"type": "insight-card", "kicker": "What we need", "title": "Profiles are found by *email*.",
             "body": ["Pass the lead's email address and we match it, ignoring case, across every email field."]},
            {"type": "closing", "kicker": "Next step", "title": "Next: rerun with the lead's *email*."}]}
    matches = [e for e in all_entries if _lead_email(e) == target]
    if target and not matches:
        matches = [e for e in all_entries
                   if any("mail" in str(k).lower() and str(v or "").strip().lower() == target for k, v in e.items())]
    period = period_label(start, end)
    if not matches:
        return {"meta": m, "sections": [
            {"type": "title-block", "kicker": kicker, "title": "We found no *submissions* from %s." % masked,
             "meta_bits": [b for b in [customer_domain, "%s searched" % _plural(len(all_entries), "submission"),
                                       period] if b]},
            {"type": "insight-card", "kicker": "What we checked", "title": "Not one of %s *matched*." % _plural(
                len(all_entries), "submission"),
             "body": ["We searched every email field in %s from %s for %s." % (
                 _plural(len(all_entries), "submission"), period or "the data provided", masked),
                      "Check the spelling, or widen the date range: the lead may have converted before %s." % (
                          _md(start) + start.strftime(", %Y") if start else "this period")]},
            {"type": "closing", "kicker": "Next step", "title": "Next: check the *email* and run this again.",
             "body": "Profiles match on the exact email address, ignoring case."}]}

    matches.sort(key=lambda e: entry_dt(e) or _dt.datetime.min)
    fmap = _forms_map(forms)
    first, last = matches[0], matches[-1]
    who = next((_person(e) for e in reversed(matches) if _person(e)), "")
    first_name = who.split(" ")[0] if who else ""
    d_first, d_last = entry_dt(first), entry_dt(last)
    k = len(matches)

    # first touch
    ft_src = get_field(first, "utm_source (first touch, HandL)", "first_utm_source")
    ft_med = get_field(first, "utm_medium (first touch, HandL)", "first_utm_medium")
    ft_camp = get_field(first, "utm_campaign (first touch, HandL)", "first_utm_campaign")
    ft_land = page_path(get_field(first, "landing_page (first touch, HandL)"))
    ft_ref = _ref_domain(get_field(first, "referrer (first touch, HandL)"))
    has_ft = bool(ft_src or ft_med or ft_land or ft_ref)
    fv = next((_parse_dt(get_field(first, key)) for key in _FIRST_VISIT_KEYS if get_field(first, key)), None)
    if has_ft:
        ch = first_touch(first)
        found = _src_name(ft_src) if ft_src else (ft_ref or ch)
        found_title = "%s, first visit" % (ch.lower() if ch else "first visit")
        found_body = ("Landed on %s." % ft_land) if ft_land else None
    else:
        found = lead_platform(first) or (_src_name(lead_source_medium(first)[0]) if lead_source_medium(first)[0]
                                         else last_touch(first))
        found_title = "earliest touch we saw"
        found_body = "First-visit fields were not captured, so this is their first form."
    closer = lead_platform(first) or (_src_name(lead_source_medium(first)[0]) if lead_source_medium(first)[0]
                                      else last_touch(first))
    term0 = lead_term(first)
    closer_title = ("searched \"%s\"" % _safe(term0, 28)) if term0 else (
        "campaign %s" % _label_camp(lead_campaign(first)) if lead_campaign(first) else "right before the first form")

    # timeline
    events = []
    if has_ft:
        tags = [t for t in ("utm_source=%s" % _safe(ft_src, 24) if ft_src else "",
                            "utm_medium=%s" % _safe(ft_med, 24) if ft_med else "",
                            "utm_campaign=%s" % _safe(ft_camp, 30) if ft_camp else "",
                            "referrer: %s" % _safe(ft_ref, 30) if ft_ref else "") if t]
        events.append({"date": _when(fv) if fv else "First visit",
                       "title": "First visit from %s" % (_src_name(ft_src) if ft_src else (ft_ref or "a direct visit")),
                       "detail": ("Landed on %s" % ft_land) if ft_land else "Landing page not recorded",
                       "tags": tags, "kind": "touch"})
    for i, e in enumerate(matches):
        src, med = lead_source_medium(e)
        plat = lead_platform(e)
        term, camp, content = lead_term(e), lead_campaign(e), lead_content(e)
        form = _form_name(e, fmap)
        if term:
            what = "Searched \"%s\", then filled %s" % (_safe(term, 30), form)
        elif plat:
            what = "Clicked a %s, then filled %s" % (_SHORT_PLAT.get(plat, plat), form)
        elif src:
            what = "Came from %s and filled %s" % (_src_name(src), form)
        elif last_touch(e) != "Direct":
            what = "Came from %s and filled %s" % (_CHANNEL_PHRASE.get(last_touch(e), last_touch(e).lower()), form)
        else:
            what = "Came %s and filled %s" % ("back directly" if i else "in directly", form)
        page = landing_of(e)[0] or page_path(get_field(e, "Source URL"))
        det = ("On %s" % page) if page else "Page not recorded"
        if camp:
            det += ", campaign %s" % _label_camp(camp)
        tags = [t for t in ("utm_source=%s" % _safe(src, 24) if src else "",
                            "utm_medium=%s" % _safe(med, 24) if med else "",
                            "utm_term=%s" % _safe(term, 30) if term else "",
                            "utm_content=%s" % _safe(content, 30) if content else "",
                            _click_platform(e) and ("gclid" if get_field(e, "gclid (HandL)", "gclid") else
                                                    "fbclid" if get_field(e, "fbclid (HandL)", "fbclid") else "msclkid") or "")
                if t]
        d = entry_dt(e)
        events.append({"date": _when(d) if d else "Date unknown", "title": what, "detail": det, "tags": tags,
                       "kind": "conversion"})
    events = events[:1] + events[1:][-11:] if len(events) > 12 else events

    # callouts
    calls = [{"kicker": "How they found you", "value": _safe(found, 28), "title": found_title}]
    if found_body:
        calls[0]["body"] = found_body
    calls.append({"kicker": "What closed them", "value": _safe(closer, 28), "title": closer_title})
    if fv and d_first:
        dd = max(0, (d_first.date() - fv.date()).days)
        calls.append({"kicker": "Days to convert", "value": "Same day" if dd == 0 else _plural(dd, "day"),
                      "title": "from first visit to first form"})
    elif k > 1 and d_first and d_last:
        dd = (d_last.date() - d_first.date()).days
        calls.append({"kicker": "Days between forms", "value": "Same day" if dd == 0 else _plural(dd, "day"),
                      "title": "from first form to latest"})
    calls.append({"kicker": "Submissions", "value": n(k), "title": "form filled" if k == 1 else "forms filled"})

    # what they told you
    merged, seen_emails = [], set()
    for e in reversed(matches):
        for key, v in _fields(e):
            if not v or v.lower() in ("none", "null", "nan", "undefined") or any(key == x[0] for x in merged):
                continue
            kl = key.lower()
            if "mail" in kl or "@" in v:
                if v.lower() in seen_emails:
                    continue
                seen_emails.add(v.lower())
                v = _mask(v)
            elif any(p in kl for p in PHONE_KEYS):
                v = _mask_phone(v)
            else:
                v = _safe(v, 140)
            merged.append((key, v))
    rows = [{"field": _safe(key, 32), "answer": v} for key, v in merged[:15]]

    # sales angle
    k_s, service = _find(last, SERVICE_KEYS)
    k_t, timeframe = _find(last, TIMEFRAME_KEYS)
    soft_time = ""
    if not k_t:
        _k, soft_time = _find(last, SOFT_TIME_KEYS)
        if soft_time and _timeframe_points(soft_time) == 20:
            timeframe, soft_time = soft_time, ""
    k_b, budget = _find(last, BUDGET_KEYS)
    term_any = next((lead_term(e) for e in reversed(matches) if lead_term(e)), "")
    camp_any = next((lead_campaign(e) for e in reversed(matches) if lead_campaign(e)), "")
    has_tf = bool(timeframe) and _norm_text(timeframe) not in _EMPTY_ANSWERS
    has_bud = bool(budget) and _norm_text(budget) not in _EMPTY_ANSWERS
    if service and _norm_text(service) not in _EMPTY_ANSWERS:
        topic = _safe(service, 40)
    elif term_any:
        topic = "\"%s\"" % _safe(term_any, 36)
    elif camp_any:
        topic = _label_camp(camp_any)
    elif has_tf:
        topic = "their timeline"
    elif has_bud:
        topic = "their budget"
    else:
        topic = "what brought them in"
    ctx = _ctx(all_entries, _brand_forms(m.get("customer_name"), customer_domain))
    sc, why = score_lead(last, ctx)
    ang = []
    if term_any:
        ang.append("They searched \"%s\" before converting." % _safe(term_any, 36))
    if service and _norm_text(service) not in _EMPTY_ANSWERS:
        ang.append("They asked about %s." % _safe(service, 40))
    if has_tf:
        ang.append("They want to start: %s." % _safe(timeframe, 30).lower())
    elif soft_time and _norm_text(soft_time) not in _EMPTY_ANSWERS:
        ang.append("Preferred time: %s." % _safe(soft_time, 30).lower())
    if has_bud:
        ang.append("Stated budget: %s." % _safe(budget, 30))
    if k > 1:
        ang.append("They came back %s, so they are still deciding." % ("once" if k == 2 else "%s times" % n(k - 1)))
    ang = ang[:3]
    ang.append("Lead score %s of 100 (%s)%s." % (n(sc), _tier(sc)["label"],
                                                 (": " + ", ".join(r[0].lower() + r[1:] for _, r, _k in
                                                                   sorted(why, key=lambda x: -x[0])[:2])) if why else ""))

    # ---- title
    who_txt = who or "This lead"
    head_found = found
    if "." in str(found) or len(str(found)) > 18:
        # a domain or a long label can't wrap in a headline; name the channel there instead
        head_found = (first_touch(first) if has_ft else last_touch(first))
    if str(head_found) == "Direct":
        headline = "%s arrived as a *direct* visit and filled %s." % (who_txt, _plural(k, "form"))
    elif str(head_found) in _CHANNEL_PHRASE:
        ph = _CHANNEL_PHRASE[head_found]
        head, tail = (ph.split(" ", 1) + [""])[:2] if ph.startswith("a ") else ("", ph)
        headline = "%s found you through %s*%s* and filled %s." % (
            who_txt, (head + " ") if head else "", tail, _plural(k, "form"))
    else:
        headline = "%s found you through *%s* and filled %s." % (who_txt, _safe(head_found, 30), _plural(k, "form"))
    sub = "First form %s via %s." % (_when(d_first) if d_first else "date unknown",
                                     _CHANNEL_PHRASE.get(closer, _safe(closer, 30)))
    if k > 1 and d_first and d_last:
        sub += " Latest on %s." % _when(d_last)
    secs = [{"type": "title-block", "kicker": kicker, "title": headline, "subtitle": sub,
             "meta_bits": [b for b in [customer_domain,
                                       ("First form " + d_first.strftime("%b %-d, %Y")) if d_first else "",
                                       _plural(k, "submission")] if b]},
            {"type": "callouts", "items": calls[:4]},
            {"type": "insight-card", "kicker": "The sales angle", "title": "Open with *%s*." % topic,
             "body": ang[:4], "tone": "good" if sc >= HOT else "neutral"},
            {"type": "section-header", "number": "01", "kicker": "The journey",
             "title": "Every *touch* we recorded.",
             "dek": "Oldest first. Tags show the exact UTM values on each visit."},
            {"type": "timeline", "title": "%s's *journey*" % (first_name or "This lead"), "events": events}]
    if rows:
        secs.append({"type": "section-header", "number": "02", "kicker": "The answers",
                     "title": "What they *told* you."})
        secs.append({"type": "ranked-list", "title": "Form *answers*",
                     "columns": [{"key": "field", "label": "Field", "type": "name"},
                                 {"key": "answer", "label": "Answer", "type": "text"}],
                     "rows": rows, "caption": "Latest answer per field. Email and phone are masked."})

    recs = [{"label": "First call", "title": "Open the call with *%s*" % topic,
             "body": "They %s. Mention it in your first line so they know you read the form." % (
                 ("searched \"%s\"" % _safe(term_any, 30)) if term_any else
                 ("asked about %s" % _safe(service, 30)) if service and _norm_text(service) not in _EMPTY_ANSWERS else
                 ("want to start %s" % _safe(timeframe, 30).lower()) if has_tf else
                 ("named a budget of %s" % _safe(budget, 30)) if has_bud else
                 "came in through %s" % _CHANNEL_PHRASE.get(closer, _safe(closer, 30))),
             "impact": "High", "effort": "Low"}]
    src_rec = (ft_src, ft_camp) if has_ft and ft_src else (lead_source_medium(first)[0], lead_campaign(first))
    if src_rec[0]:
        recs.append({"label": "In your CRM", "title": "Record the *%s* on the contact" % ("first touch" if has_ft else "source"),
                     "body": "Save utm_source=%s%s so revenue from this lead credits %s." % (
                         _safe(src_rec[0], 40), (", utm_campaign=%s" % _safe(src_rec[1], 30)) if src_rec[1] else "",
                         _src_name(src_rec[0])),
                     "impact": "Medium", "effort": "Low"})
    if k > 1:
        recs.append({"label": "Clean up", "title": "Merge the *%s* into one contact" % _plural(k, "submission"),
                     "body": "They filled forms on %s. One record keeps the whole history for the next call." % (
                         ", ".join(_when(entry_dt(e)) for e in matches[:4] if entry_dt(e))),
                     "impact": "Low", "effort": "Low"})
    if not _find(last, PHONE_KEYS)[1]:
        recs.append({"label": "Follow-up", "title": "Reply by *email* with a clear next step",
                     "body": "They left no phone number. Answer what they asked and offer two times to talk.",
                     "impact": "Medium", "effort": "Low"})
    if len(recs) < 2:
        recs.append({"label": "Follow-up", "title": "Log the outcome in your *CRM*",
                     "body": "Mark whether this lead booked or bought, so future reports can tie revenue to %s." % _safe(closer, 30),
                     "impact": "Low", "effort": "Low"})
    secs.append({"type": "section-header", "number": "03" if rows else "02", "kicker": "Next steps",
                 "title": "How to win *%s*." % (first_name or "this lead")})
    secs.append({"type": "recommendations", "items": recs[:4]})
    secs.append({"type": "closing", "kicker": "The lead in one line",
                 "title": "Next: call %s about *%s*. %s" % (
                     first_name or "them", topic,
                     ("They filled %s in %s." % (_plural(k, "form"), _plural(max(1, (d_last.date() - d_first.date()).days), "day")))
                     if k > 1 and d_first and d_last else "Lead score %s of 100." % n(sc)),
                 "summary_stats": [{"value": _safe(found, 28), "label": "Found you via"},
                                   {"value": _safe(closer, 28), "label": "Converted via"},
                                   {"value": n(k), "label": "Submissions"},
                                   {"value": n(sc), "label": "Lead score"}],
                 "bullets": [b for b in ["First form: %s." % _when(d_first) if d_first else "",
                                         "Latest form: %s." % _when(d_last) if k > 1 and d_last else "",
                                         "Score %s of 100, %s." % (n(sc), _tier(sc)["label"].lower())] if b]})
    return {"meta": m, "sections": secs}


def _label_camp(c):
    return _safe(pretty(c), 36)



# ---------------------------------------------------------------------------
# FORM PERFORMANCE
# ---------------------------------------------------------------------------
_DISPOSABLE = {"mailinator.com", "guerrillamail.com", "guerrillamail.net", "sharklasers.com", "10minutemail.com",
               "tempmail.com", "temp-mail.org", "yopmail.com", "trashmail.com", "getnada.com", "dispostable.com",
               "maildrop.cc", "throwawaymail.com", "fakeinbox.com", "mailnesia.com", "mintemail.com",
               "spamgourmet.com", "emailondeck.com", "test.com"}
_TEST_LOCAL = {"test", "testing", "asdf", "qwerty", "abc", "aaa", "xxx", "fake", "spam"}


def _spam_flags(entries):
    """{id(entry): [reasons]} for entries that look like spam, judged within one form."""
    out = defaultdict(list)
    named = sum(1 for e in entries if _person(e))
    collects_names = named >= 0.5 * len(entries) if entries else False
    stamps = Counter(get_field(e, "Date Created", "date_created") for e in entries)
    for e in entries:
        em = _lead_email(e)
        if em:
            local, _, dom = em.partition("@")
            if dom in _DISPOSABLE or local in _TEST_LOCAL:
                out[id(e)].append("disposable or test email")
        if collects_names and not _person(e):
            out[id(e)].append("empty name")
        ts = get_field(e, "Date Created", "date_created")
        if ts and (stamps[ts] >= 3 or (stamps[ts] >= 2 and not ts.rstrip("Z").endswith(":00"))):
            out[id(e)].append("same-second duplicate")
    return out


def build_form_performance(current, prior=None, forms=None, brand_profile=None, customer_name=None,
                           customer_domain="", compare_label=None, prepared_by=None, prepared_for=None, **_):
    """Which forms earn their place: volume, trend, tagging and spam, form by form."""
    prior, start, end, m = _setup(current, prior, brand_profile, customer_name, customer_domain,
                                  compare_label, prepared_by, prepared_for)
    name = "Form performance"
    if not current:
        return empty_report(name, m)
    period = period_label(start, end)
    kicker = _kick(name, period)
    days = _days(start, end)
    when = _in_period(start, end)
    has_prior = bool(prior)
    vs = _vs(m["compare_label"])
    fmap = _forms_map(forms)
    m["sources"] = [{"name": "UTM Grabber", "detail": "%s submissions" % n(len(current))}]

    def fkey(e):
        return get_field(e, "Form ID", "form_id") or "main"

    groups = defaultdict(list)
    for e in current:
        groups[fkey(e)].append(e)
    titles = {}
    for k, v in groups.items():
        t = Counter(get_field(e, "Form Title", "form_title") for e in v if get_field(e, "Form Title", "form_title"))
        if t:
            titles[k] = _safe(t.most_common(1)[0][0], 40)

    def fname(k):
        return fmap.get(k) or titles.get(k) or ("Form %s" % _safe(k, 12) if k != "main" else "Main form")

    for k in fmap:
        groups.setdefault(k, [])
    prior_c = Counter(fkey(e) for e in prior)
    total = len(current)
    order = sorted(groups, key=lambda k: (-len(groups[k]), fname(k)))
    active = [k for k in order if groups[k]]
    bits = [customer_domain, _plural(total, "submission"), _plural(len(active), "active form"),
            "%d days" % days if days else ""]

    if total < MIN_LEADS:
        rows = [{"rank": str(i + 1), "form": fname(k), "subs": {"value": len(groups[k]), "label": n(len(groups[k]))}}
                for i, k in enumerate(order[:12])]
        return _short(m, kicker, "Only %s so far, too few to judge your *forms*." % _plural(total, "submission"),
                      "Form comparisons need at least %d *submissions*." % MIN_LEADS,
                      ["With %s, one submission swings a form's share by %s." % (
                          _plural(total, "submission"), pct(100.0 / total)),
                       "Run this again once more submissions arrive."],
                      stats=[stat("Submissions", n(total)), stat("Active forms", n(len(active)))],
                      extra=[{"type": "ranked-list", "title": "Forms seen so *far*",
                              "columns": [{"key": "rank", "label": "#", "type": "rank"},
                                          {"key": "form", "label": "Form", "type": "name"},
                                          {"key": "subs", "label": "Submissions", "type": "bar"}], "rows": rows}],
                      close_title="Next: rerun this once you pass *%d submissions*." % MIN_LEADS, bits=bits)

    flags = {}
    info = {}
    tagged_all = share(sum(1 for e in current if not _untagged(e)), total)
    dormant_cut = max(1.0, days / 14.0) if days else 1.0
    for k in order:
        v = groups[k]
        fl = _spam_flags(v)
        flags.update(fl)
        c, p = len(v), prior_c.get(k, 0)
        tg = share(sum(1 for e in v if not _untagged(e)), c) if c else 0.0
        sp = share(len(fl), c) if c else 0.0
        if c < dormant_cut:
            status = {"label": "Dormant", "tone": "warn"}
        elif sp >= 20 and len(fl) >= 3:
            status = {"label": "Spam risk", "tone": "bad"}
        elif tg < 10 and tagged_all >= 30 and c >= 5:
            status = {"label": "No UTMs", "tone": "bad"}
        elif has_prior:
            status = _change_badge(c, p)
        else:
            status = {"label": "Active", "tone": "good"}
        info[k] = {"subs": c, "prior": p, "tagged": tg, "spam": sp, "spam_n": len(fl), "status": status,
                   "reasons": Counter(r for rs in fl.values() for r in rs)}
    spam_all = share(len(flags), total)
    sctx = _ctx(current, _brand_forms(m.get("customer_name"), customer_domain))
    avg_all = sum(score_lead(e, sctx)[0] for e in current) / float(total)
    for k in order:
        v = groups[k]
        info[k]["score"] = (sum(score_lead(e, sctx)[0] for e in v) / float(len(v))) if v else None
    dormant = [k for k in order if info[k]["status"]["label"] == "Dormant"]
    no_utm = [k for k in order if info[k]["status"]["label"] == "No UTMs"]
    spammy = [k for k in order if info[k]["status"]["label"] == "Spam risk"]
    top = active[0]
    top_share = share(info[top]["subs"], total)
    labels, daily = daily_counts(current, start, end)

    # ---- one form only: summarize it instead of ranking
    if len(order) == 1:
        it = info[top]
        secs = [{"type": "title-block", "kicker": kicker,
                 "title": "All %s came through *%s*." % (_plural(total, "submission"), fname(top)),
                 "subtitle": "One form carries your whole pipeline %s. %s arrived with UTMs; %s look like spam." % (
                     when, pct(it["tagged"]), pct(it["spam"])), "meta_bits": [b for b in bits if b]},
                {"type": "stat-strip", "stats": [
                    stat("Submissions", n(total), total, it["prior"] if has_prior else None, spark=daily),
                    stat("Per day", "%.1f" % (total / float(max(1, days)))),
                    stat("With UTMs", pct(it["tagged"])),
                    stat("Spam-like", pct(it["spam"]), good="down")]},
                {"type": "chart", "chart": {"type": "area", "labels": labels, "values": daily},
                 "chart_title": "Submissions per *day*",
                 "caption": "Every submission to %s %s." % (fname(top), when)}]
        recs = [{"label": "Ongoing", "title": "Test *%s* every week" % fname(top),
                 "body": "It is your only form. If it breaks, every lead stops. Submit a test entry each week.",
                 "impact": "High", "effort": "Low"}]
        if it["spam_n"] >= 3:
            r, c = it["reasons"].most_common(1)[0]
            recs.append({"label": "This week", "title": "Filter *spam* on %s" % fname(top),
                         "body": "%s look like spam (most often: %s). Add a honeypot field or reCAPTCHA." % (
                             _plural(it["spam_n"], "submission"), r), "impact": "Medium", "effort": "Low"})
        if it["tagged"] < 50:
            recs.append({"label": "This month", "title": "Check the *UTM fields* on %s" % fname(top),
                         "body": "Only %s of submissions carried UTMs. Make sure the hidden UTM Grabber fields are on the form." %
                                 pct(it["tagged"]), "impact": "Medium", "effort": "Low"})
        if len(recs) < 2:
            recs.append({"label": "This quarter", "title": "Add a second *form placement*",
                         "body": "A short form on your top landing page gives visitors a second way in.",
                         "impact": "Medium", "effort": "Medium"})
        secs += [{"type": "section-header", "number": "01", "kicker": "Next steps", "title": "Keep it *working*."},
                 {"type": "recommendations", "items": recs[:4]},
                 {"type": "closing", "kicker": "The form in one line",
                  "title": "Next: test *%s* weekly. It carries all %s." % (fname(top), _plural(total, "submission")),
                  "summary_stats": [{"value": n(total), "label": "Submissions"}, {"value": pct(it["tagged"]), "label": "With UTMs"},
                                    {"value": pct(it["spam"]), "label": "Spam-like"}]}]
        return {"meta": m, "sections": secs}

    # ---- title
    headline = "*%s* brought in %s of %s." % (fname(top), pct(top_share), _plural(total, "submission"))
    sub = "%s of %s forms took submissions %s." % (n(len(active)), n(len(order)), when)
    if dormant:
        sub += " %s barely moved." % _plural(len(dormant), "form")
    if spam_all >= 5:
        sub += " %s of submissions look like spam." % pct(spam_all)
    secs = [{"type": "title-block", "kicker": kicker, "title": headline, "subtitle": sub,
             "meta_bits": [b for b in bits if b]}]
    stats = [stat("Submissions", n(total), total, len(prior) if has_prior else None, spark=daily),
             stat("Active forms", n(len(active)), note=("of %s listed" % n(len(fmap))) if fmap else None),
             stat("Top form share", pct(top_share), note=fname(top)),
             stat("With UTMs", pct(tagged_all), note="any utm_ tag"),
             stat("Spam-like", pct(spam_all), good="down", note=_plural(len(flags), "submission"))]
    if dormant or fmap:
        stats.append(stat("Dormant forms", n(len(dormant)), good="down", note="under 1 per 2 weeks"))
    secs.append({"type": "stat-strip", "stats": stats})

    # takeaway: the biggest issue, else the concentration
    if no_utm:
        k = no_utm[0]
        tk = {"tone": "bad", "title": "*%s* captures almost no UTMs." % fname(k),
              "body": ["Only %s of its %s carried any UTM, vs %s across all forms." % (
                  pct(info[k]["tagged"]), _plural(info[k]["subs"], "submission"), pct(tagged_all)),
                  "The hidden UTM Grabber fields are probably missing from this form."]}
    elif spammy:
        k = spammy[0]
        r, c = info[k]["reasons"].most_common(1)[0]
        tk = {"tone": "warn", "title": "*%s* of %s's submissions look like spam." % (pct(info[k]["spam"]), fname(k)),
              "body": ["%s were flagged; the most common sign: %s." % (_plural(info[k]["spam_n"], "submission"), r),
                       "Spam inflates lead counts and wastes follow-up time."]}
    elif dormant:
        tk = {"tone": "warn", "title": "%s took almost no *submissions*." % _plural(len(dormant), "form"),
              "body": ["%s: %s." % (", ".join(fname(k) for k in dormant[:3]),
                                    ", ".join(n(info[k]["subs"]) for k in dormant[:3])),
                       "Check that they still load, or retire them."]}
    else:
        tk = {"tone": "neutral", "title": "*%s* carries %s of your pipeline." % (fname(top), pct(top_share)),
              "body": ["Every listed form took submissions and none looks like a spam target."]}
    secs.append(dict({"type": "insight-card", "kicker": "The takeaway"}, **tk))

    # ---- 01 leaderboard
    secs.append({"type": "section-header", "number": "01", "kicker": "Leaderboard",
                 "title": "Which *forms* earn their place."})
    cols = [{"key": "rank", "label": "#", "type": "rank"},
            {"key": "form", "label": "Form", "type": "name"},
            {"key": "subs", "label": "Submissions", "type": "bar"},
            {"key": "share", "label": "Share", "type": "pct", "align": "right"}]
    if has_prior:
        cols.append({"key": "change", "label": vs, "type": "delta", "align": "right"})
    cols += [{"key": "tagged", "label": "With UTMs", "type": "pct", "align": "right"},
             {"key": "spam", "label": "Spam-like", "type": "pct", "align": "right"},
             {"key": "status", "label": "Status", "type": "badge"}]
    rows = []
    for i, k in enumerate(order[:12]):
        it = info[k]
        row = {"rank": str(i + 1), "form": fname(k), "subs": {"value": it["subs"], "label": n(it["subs"])},
               "share": pct(share(it["subs"], total)),
               "change": _delta_cell(it["subs"], it["prior"]) if has_prior else {"label": "–", "direction": "flat"},
               "tagged": pct(it["tagged"]) if it["subs"] else "–", "spam": pct(it["spam"]) if it["subs"] else "–",
               "status": it["status"]}
        if i == 0:
            row["_highlight"] = True
        if not it["subs"]:
            row["_muted"] = True
        rows.append(row)
    secs.append({"type": "ranked-list", "title": "Submissions by *form*", "columns": cols, "rows": rows,
                 "caption": "Spam-like: a disposable or test email, a blank name on a form that collects names, or "
                            "several entries in the same second. Dormant: under one submission per two weeks."})

    # ---- 02 rhythm
    top3 = active[:3]
    long_ = days > 45
    if long_:
        wks = _weeks(start, end)
        xl = [_md(a) for a, _ in wks]
        series = [{"label": fname(k), "values": _weekly(groups[k], wks)} for k in top3]
    else:
        xl = labels
        series = [{"label": fname(k), "values": daily_counts(groups[k], start, end)[1]} for k in top3]
    trend = []
    for s_ in series:
        vals = s_["values"]
        h = len(vals) // 2
        a, b = sum(vals[:h]), sum(vals[h:])
        trend.append((s_["label"], a, b))
    lab, a, b = trend[0]
    move = "rose" if b > a * 1.15 else ("slowed" if b < a * 0.85 else "held steady")
    ib = ["%s: %s in the first half of the period, %s in the second." % (lab, n(a), n(b))]
    for lab2, a2, b2 in trend[1:3]:
        ib.append("%s: %s, then %s." % (lab2, n(a2), n(b2)))
    secs.append({"type": "section-header", "number": "02", "kicker": "Rhythm",
                 "title": "How each *form* moved %s." % ("week by week" if long_ else "day by day")})
    secs.append({"type": "chart-insight",
                 "chart": {"type": "line-multi", "labels": xl, "series": series},
                 "caption": "%s submissions for the top %s forms" % ("Weekly" if long_ else "Daily", len(top3)),
                 "insight_kicker": "The trend", "insight_title": "*%s* %s through the period." % (lab, move),
                 "insight_body": ib})

    # ---- 03 next steps
    recs = []
    for k in no_utm[:1]:
        recs.append({"label": "This week", "title": "Add UTM fields to *%s*" % fname(k),
                     "body": "Only %s of its %s carried UTMs, vs %s overall. Add the hidden UTM Grabber fields." % (
                         pct(info[k]["tagged"]), _plural(info[k]["subs"], "submission"), pct(tagged_all)),
                     "impact": "High", "effort": "Low"})
    for k in spammy[:1]:
        r, c = info[k]["reasons"].most_common(1)[0]
        recs.append({"label": "This week", "title": "Filter *spam* on %s" % fname(k),
                     "body": "%s of its submissions look like spam (most often: %s). Add a honeypot field or reCAPTCHA." % (
                         pct(info[k]["spam"]), r), "impact": "Medium", "effort": "Low"})
    if has_prior:
        falls = [k for k in active if info[k]["prior"] >= 5 and info[k]["subs"] < 0.6 * info[k]["prior"]]
        if falls:
            k = max(falls, key=lambda x: info[x]["prior"] - info[x]["subs"])
            recs.append({"label": "This week", "title": "Check why *%s* slowed" % fname(k),
                         "body": "It fell from %s to %s submissions. Test the form and the pages that host it." % (
                             n(info[k]["prior"]), n(info[k]["subs"])), "impact": "Medium", "effort": "Low"})
    if dormant:
        k = dormant[0]
        recs.append({"label": "This month", "title": "Fix or retire *%s*" % fname(k),
                     "body": "It took %s in %s. Check it still loads, or remove it so it stops splitting traffic." % (
                         _plural(info[k]["subs"], "submission"), _plural(days, "day") if days else "this period"),
                     "impact": "Low", "effort": "Low"})
    if top_share >= 60:
        recs.append({"label": "Ongoing", "title": "Test *%s* every week" % fname(top),
                     "body": "It handles %s of submissions. If it breaks, most of your leads stop." % pct(top_share),
                     "impact": "Medium", "effort": "Low"})
    q = [k for k in active if info[k]["subs"] >= 10 and info[k]["score"] is not None]
    if len(q) >= 2 and len(recs) < 4:
        bq = max(q, key=lambda k: info[k]["score"])
        if info[bq]["score"] >= 1.2 * max(1.0, avg_all):
            recs.append({"label": "This month", "title": "Give *%s* a more visible spot" % fname(bq),
                         "body": "Its leads score %s on average, vs %s across all forms (lead quality scorer rules). "
                                 "Put it where more visitors see it." % (n(round(info[bq]["score"])), n(round(avg_all))),
                         "impact": "Medium", "effort": "Medium"})
    if len(recs) < 2:
        recs.append({"label": "Ongoing", "title": "Rerun this *form* check monthly",
                     "body": "Forms break quietly after site updates. A monthly look catches it early.",
                     "impact": "Low", "effort": "Low"})
    secs.append({"type": "section-header", "number": "03", "kicker": "Next steps", "title": "What to do *next*."})
    secs.append({"type": "recommendations", "items": recs[:4]})
    notes = ["Forms are grouped by Form ID%s." % (" and named from your form list" if fmap else ""),
             "With UTMs: the share of a form's submissions with at least one of utm_source, utm_medium or utm_campaign.",
             "Spam-like signs are judged per form: disposable or test email domains, a blank name where most entries "
             "have one, and three or more entries in the same second (two when the time has seconds)."]
    if has_prior:
        notes.append("Changes compare %s with %s." % (period, m["compare_label"]))
    secs.append({"type": "notes", "items": notes})
    t = recs[0]["title"]
    close = "Next: %s. %s" % (t[0].lower() + t[1:], recs[0]["body"].split(". ")[0].rstrip(".") + ".")
    secs.append({"type": "closing", "kicker": "The forms in one line", "title": close,
                 "summary_stats": [{"value": n(total), "label": "Submissions"},
                                   {"value": n(len(active)), "label": "Active forms"},
                                   {"value": pct(top_share), "label": "Top form share"},
                                   {"value": pct(spam_all), "label": "Spam-like"}],
                 "bullets": ["%s brought in %s." % (fname(top), _plural(info[top]["subs"], "submission")),
                             "%s of submissions carried UTMs." % pct(tagged_all)] +
                            (["%s dormant: %s." % (_plural(len(dormant), "form"), ", ".join(fname(k) for k in dormant[:3]))]
                             if dormant else []) +
                            (["%s of submissions look like spam." % pct(spam_all)] if spam_all >= 5 else [])})
    return {"meta": m, "sections": secs}


REGISTRY = {
    "audit": build_audit, "hygiene": build_audit, "utm-audit": build_audit, "utm-hygiene-audit": build_audit,
    "tracking-audit": build_audit,
    "lead-scorer": build_lead_scorer, "lead-quality": build_lead_scorer, "score-leads": build_lead_scorer,
    "lead-quality-scorer": build_lead_scorer,
    "lead-profile": build_lead_profile, "lead": build_lead_profile, "profile": build_lead_profile,
    "lead-profile-enrichment": build_lead_profile,
    "form-performance": build_form_performance, "forms": build_form_performance, "form": build_form_performance,
}
