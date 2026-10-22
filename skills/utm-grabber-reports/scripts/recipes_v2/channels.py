"""
Channel recipes: paid vs organic, source to CRM, anomaly check and lead forecast.

Same pattern as core.build_monthly: guard thin data, compute every number from the
inputs, lead with the outcome, one *accent* per title, recommendations derived from
thresholds in the data, a closing that names the next step and the number behind it.
"""
import math
from collections import Counter

from .common import (CHANNELS, daily_counts, delta, empty_report, first_touch, get_field, last_touch, meta, n,
                     pct, period_label, pretty, share, source_label, span, stat)
from .core import (_AI, _ONE_DAY, _camp, _clean, _counts, _cov, _day, _find_field, _growth, _has_first_touch, _page,
                   _pl, _pname, _prior_label, _quality_rules, _rule_share, _short, _signed, _sn, _src, _tagged, _thin,
                   _trim, _undated, _usable)


def _when(days):
    return "this week" if days == 7 else ("in a single day" if days == 1 else "in the last %d days" % days)


def _about(x):
    """Round a forecast to the precision the data supports."""
    x = max(0.0, x)
    if x < 20:
        return int(round(x))
    step = 5 if x < 100 else (10 if x < 1000 else 50)
    return int(step * round(x / float(step)))


# ---------------------------------------------------------------------------
# PAID VS ORGANIC
# ---------------------------------------------------------------------------
def _src_or_channel(e):
    s = _src(e)
    return source_label(s) if s else "%s (no UTM)" % last_touch(e)


def _top_label(entries):
    """Top source of a group; untagged leads count under their channel, as in the sources table."""
    c = Counter(_src_or_channel(e) for e in entries)
    return c.most_common(1)[0] if c else ("", 0)


def _top_phrase(label):
    return ("%s visits with no UTM tags" % label.split(" (")[0].lower()) if label.endswith("(no UTM)") else label


def _moved(g):
    if g is None:
        return "held level"
    return ("grew %s" % _signed(g)[1:]) if g >= 3 else (("fell %s" % _signed(g)[1:]) if g <= -3 else "held level")


def _pshort(p):
    return "Home" if p == "/" else _trim(p, 10)


def _cshort(label):
    """Comparison cells stay short (they can't wrap on phones): 'Direct (no UTM)' -> 'Direct'."""
    return _trim(label.split(" (")[0], 10)


def build_paid_vs_organic(current, prior=None, brand_profile=None, customer_name=None, customer_domain="",
                          form_label=None, compare_label=None, prepared_by=None, prepared_for=None, **_):
    """Paid against everything else: size, growth, sources, pages, lead quality and who opens the journey."""
    current, prior = list(current or []), _usable(prior)
    start, end = span(current)
    pstart, pend = span(prior) if prior else (None, None)
    m = meta(brand_profile, customer_name, customer_domain,
             compare_label=compare_label or (_prior_label(pstart, pend) if prior else "last period"),
             sources=None, prepared_by=prepared_by, prepared_for=prepared_for)
    name = "Paid vs organic"
    if not current:
        return empty_report(name, m)
    if start is None:
        return _undated(name, m, current)
    period = period_label(start, end)
    total = len(current)
    if total < 10:
        return _thin(name, m, current, period)
    cmp_ = m["compare_label"]
    has_prior = bool(prior)
    days = (end - start).days + 1
    m["sources"] = [{"name": "UTM Grabber", "detail": _pl(total, "lead")}]

    def is_paid(e):
        return last_touch(e) == "Paid"

    P = [e for e in current if is_paid(e)]
    O = [e for e in current if not is_paid(e)]
    Pp = [e for e in prior if is_paid(e)]
    Op = [e for e in prior if not is_paid(e)]
    nP, nO = len(P), len(O)
    gP = _growth(nP, len(Pp)) if has_prior else None
    gO = _growth(nO, len(Op)) if has_prior else None
    ps = share(nP, total)
    ps_p = share(len(Pp), len(prior)) if has_prior else None
    covP, covP_p = _cov(P), (_cov(Pp) if Pp else None)
    _, dP = daily_counts(P, start, end)
    _, dO = daily_counts(O, start, end)
    if days > 45:
        lab, sP, sO = [], [], []
        for i in range(days % 7, days, 7):        # whole weeks ending on the last day; a partial first week is left out
            d = start + i * _ONE_DAY
            lab.append("Week of %s %d" % (d.strftime("%b"), d.day))
            sP.append(sum(dP[i:i + 7]))
            sO.append(sum(dO[i:i + 7]))
        unit_word = "week"
    else:
        lab, _ = daily_counts(current, start, end)
        sP, sO, unit_word = dP, dO, "day"
    tP, tO = _top_label(P), _top_label(O)
    pgP, pgO = _counts(P, _page), _counts(O, _page)
    aP, bP = (sum(dP[:days // 2]), sum(dP[days - days // 2:]))
    aO, bO = (sum(dO[:days // 2]), sum(dO[days - days // 2:]))

    # headline: the trajectory if we have a prior period, else the split
    faster = None
    if gP is not None and gO is not None and abs(gO - gP) >= 10:
        faster = "Organic" if gO > gP else "Paid"
    if faster:
        g_f, g_s = (gO, gP) if faster == "Organic" else (gP, gO)
        slower = "paid" if faster == "Organic" else "organic"
        if g_f > 0 and g_s < 0:
            headline = "*%s* grew %s while %s fell %s." % (faster, _signed(g_f)[1:], slower, _signed(g_s)[1:])
        elif g_f > 0:
            headline = "*%s* grew faster than %s: %s against %s." % (faster, slower, _signed(g_f), _signed(g_s))
        else:
            headline = "Both fell, but *%s* held up better: %s against %s." % (faster.lower(), _signed(g_f), _signed(g_s))
    elif has_prior and gP is not None and gO is not None:
        headline = "Paid and organic moved together; paid holds at *%s* of leads." % pct(ps)
    elif nP == 0:
        headline = "Every lead was *organic*: no paid clicks this period."
    elif nO == 0:
        headline = "Every lead came from a paid *click* this period."
    else:
        headline = "Paid clicks brought *%s* of leads; organic brought the rest." % pct(ps)
    sub = ["%s paid and %s organic leads over %s." % (n(nP), n(nO), _pl(days, "day"))]
    if tP[0] and tO[0] and tP[0] == tO[0]:
        sub.append("%s tops both sides: %s of paid leads and %s of organic." % (
            _top_phrase(tP[0])[:1].upper() + _top_phrase(tP[0])[1:], pct(share(tP[1], nP)), pct(share(tO[1], nO))))
    elif tP[0] and tO[0]:
        sub.append("%s is the top paid source (%s of paid leads); %s %s organic (%s)." % (
            _top_phrase(tP[0]), pct(share(tP[1], nP)), _top_phrase(tO[0]),
            "lead" if tO[0].endswith("(no UTM)") else "leads", pct(share(tO[1], nO))))

    secs = [{"type": "title-block", "kicker": "Paid vs organic · %s" % period, "title": headline,
             "subtitle": " ".join(sub),
             "meta_bits": [b for b in [customer_domain, form_label, "%s submissions" % n(total), _pl(days, "day")] if b]},
            {"type": "stat-strip", "stats": [
                stat("Paid leads", n(nP), nP, len(Pp) if has_prior and Pp else None, spark=dP,
                     note="%.1f a day" % (nP / float(days))),
                stat("Organic leads", n(nO), nO, len(Op) if has_prior and Op else None, spark=dO,
                     note="%.1f a day" % (nO / float(days))),
                stat("Paid share", pct(ps), ps, ps_p, kind="pts", good="neutral", note="of all leads"),
                stat("Paid leads fully tagged", pct(covP), covP, covP_p, kind="pts",
                     note="%s of %s paid leads" % (n(sum(1 for e in P if _tagged(e))), n(nP)))]}]

    # 01 the split
    rows = []

    def add(label, a, b, ad, bd, better=None, rate=True):
        row = {"label": label, "a": round(a, 2), "b": round(b, 2), "a_display": ad, "b_display": bd}
        if better and (abs(a - b) >= 3 if rate else abs(a - b) >= 0.03 * max(abs(a), abs(b), 1e-9)):
            row["better"] = "a" if (a > b) == (better == "high") else "b"
        rows.append(row)

    add("Leads", nP, nO, n(nP), n(nO), rate=False)
    add("Share of leads", ps, 100 - ps, pct(ps), pct(100 - ps))
    if gP is not None and gO is not None:
        add("Change vs %s" % cmp_, gP, gO, _signed(gP), _signed(gO), "high")
    add("Top source share", share(tP[1], nP), share(tO[1], nO),
        "%s %s" % (_cshort(tP[0]), pct(share(tP[1], nP))) if tP[0] else "\u2013",
        "%s %s" % (_cshort(tO[0]), pct(share(tO[1], nO))) if tO[0] else "\u2013")
    if pgP or pgO:
        kP = pgP.most_common(1)[0] if pgP else ("", 0)
        kO = pgO.most_common(1)[0] if pgO else ("", 0)
        add("Top landing page share", share(kP[1], nP), share(kO[1], nO),
            "%s %s" % (_pshort(kP[0]), pct(share(kP[1], nP))) if kP[0] else "\u2013",
            "%s %s" % (_pshort(kO[0]), pct(share(kO[1], nO))) if kO[0] else "\u2013")
    add("Fully tagged", _cov(P), _cov(O), pct(_cov(P)), pct(_cov(O)))
    quality = []
    for qlabel, test, _f in _quality_rules(current):
        qa, na = _rule_share(P, test)
        qb, nb = _rule_share(O, test)
        if na >= 5 and nb >= 5:
            add(qlabel, qa, qb, pct(qa), pct(qb), "high")
            quality.append((qlabel, qa, qb))
    secs.append({"type": "section-header", "number": "01", "kicker": "The split",
                 "title": "Paid and organic, *measure* by measure.",
                 "dek": "Paid means a paid last touch (cpc, paid social or an ad click ID). Organic is everything "
                        "else: search, social, referral, email and direct."})
    secs.append({"type": "comparison", "a": {"label": "Paid", "sub": _pl(nP, "lead")},
                 "b": {"label": "Organic", "sub": _pl(nO, "lead")}, "rows": rows,
                 "caption": "A tick marks the side ahead by 3 points or more where higher is better."
                            + (" Quality rows count only leads who answered the question." if quality else "")})

    # 02 trajectory
    traj = []
    if gP is not None and gO is not None:
        traj.append("Against %s, paid %s and organic %s." % (cmp_, _moved(gP), _moved(gO)))

    def half(a, b):
        noise = abs(b - a) < (a + b) ** 0.5
        return "%s to %s%s" % (n(a), n(b), ", within normal swing" if noise and a != b else "")

    traj.append("Inside the period (first half to second half), paid went from %s; organic from %s." % (
        half(aP, bP), half(aO, bO)))
    if faster:
        t_title = "*%s* has the momentum." % faster
    else:
        hP = _growth(bP, aP) if aP else None
        hO = _growth(bO, aO) if aO else None
        real = abs(bP - aP) >= (aP + bP) ** 0.5 or abs(bO - aO) >= (aO + bO) ** 0.5
        if hP is not None and hO is not None and abs(hP - hO) >= 15 and real:
            t_title = "*%s* finished the period stronger." % ("Paid" if hP > hO else "Organic")
        else:
            t_title = "Neither side is pulling *away*."
    secs.append({"type": "section-header", "number": "02", "kicker": "Trajectory",
                 "title": "Which side is *growing*.", "dek": "Leads per %s, paid against organic." % unit_word})
    secs.append({"type": "chart-insight",
                 "chart": {"type": "line-multi", "labels": lab,
                           "series": [{"label": "Paid", "values": sP}, {"label": "Organic", "values": sO}]},
                 "caption": "Leads per %s by last-touch channel group" % unit_word,
                 "insight_kicker": "Trajectory", "insight_title": t_title, "insight_body": traj})

    # 03 sources on each side
    srcP = _counts(P, _src).most_common(5)
    srcO = Counter(_src_or_channel(e) for e in O).most_common(5)
    nxt = 3
    if srcP or srcO:
        rows_t = []
        for i in range(max(len(srcP), len(srcO))):
            r = {"rank": str(i + 1)}
            if i < len(srcP):
                r["p"], r["pv"] = source_label(srcP[i][0]), {"value": srcP[i][1], "label": n(srcP[i][1])}
            else:
                r["p"], r["pv"] = "–", {"value": 0, "label": "–"}
            if i < len(srcO):
                r["o"], r["ov"] = srcO[i][0], {"value": srcO[i][1], "label": n(srcO[i][1])}
            else:
                r["o"], r["ov"] = "–", {"value": 0, "label": "–"}
            rows_t.append(r)
        secs.append({"type": "section-header", "number": "03", "kicker": "Sources",
                     "title": "Who feeds each *side*."})
        secs.append({"type": "ranked-list", "title": "Top five *sources* on each side",
                     "columns": [{"key": "rank", "label": "#", "type": "rank"},
                                 {"key": "p", "label": "Paid source", "type": "name"},
                                 {"key": "pv", "label": "Paid leads", "type": "bar"},
                                 {"key": "o", "label": "Organic source", "type": "name"},
                                 {"key": "ov", "label": "Organic leads", "type": "bar"}],
                     "rows": rows_t,
                     "caption": "Organic leads without a utm_source are grouped by channel."})
        nxt = 4

    # 04 first touch vs last touch (only when the plugin captured first touch)
    opened = closed_by_paid = 0
    if _has_first_touch(current):
        ftP = sum(1 for e in current if first_touch(e) == "Paid")
        opened = sum(1 for e in P if first_touch(e) != "Paid")        # paid closed, organic opened
        closed_by_paid = sum(1 for e in O if first_touch(e) == "Paid")  # paid opened, organic closed
        secs.append({"type": "section-header", "number": "%02d" % nxt, "kicker": "First touch",
                     "title": "Who *opens* the journey.",
                     "dek": "First touch is how a lead first reached the site; last touch is the visit that converted."})
        secs.append({"type": "chart-insight",
                     "chart": {"type": "bar-grouped", "labels": ["Paid", "Organic"],
                               "groups": [{"label": "First touch", "values": [ftP, total - ftP]},
                                          {"label": "Last touch", "values": [nP, nO]}]},
                     "caption": "Leads credited to each side by first touch and by last touch",
                     "insight_kicker": "Openers vs closers",
                     "insight_title": ("Every journey started and ended on the same *side*." if not (opened or closed_by_paid)
                                       else ("*Organic* opened %s of the journeys paid closed." % pct(share(opened, nP)))
                                       if opened >= closed_by_paid else
                                       ("*Paid* opened %s of the journeys organic closed." % pct(share(closed_by_paid, nO)))),
                     "insight_body": ["%s paid leads first found you through organic channels; %s organic leads "
                                      "first came from a paid click." % (n(opened), n(closed_by_paid)),
                                      "Judge each side on both touches, or the opener looks weaker than it is."]})
        nxt += 1

    # next steps
    recs = []
    if faster == "Organic":
        kO = pgO.most_common(1)[0] if pgO else None
        page_txt = ""
        if kO:
            pg = _pname(kO[0])
            page_txt = " %s brought %s of them." % (pg[:1].upper() + pg[1:], n(kO[1]))
        recs.append({"label": "This quarter", "title": "Put more into the *content* that feeds organic",
                     "body": "Organic leads %s while paid %s.%s" % (_moved(gO), _moved(gP), page_txt),
                     "impact": "High", "effort": "Medium"})
    elif faster == "Paid":
        recs.append({"label": "This month", "title": "Keep *paid* funded while it scales",
                     "body": "Paid leads %s while organic %s. %s drove %s of paid leads." % (
                         _moved(gP), _moved(gO), tP[0] or "One source", pct(share(tP[1], nP))),
                     "impact": "High", "effort": "Medium"})
    if nP and covP < 90:
        k = nP - sum(1 for e in P if _tagged(e))
        recs.append({"label": "This week", "title": "Tag every paid *ad URL*",
                     "body": "%s of paid leads (%s) lacked a full UTM set, so you can't tell which ads paid off." % (
                         pct(100 - covP), n(k)), "impact": "High" if covP < 70 else "Medium", "effort": "Low"})
    if nP >= 10 and share(tP[1], nP) >= 70 and not tP[0].endswith("(no UTM)"):
        recs.append({"label": "This quarter", "title": "Test a second *paid* channel",
                     "body": "%s drives %s of paid leads. One platform change could cut paid volume sharply." % (
                         tP[0], pct(share(tP[1], nP))), "impact": "Medium", "effort": "Medium"})
    if pgO and len(recs) < 4:
        k, v = pgO.most_common(1)[0]
        if share(v, nO) >= 20:
            recs.append({"label": "Ongoing", "title": ("Protect your *home page*" if k == "/" else
                                                      "Protect *%s*" % _trim(k, 30)),
                         "body": "It brought %s of organic leads (%s). Keep it current and linked from your top "
                                 "posts." % (pct(share(v, nO)), n(v)), "impact": "Medium", "effort": "Low"})
    if opened and share(opened, nP) >= 25 and len(recs) < 4:
        recs.append({"label": "Reporting", "title": "Credit *organic* for the journeys it starts",
                     "body": "%s of paid leads first arrived through organic channels. Cutting organic content "
                             "would likely cost paid leads too." % pct(share(opened, nP)),
                     "impact": "Medium", "effort": "Low"})
    for qlabel, qa, qb in quality:
        if abs(qa - qb) >= 10 and len(recs) < 4:
            hi = "Paid" if qa > qb else "Organic"
            recs.append({"label": "Lead quality", "title": "Weigh *%s* leads for quality, not just volume" % hi.lower(),
                         "body": "%s of %s leads answered “%s” against %s on the other side." % (
                             pct(max(qa, qb)), hi.lower(), qlabel.lower(), pct(min(qa, qb))),
                         "impact": "Medium", "effort": "Low"})
    if len(recs) < 2:
        recs.append({"label": "Next quarter", "title": "Rebalance budget by *trajectory*, not size",
                     "body": "Paid is %s of leads today. Compare this report each quarter and shift budget toward the "
                             "side that is growing." % pct(ps), "impact": "Medium", "effort": "Low"})
    secs.append({"type": "section-header", "number": "%02d" % nxt, "kicker": "Next steps",
                 "title": "Where to put the next *dollar*."})
    secs.append({"type": "recommendations", "items": recs[:4]})
    secs.append({"type": "notes", "title": "How we built this report", "items": [
        "Paid: the converting visit was a paid click (utm_medium cpc, ppc or paid social, or a Google or "
        "Microsoft click ID). Organic: every other lead.",
        ("Change compares with %s (%s paid, %s organic)." % (cmp_, n(len(Pp)), n(len(Op)))) if has_prior else
        "No earlier period was supplied, so trajectory uses the first and second half of this period.",
        "First touch comes from UTM Grabber's first-visit fields." if opened or closed_by_paid else
        "First-touch fields were not captured on these leads, so every number here is last touch."]})
    r0 = recs[0]
    if r0["title"].startswith("Protect"):
        k, v = pgO.most_common(1)[0]
        ctitle = "Next: protect %s. It brings %s of organic leads." % (
            "your *home page*" if k == "/" else "*%s*" % _trim(k, 30), pct(share(v, nO)))
    elif r0["title"].startswith("Test a second"):
        ctitle = "Next: test a second *paid* channel. %s drives %s of paid leads." % (tP[0], pct(share(tP[1], nP)))
    elif r0["title"].startswith("Credit"):
        ctitle = "Next: credit *organic* for the journeys it opens. It started %s of paid leads." % pct(share(opened, nP))
    elif r0["title"].startswith("Weigh"):
        ctitle = "Next: %s. %s" % (r0["title"][0].lower() + r0["title"][1:], r0["body"].split(" against")[0] + ".")
    elif faster:
        ctitle = "Next: keep backing *%s*. It %s while %s %s." % (
            faster.lower(), _moved(gO if faster == "Organic" else gP), "paid" if faster == "Organic" else "organic",
            _moved(gP if faster == "Organic" else gO))
    elif r0["title"].startswith("Tag every paid"):
        ctitle = "Next: tag every paid *ad URL*. %s of paid leads are untraceable." % pct(100 - covP)
    else:
        ctitle = "Next: %s. Paid is %s of leads." % (r0["title"][0].lower() + r0["title"][1:], pct(ps))
    secs.append({"type": "closing", "kicker": "The split in one line", "title": ctitle,
                 "summary_stats": [{"value": pct(ps), "label": "Paid share"},
                                   {"value": n(nP), "label": "Paid leads"},
                                   {"value": n(nO), "label": "Organic leads"},
                                   {"value": pct(covP), "label": "Paid fully tagged"}],
                 "bullets": [x for x in [
                     ("Against %s, paid %s and organic %s." % (cmp_, _moved(gP), _moved(gO))) if gP is not None and gO is not None else None,
                     ("Top sources: %s for paid, %s for organic." % (tP[0], tO[0])) if tP[0] and tO[0] else None,
                     "%.1f paid and %.1f organic leads a day." % (nP / float(days), nO / float(days))] if x]})
    return {"meta": m, "sections": secs}


# ---------------------------------------------------------------------------
# SOURCE TO CRM
# ---------------------------------------------------------------------------
_CRM = {"hubspot": "HubSpot", "salesforce": "Salesforce", "pipedrive": "Pipedrive", "zoho": "Zoho", "zoho crm": "Zoho",
        "activecampaign": "ActiveCampaign", "active campaign": "ActiveCampaign", "gohighlevel": "GoHighLevel",
        "highlevel": "GoHighLevel", "go high level": "GoHighLevel", "monday": "monday.com", "monday.com": "monday.com",
        "keap": "Keap", "close": "Close", "copper": "Copper", "freshsales": "Freshsales", "dynamics": "Dynamics 365",
        "microsoft dynamics": "Dynamics 365", "none": "No CRM", "no crm": "No CRM", "no": "No CRM", "n/a": "No CRM",
        "other": "Other", "spreadsheet": "Spreadsheet", "excel": "Spreadsheet", "google sheets": "Spreadsheet"}


def _crm_name(v):
    s = _clean(v)
    return _CRM.get(s.lower(), s) if s else ""


def build_source_to_crm(current, prior=None, brand_profile=None, customer_name=None, customer_domain="",
                        form_label=None, compare_label=None, prepared_by=None, prepared_for=None, crm_field=None, **_):
    """Which UTM sources bring leads on which CRM, from a 'which CRM do you use' style form field."""
    current, prior = list(current or []), _usable(prior)
    start, end = span(current)
    pstart, pend = span(prior) if prior else (None, None)
    m = meta(brand_profile, customer_name, customer_domain,
             compare_label=compare_label or (_prior_label(pstart, pend) if prior else "last period"),
             sources=None, prepared_by=prepared_by, prepared_for=prepared_for)
    name = "Source to CRM"
    if not current:
        return empty_report(name, m)
    if start is None:
        return _undated(name, m, current)
    period = period_label(start, end)
    total = len(current)
    key = (crm_field if crm_field and any(get_field(e, crm_field) for e in current)
           else _find_field(current, ("crm",), min_share=0))
    m["sources"] = [{"name": "UTM Grabber", "detail": _pl(total, "lead")}]
    if not key:
        fields = set()
        for e in current[:300]:
            fields.update(k for k in e if "handl" not in str(k).lower() and "utm" not in str(k).lower())
        return {"meta": m, "sections": [
            {"type": "title-block", "kicker": "%s · %s" % (name, period),
             "title": "This form doesn't ask which *CRM* a lead uses.",
             "subtitle": "So there is nothing to map yet. One new form question fixes that.",
             "meta_bits": [b for b in [customer_domain, "%s submissions" % n(total)] if b]},
            {"type": "stat-strip", "stats": [stat("Leads checked", n(total)), stat("Form fields scanned", n(len(fields))),
                                             stat("CRM answers", "0", good="neutral")]},
            {"type": "insight-card", "kicker": "What's needed", "title": "Add a *CRM* question to the form.",
             "tone": "warn",
             "body": ["We scanned %s form fields on %s and found none that names a CRM." % (n(len(fields)), _pl(total, "lead")),
                      "Add a dropdown such as “Which CRM do you use?” with HubSpot, Salesforce, Pipedrive, "
                      "Zoho, Other and No CRM. This report fills itself in as answers arrive."]},
            {"type": "closing", "kicker": "Next step", "title": "Next: add a *CRM* question to the form, then run this again.",
             "body": "Answers start mapping to UTM sources from the first new submission."}]}

    def crm_of(e):
        return _crm_name(get_field(e, key))

    answered = [e for e in current if crm_of(e)]
    rate = share(len(answered), total)
    if len(answered) < 10:
        return _short(name, m, answered or current, period,
                      why=["Only %s of %s answered the “%s” question, too few to map sources." % (
                          n(len(answered)), _pl(total, "lead"), _clean(key)),
                           "Make the question required, or widen the date range."],
                      ins_title="Mapping needs at least *10 answers*.",
                      title="Only %s named a *CRM* so far." % _pl(len(answered), "lead"),
                      next_title="Next: make the *CRM* question required and run this again.")
    crms = Counter(crm_of(e) for e in answered)
    srcs = Counter(_src(e) for e in answered)            # "" = no UTM source
    n_ans = len(answered)
    named = [c for c in crms if c not in ("No CRM", "Other")]
    crm_cols = [c for c, _ in crms.most_common()]
    if len(crm_cols) > 6:
        crm_cols = crm_cols[:5] + ["Other CRMs"]
    src_rows = [s for s, _ in srcs.most_common() if s][:7]
    if srcs.get(""):
        src_rows.append("")
    fold_c = set(crm_cols) if "Other CRMs" not in crm_cols else set(crm_cols[:-1])

    def col_of(c):
        return c if c in fold_c else "Other CRMs"

    cell = Counter((_src(e), col_of(crm_of(e))) for e in answered)
    row_label = {s: (source_label(s) if s else "No UTM source") for s in src_rows}
    values = [[cell.get((s, c), 0) for c in crm_cols] for s in src_rows]

    # lift: how much more often a source's leads name a CRM than leads overall
    pairs = []
    for s in [x for x in srcs if x]:
        for c in named:
            k = cell.get((s, c), 0) if c in fold_c else sum(1 for e in answered if _src(e) == s and crm_of(e) == c)
            exp = srcs[s] * crms[c] / float(n_ans)
            # a pairing counts only with 5+ leads and an excess beyond normal random swing (2 sd)
            if k >= 5 and exp > 0 and (k - exp) / math.sqrt(exp) >= 2:
                lift = (k / float(srcs[s])) / (crms[c] / float(n_ans))
                pairs.append((lift, k, s, c))
    pairs.sort(key=lambda x: (-x[0], -x[1], x[2], x[3]))
    strong = [p for p in pairs if p[0] >= 1.2]
    top_crm, top_crm_n = crms.most_common(1)[0]
    if top_crm in ("No CRM", "Other") and named:
        top_crm = max(named, key=lambda c: (crms[c], c))
        top_crm_n = crms[top_crm]
    feeders = Counter(_src(e) for e in answered if crm_of(e) == top_crm and _src(e))
    top_feed = feeders.most_common(1)[0] if feeders else None
    no_crm = crms.get("No CRM", 0)

    # prior for deltas
    prior_ans = [e for e in prior if crm_of(e)] if prior else []
    p_rate = share(len(prior_ans), len(prior)) if prior else None
    p_top = share(sum(1 for e in prior_ans if crm_of(e) == top_crm), len(prior_ans)) if prior_ans else None

    feed2 = feeders.most_common(2)
    if top_feed and len(feed2) > 1 and feed2[1][1] >= 0.9 * feed2[0][1]:
        who = "%s and %s" % (source_label(feed2[0][0]), source_label(feed2[1][0]))
        lead_share = share(feed2[0][1] + feed2[1][1], top_crm_n)
    elif top_feed:
        who = source_label(top_feed[0])
        lead_share = share(top_feed[1], top_crm_n)
    else:
        who, lead_share = None, 0
    headline = ("*%s* leads the CRM answers at %s, %s %s." % (
        top_crm, pct(share(top_crm_n, n_ans)), "mostly from" if lead_share >= 50 else "most often from", who)
                if who else "*%s* leads the CRM answers at %s." % (top_crm, pct(share(top_crm_n, n_ans))))
    sub = ["%s of %s answered the “%s” question." % (n(n_ans), _pl(total, "lead"), _clean(key))]
    if strong:
        lift, k, s, c = strong[0]
        sub.append("The clearest pairing: %s leads name %s %.1fx as often as average." % (source_label(s), c, lift))
    secs = [{"type": "title-block", "kicker": "Source to CRM · %s" % period, "title": headline, "subtitle": " ".join(sub),
             "meta_bits": [b for b in [customer_domain, form_label, "Field: %s" % _clean(key), "%s answers" % n(n_ans)] if b]},
            {"type": "stat-strip", "stats": [
                stat("Answered the CRM question", pct(rate), rate, p_rate, kind="pts",
                     note="%s of %s leads" % (n(n_ans), n(total))),
                stat("CRMs named", n(len(named)), good="neutral",
                     note="plus %s" % " and ".join(x for x in ("No CRM", "Other") if crms.get(x)) if crms.get("No CRM") or crms.get("Other") else None),
                stat("%s share" % top_crm, pct(share(top_crm_n, n_ans)), share(top_crm_n, n_ans), p_top, kind="pts",
                     good="neutral", note="Top CRM, %s" % _pl(top_crm_n, "answer")),
                stat("No CRM yet", pct(share(no_crm, n_ans)), good="neutral",
                     note="%s said they use none" % _pl(no_crm, "lead") if no_crm else "Every answer named a tool")]}]

    # 01 the map
    secs.append({"type": "section-header", "number": "01", "kicker": "The map",
                 "title": "Which sources bring which *CRM*.",
                 "dek": "Each cell counts the leads from one utm_source who named one CRM. Darker means more."})
    secs.append({"type": "heatmap", "chart_title": "Leads by source and *CRM*",
                 "rows": [row_label[s] for s in src_rows], "cols": crm_cols, "values": values,
                 "low_label": "Fewer", "high_label": "More",
                 "caption": "Top %s sources by answers%s." % (
                     n(len([s for s in src_rows if s])), ", plus leads with no UTM source" if "" in src_rows else "")})
    if strong:
        lift, k, s, c = strong[0]
        body = ["%s of %s leads use %s, against %s of all answers." % (
            pct(100.0 * k / srcs[s]), source_label(s), c, pct(share(crms[c], n_ans)))]
        second = next((p for p in strong[1:] if p[3] != c and p[2] != s), None)
        if second:
            body.append("%s leads lean %s: %s against %s overall (%.1fx)." % (
                source_label(second[2]), second[3], pct(100.0 * second[1] / srcs[second[2]]),
                pct(share(crms[second[3]], n_ans)), second[0]))
        body.append("Lift compares a source's CRM mix with the mix across all answers. Pairs count only with 5 or "
                    "more leads and an excess beyond normal random swing.")
        secs.append({"type": "insight-card", "kicker": "Match-making",
                     "title": "%s leads name *%s* %.1fx as often as average." % (source_label(s), c, lift), "body": body})
    else:
        secs.append({"type": "insight-card", "kicker": "Match-making",
                     "title": "No source leans hard toward one *CRM*.",
                     "body": ["No source names any CRM clearly more often than average: no pairing has 5 or more "
                              "leads and an excess beyond normal random swing.",
                              "Your message can stay CRM-neutral across channels for now."]})

    # 02 per CRM table
    rows = []
    for i, (c, v) in enumerate(crms.most_common(8)):
        f = Counter(_src(e) for e in answered if crm_of(e) == c and _src(e))
        best = max([p for p in pairs if p[3] == c], key=lambda p: (p[0], p[1]), default=None)
        rows.append({"rank": str(i + 1), "crm": c, "leads": {"value": v, "label": n(v)},
                     "share": pct(share(v, n_ans)),
                     "top": ("%s, %s" % (source_label(f.most_common(1)[0][0]), pct(share(f.most_common(1)[0][1], v))))
                     if f else "Not tagged",
                     "lean": ("%s, %.1fx" % (source_label(best[2]), best[0])) if best and best[0] >= 1.2 else "–"})
    secs.append({"type": "section-header", "number": "02", "kicker": "By CRM", "title": "Each *CRM* and where it comes from."})
    secs.append({"type": "ranked-list", "title": "CRMs by *answers*",
                 "columns": [{"key": "rank", "label": "#", "type": "rank"}, {"key": "crm", "label": "CRM", "type": "name"},
                             {"key": "leads", "label": "Leads", "type": "bar"},
                             {"key": "share", "label": "Share", "type": "pct", "align": "right"},
                             {"key": "top", "label": "Top source", "type": "text"},
                             {"key": "lean", "label": "Leans toward", "type": "text"}],
                 "rows": rows,
                 "caption": "Leans toward: the source whose leads name this CRM most often compared with average "
                            "(1.2x or more, 5+ leads, beyond normal random swing)."})

    # next steps
    recs = []
    used = set()
    for lift, k, s, c in strong:
        if len(recs) >= 2 or c in used or s in used:
            continue
        used.update([c, s])
        title = ("Speak *%s* in your %s ads" if not recs else "Build a *%s* landing page for %s traffic") % (c, source_label(s))
        recs.append({"label": "This month", "title": title,
                     "body": "%s of %s leads use %s, against %s overall (%.1fx). Name the integration in the ad and on "
                             "the page they land on." % (pct(100.0 * k / srcs[s]), source_label(s), c,
                                                         pct(share(crms[c], n_ans)), lift),
                     "impact": "Medium", "effort": "Medium" if recs else "Low"})
    if share(no_crm, n_ans) >= 15:
        recs.append({"label": "This quarter", "title": "Give *no-CRM* leads their own path",
                     "body": "%s of answers named no CRM. They need a simpler first step than leads who already run "
                             "one." % pct(share(no_crm, n_ans)), "impact": "Medium", "effort": "Medium"})
    if rate < 70:
        recs.append({"label": "This week", "title": "Make the *CRM* question required",
                     "body": "Only %s of leads answered it, so %s of leads can't be mapped." % (pct(rate), pct(100 - rate)),
                     "impact": "Medium", "effort": "Low"})
    if share(srcs.get("", 0), n_ans) >= 25:
        recs.append({"label": "This week", "title": "Tag the links behind *untagged* answers",
                     "body": "%s of CRM answers came with no UTM source, so their channel is unknown." % pct(share(srcs.get("", 0), n_ans)),
                     "impact": "Medium", "effort": "Low"})
    if len(recs) < 2:
        recs.append({"label": "Ongoing", "title": "Lead with *%s* in your messaging" % top_crm,
                     "body": "It is the most common CRM at %s of answers." % pct(share(top_crm_n, n_ans)),
                     "impact": "Medium", "effort": "Low"})
    if len(recs) < 2:
        recs.append({"label": "Next month", "title": "Re-run this map with more *answers*",
                     "body": "Pairings firm up as answers grow; %s answers is a start." % n(n_ans),
                     "impact": "Low", "effort": "Low"})
    secs.append({"type": "section-header", "number": "03", "kicker": "Next steps", "title": "Personalize by *CRM*."})
    secs.append({"type": "recommendations", "items": recs[:4]})
    secs.append({"type": "notes", "title": "How we built this report", "items": [
        "CRM answers come from the form field “%s”; spellings are grouped (for example “hubspot” and "
        "“HubSpot”), and answers such as “no” or “none” show as No CRM." % _clean(key),
        "Sources are each lead's last-touch utm_source, %s." % period,
        "Lift = the share of a source's leads naming a CRM, divided by that CRM's share of all answers."]})
    if strong:
        lift, k, s, c = strong[0]
        ctitle = "Next: speak *%s* in %s ads. %s of those leads use it." % (c, source_label(s), pct(100.0 * k / srcs[s]))
    elif rate < 70:
        ctitle = "Next: make the *CRM* question required. Only %s of leads answer it." % pct(rate)
    else:
        ctitle = "Next: lead with *%s* in your messaging. %s of leads use it." % (top_crm, pct(share(top_crm_n, n_ans)))
    secs.append({"type": "closing", "kicker": "The map in one line", "title": ctitle,
                 "summary_stats": [{"value": n(n_ans), "label": "CRM answers"},
                                   {"value": top_crm, "label": "Top CRM"},
                                   {"value": n(len(named)), "label": "CRMs named"},
                                   {"value": pct(share(no_crm, n_ans)), "label": "No CRM yet"}],
                 "bullets": [x for x in [
                     ("%s sends the most %s leads (%s)." % (source_label(top_feed[0]), top_crm,
                                                             pct(share(top_feed[1], top_crm_n)))) if top_feed else None,
                     "%s of leads answered the CRM question." % pct(rate),
                     ("%s pairing%s lean 1.2x or more toward one CRM." % (n(len(strong)), "" if len(strong) == 1 else "s"))
                     if strong else "No source leans hard toward one CRM."] if x]})
    return {"meta": m, "sections": secs}


# ---------------------------------------------------------------------------
# ANOMALY CHECK
# ---------------------------------------------------------------------------
_RANK = {"fail": 0, "warn": 1, "info": 2, "pass": 3}


def build_anomaly(current, baseline, brand_profile=None, customer_name=None, customer_domain="", form_label=None,
                  compare_label=None, prepared_by=None, prepared_for=None, **_):
    """What moved this period against its usual pace: channels, sources and campaigns, with the rule used."""
    current = list(current or [])
    m = meta(brand_profile, customer_name, customer_domain, compare_label=compare_label or "the usual pace",
             sources=None, prepared_by=prepared_by, prepared_for=prepared_for)
    name = "Anomaly check"
    if not current:
        return empty_report(name, m, reason="No form submissions arrived in this window.",
                            hint="If leads usually arrive every day, check that your forms submit and UTM Grabber is active.")
    start, end = span(current)
    if start is None:
        return _undated(name, m, current)
    base = [e for e in (baseline or []) if _day(e) is not None and _day(e) < start]   # never overlap the window
    days = (end - start).days + 1
    period = period_label(start, end)
    total = len(current)
    if not base:
        return _short(name, m, current, period,
                      why=["An anomaly is a change against a normal pace. We had no leads from before %s to set "
                           "that pace." % period_label(start, start),
                           "Pull the 30 days before this window as the baseline and run the check again."],
                      ins_title="We need a *baseline* to spot changes.",
                      title="No *baseline* to compare %s against." % _pl(total, "lead"),
                      next_title="Next: add the previous 30 days as a *baseline* and run this again.")
    bstart, bend = span(base)
    bdays = (bend - bstart).days + 1
    scale = days / float(bdays)
    exp_total = len(base) * scale
    if total < 10 and exp_total < 10:
        return _thin(name, m, current, period, _when(days))
    m["sources"] = [{"name": "UTM Grabber", "detail": "%s, %s baseline" % (_pl(total, "lead"), n(len(base)))}]

    checks = []

    def run(kind, key, label):
        cur, bas = Counter(key(e) for e in current), Counter(key(e) for e in base)
        for k in set(cur) | set(bas):
            if not k:
                continue
            c, exp = cur.get(k, 0), bas.get(k, 0) * scale
            item = {"kind": kind, "key": k, "label": label(k), "c": c, "exp": exp, "pct": None}
            if exp < 1:
                if c >= 3:
                    item.update(status="info", tag="New")
                    checks.append(item)
                continue
            p = 100.0 * (c - exp) / exp
            z = (c - exp) / math.sqrt(exp)
            item["pct"] = p
            if c == 0 and exp >= 3:                 # went quiet: checked before the 5-lead minimum
                item.update(status="fail" if exp >= 4 else "warn", tag="Gone")
                checks.append(item)
                continue
            if max(c, exp) < 5:
                continue
            if p <= -50 and z <= -2:
                item.update(status="fail", tag="Drop")
            elif p <= -25 and z <= -1.5:
                item.update(status="warn", tag="Watch")
            elif p >= 50 and z >= 2:
                item.update(status="info", tag="Spike")
            elif p >= 25 and z >= 1.5:
                item.update(status="pass", tag="Up")
            else:
                item.update(status="pass", tag="Normal")
            checks.append(item)

    run("channel", last_touch, lambda k: k)
    run("source", _src, source_label)
    run("campaign", _camp, pretty)
    flagged = [x for x in checks if x["status"] in ("fail", "warn") or x.get("tag") in ("Spike", "New")]
    # most serious first: Fix before Watch, then the most leads lost
    drops = sorted([x for x in flagged if x["status"] in ("fail", "warn")],
                   key=lambda x: (_RANK[x["status"]], -(x["exp"] - x["c"]), x["label"]))
    rises = sorted([x for x in flagged if x.get("tag") == "Spike"], key=lambda x: (-x["pct"], x["label"]))
    news = sorted([x for x in checks if x.get("tag") == "New" and x["kind"] == "source"], key=lambda x: (-x["c"], x["label"]))
    gone = [x for x in drops if x.get("tag") == "Gone" and x["kind"] == "source"]
    when = _when(days)

    # headline
    def subject(x):
        return {"campaign": "The *%s* campaign", "channel": "*%s* traffic"}.get(x["kind"], "*%s*") % x["label"]

    if drops:
        x = drops[0]
        headline = ("%s went quiet %s: no leads against about %s expected." % (subject(x), when, n(round(x["exp"])))
                    if x["c"] == 0 else
                    "%s ran %s below its usual pace %s." % (subject(x), _signed(x["pct"])[1:], when))
    elif rises:
        x = rises[0]
        headline = "%s ran %s above its usual pace %s." % (subject(x), _signed(x["pct"])[1:], when)
    else:
        headline = "No *anomalies* %s." % when
    d_all = delta(total, exp_total)
    sub = [] if (drops or rises) else ["Every channel, source and campaign stayed in its normal range."]
    sub += ["%s against about %s expected from the %d-day baseline (%s)." % (
        _pl(total, "lead").capitalize(), n(round(exp_total)), bdays,
        d_all.get("delta_label", "flat").replace("Flat", "flat")),
        "%s of %s checks flagged." % (n(len(flagged)), n(len(checks)))]
    allp = [x for x in checks if x["pct"] is not None]
    worst = min(allp, key=lambda x: x["pct"]) if allp else None
    best = max(allp, key=lambda x: x["pct"]) if allp else None
    labels_all, daily_all = daily_counts(base + current, bstart, end)
    split = len(labels_all) - days
    for i in range(bdays, split):                   # days between baseline and window: no data, not zero
        daily_all[i] = None
    secs = [{"type": "title-block", "kicker": "Anomaly check · %s" % period, "title": headline, "subtitle": " ".join(sub),
             "meta_bits": [b for b in [customer_domain, "Baseline: %s" % period_label(bstart, bend), _pl(days, "day")] if b]},
            {"type": "stat-strip", "stats": [
                dict(stat("Leads", n(total), total, exp_total, spark=daily_all[-min(len(daily_all), 30):],
                          note="About %s expected" % n(round(exp_total))), compare="the usual pace"),
                stat("Flagged", n(len(flagged)), good="neutral",
                     note="%s down, %s up or new" % (n(len(drops)), n(len(flagged) - len(drops)))),
                stat("Largest drop", _signed(worst["pct"]) if worst and worst["pct"] < 0 else "\u2013", good="neutral",
                     note=("%s (%s)%s" % (worst["label"], worst["kind"], "" if worst["status"] in ("fail", "warn")
                                           else ", within normal swing")) if worst and worst["pct"] < 0 else "Nothing fell"),
                stat("Largest rise", _signed(best["pct"]) if best and best["pct"] > 0 else "\u2013", good="neutral",
                     note=("%s (%s)%s" % (best["label"], best["kind"], "" if best.get("tag") == "Spike"
                                           else ", within normal swing")) if best and best["pct"] > 0 else "Nothing rose")]}]

    # 01 scorecard
    order = sorted(checks, key=lambda x: (_RANK[x["status"]], -(abs(x["pct"]) if x["pct"] is not None else 999),
                                          -x["exp"], x["label"]))
    shown = [x for x in order if x["status"] != "pass"][:8]
    healthy = [x for x in order if x["status"] == "pass" and x["kind"] == "channel"]
    shown += healthy[:max(0, 5 - len(shown))]          # top up with healthy channels so the card reads in context
    items = []
    for x in shown:
        val = "New" if x.get("tag") == "New" else _signed(x["pct"])
        items.append({"label": "%s (%s)" % (x["label"], x["kind"]), "value": val, "status": x["status"],
                      "status_label": {"Gone": "Fix" if x["status"] == "fail" else "Watch", "Drop": "Fix",
                                       "Watch": "Watch", "Spike": "Spike", "New": "New", "Up": "Up",
                                       "Normal": "Healthy"}[x["tag"]],
                      "detail": "%s %s against about %s expected." % (_pl(x["c"], "lead").capitalize(), when,
                                                                      n(round(x["exp"]))) if x.get("tag") != "New" else
                      "%s %s; under 1 expected from the baseline." % (_pl(x["c"], "lead").capitalize(), when)})
    secs.append({"type": "section-header", "number": "01", "kicker": "The scorecard", "title": "What *moved*, and how far.",
                 "dek": "Flagged items first. Fix: a drop of half or more. Watch: a drop of a quarter or more. Both "
                        "must be bigger than normal random swing."})
    secs.append({"type": "scorecard", "title": "Checks against the *baseline*", "items": items})

    # 02 by source
    src_checks = [x for x in checks if x["kind"] == "source" and x["pct"] is not None and max(x["c"], x["exp"]) >= 3]
    src_checks = sorted(src_checks, key=lambda x: (-max(x["c"], x["exp"]), x["label"]))[:8]
    calls = []
    if news:
        x = news[0]
        calls.append({"kicker": "New source", "value": n(x["c"]), "tone": "neutral",
                      "title": "leads from %s, which the baseline never saw" % x["label"]})
    if gone:
        x = gone[0]
        calls.append({"kicker": "Went quiet", "value": "0", "tone": "bad",
                      "title": "leads from %s, against about %s expected" % (x["label"], n(round(x["exp"])))})
    if drops and not (gone and drops[0] is gone[0]):
        x = drops[0]
        calls.append({"kicker": "Biggest drop", "value": _signed(x["pct"]), "tone": "bad",
                      "title": "%s: %s against about %s" % (x["label"], _pl(x["c"], "lead"), n(round(x["exp"])))})
    if rises:
        x = rises[0]
        calls.append({"kicker": "Biggest spike", "value": _signed(x["pct"]), "tone": "warn",
                      "title": "%s: %s against about %s" % (x["label"], _pl(x["c"], "lead"), n(round(x["exp"])))})
    if len(calls) == 1:
        calls.append({"kicker": "Total leads", "value": n(total), "tone": "neutral",
                      "title": "%s against about %s expected" % (when, n(round(exp_total)))})
    secs.append({"type": "section-header", "number": "02", "kicker": "By source",
                 "title": "Every *source* against its usual pace."})
    if len(src_checks) >= 2:
        vals = [round(max(-100.0, min(200.0, x["pct"]))) for x in src_checks]
        secs.append({"type": "chart", "chart": {"type": "bar-diverging", "labels": [x["label"] for x in src_checks],
                                                "values": vals, "unit": "%", "good": "up"},
                     "chart_title": "Change against the usual pace, by *source*",
                     "caption": "Top %s sources by volume. Expected = baseline leads scaled to %s.%s" % (
                         n(len(src_checks)), _pl(days, "day"), " Rises are capped at +200%." if any(v >= 200 for v in vals) else "")})
    if calls:
        secs.append({"type": "callouts", "items": calls[:4]})

    # 03 daily
    base_avg = len(base) / float(bdays)
    s_base = daily_all[:split] + [None] * days
    s_cur = [None] * (split - 1) + daily_all[split - 1:] if split >= 1 else daily_all
    secs.append({"type": "section-header", "number": "03", "kicker": "Daily",
                 "title": "The window against the *baseline*.",
                 "dek": "Leads per day. The dashed line is the baseline's daily average."})
    secs.append({"type": "chart", "chart": {"type": "line-multi", "labels": labels_all, "end_labels": False,
                                            "series": [{"label": "Baseline", "values": s_base},
                                                       {"label": "This window" if days != 7 else "This week", "values": s_cur},
                                                       {"label": "Baseline average", "values": [round(base_avg, 2)] * len(labels_all),
                                                        "style": "dashed"}]},
                 "chart_title": "Leads per *day*",
                 "caption": "Baseline average %.1f a day; this window %.1f a day." % (base_avg, total / float(days))})

    # next steps: investigations, not fixes
    def advice(x):
        if x["kind"] == "source" and any(a in x["key"] for a in _AI):
            return "AI assistant answers shift often; check whether it still recommends you."
        if x["kind"] == "channel":
            ch = x["key"]
        else:
            fn = _src if x["kind"] == "source" else _camp
            top = Counter(last_touch(e) for e in base + current if fn(e) == x["key"]).most_common(1)
            ch = top[0][0] if top else ""
        return {"Paid": "Look at account status, budgets, rejected ads and the landing page before you change anything.",
                "Organic": "Look at rankings, indexing and whether the landing pages still load.",
                "Social": "Look at posting volume and whether links in posts and bios still work.",
                "Referral": "Look at the sites and emails that link to you, and whether those links still work.",
                "Direct": "Test every form on the site and check that UTM Grabber is still active."}.get(
            ch, "Check that its links still work and the landing pages still load.")

    recs = []
    for x in drops[:2]:
        if x["kind"] == "channel":
            title = "Check *%s* traffic end to end" % x["label"].lower()
        elif x["kind"] == "campaign":
            title = "Check the *%s* campaign" % x["label"]
        else:
            title = "Check what changed on *%s*" % x["label"]
        recs.append({"label": "Today" if x["status"] == "fail" else "This week", "title": title,
                     "body": "%s %s against about %s expected. %s" % (_pl(x["c"], "lead").capitalize(), when,
                                                                    n(round(x["exp"])), advice(x)),
                     "impact": "High" if x["status"] == "fail" else "Medium", "effort": "Low",
                     "metric": "%s vs usual" % _signed(x["pct"])})
    if rises:
        x = rises[0]
        recs.append({"label": "This week", "title": "Confirm the *%s* spike is real" % x["label"],
                     "body": "%s against about %s expected. Look for spam or duplicate submissions before you shift "
                             "budget toward it." % (_pl(x["c"], "lead").capitalize(), n(round(x["exp"]))),
                     "impact": "Medium", "effort": "Low"})
    if news and len(recs) < 4:
        x = news[0]
        recs.append({"label": "This week", "title": "Find what sent the *%s* leads" % x["label"],
                     "body": "%s arrived from a source the baseline never saw. If it's a mention or a partner, follow "
                             "up while it's fresh." % _pl(x["c"], "lead").capitalize(), "impact": "Low", "effort": "Low"})
    if not drops:
        near = [x for x in checks if x["pct"] is not None and x["pct"] <= -15 and x["status"] == "pass"]
        if near:
            x = min(near, key=lambda y: y["pct"])
            recs.append({"label": "Next week", "title": "Keep an eye on *%s*" % x["label"],
                         "body": "It ran %s below its usual pace, inside the normal range but the closest call." % (
                             _signed(x["pct"])[1:]), "impact": "Low", "effort": "Low"})
    recs.append({"label": "Ongoing", "title": "Run this *check* every week",
                 "body": "A weekly run catches a broken form or a paused campaign within days, not at month end.",
                 "impact": "Medium", "effort": "Low"})
    secs.append({"type": "section-header", "number": "04", "kicker": "What to check",
                 "title": "Where to *look* first.", "dek": "Investigations, not fixes: confirm the cause before you act."})
    secs.append({"type": "recommendations", "items": recs[:4]})
    secs.append({"type": "notes", "title": "How we built this check", "items": [
        "This window: %s (%s). Baseline: %s (%s, %s), scaled to %s to get each expected count." % (
            period, _pl(days, "day"), period_label(bstart, bend), _pl(bdays, "day"), _pl(len(base), "lead"),
            _pl(days, "day")),
        "A drop is flagged when it is 25% or more, involves at least 5 leads, and is bigger than normal random swing "
        "for that volume (1.5 standard deviations to watch, 2 to fix).",
        "New: under 1 lead expected and 3 or more arrived. Went quiet: 3 or more expected and none arrived."]})
    if drops:
        x = drops[0]
        what = subject(x).replace("The *", "the *")
        ctitle = "Next: check %s %s. It ran %s below its usual pace." % (
            what, "today" if x["status"] == "fail" else "this week", _signed(x["pct"])[1:]) if x["c"] else \
            "Next: check %s today. It sent no leads against about %s expected." % (what, n(round(x["exp"])))
    elif rises:
        x = rises[0]
        ctitle = "Next: confirm the *%s* spike. It ran %s above its usual pace." % (x["label"], _signed(x["pct"])[1:])
    else:
        ctitle = "Next: run this *check* again next week. Nothing broke the normal range."
    secs.append({"type": "closing", "kicker": "The check in one line", "title": ctitle,
                 "summary_stats": [{"value": n(total), "label": "Leads"},
                                   {"value": n(round(exp_total)), "label": "Expected"},
                                   {"value": n(len(flagged)), "label": "Flagged"},
                                   {"value": n(len(checks)), "label": "Checks run"}],
                 "bullets": [x for x in [
                     ("%s: %s, against about %s." % (drops[0]["label"], _signed(drops[0]["pct"]), n(round(drops[0]["exp"]))))
                     if drops else None,
                     ("%s: %s, against about %s." % (rises[0]["label"], _signed(rises[0]["pct"]), n(round(rises[0]["exp"]))))
                     if rises else None,
                     "Baseline: %s a day; this window: %s a day." % ("%.1f" % base_avg, "%.1f" % (total / float(days)))] if x]})
    return {"meta": m, "sections": secs}


# ---------------------------------------------------------------------------
# LEAD FORECAST
# ---------------------------------------------------------------------------
def _fit(weeks):
    """Least-squares line through weekly totals. Returns (a, b, sigma_w, significant)."""
    W = len(weeks)
    if W < 4:
        lvl = sum(weeks[-4:]) / float(len(weeks[-4:])) if weeks else 0.0
        resid = [w - lvl for w in weeks]
        sig_w = math.sqrt(sum(r * r for r in resid) / max(1, W - 1)) if W > 1 else 0.0
        return lvl, 0.0, sig_w, False
    xs = list(range(W))
    mx, my = sum(xs) / float(W), sum(weeks) / float(W)
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, weeks)) / sxx
    a = my - b * mx
    resid = [y - (a + b * x) for x, y in zip(xs, weeks)]
    sse = sum(r * r for r in resid)
    se_b = math.sqrt(sse / (W - 2) / sxx) if W > 2 else 0.0
    significant = b != 0 and abs(b) >= 2 * se_b
    if not significant:
        lvl = sum(weeks[-4:]) / 4.0
        resid = [y - my for y in weeks]
        return lvl, 0.0, math.sqrt(sum(r * r for r in resid) / max(1, W - 1)), False
    return a + b * (W - 1), b, math.sqrt(sse / max(1, W - 2)), True


def build_forecast(history, brand_profile=None, customer_name=None, customer_domain="", form_label=None,
                   compare_label=None, prepared_by=None, prepared_for=None, **_):
    """Next 7 and 30 days from 30 to 120 days of history: weekday pattern x weekly trend, with a likely range."""
    history = list(history or [])
    m = meta(brand_profile, customer_name, customer_domain, compare_label=compare_label or "the last 30 days",
             sources=None, prepared_by=prepared_by, prepared_for=prepared_for)
    name = "Lead forecast"
    if not history:
        return empty_report(name, m, reason="There is no lead history to project from.")
    start, end = span(history)
    if start is None:
        return _undated(name, m, history)
    days = (end - start).days + 1
    period = period_label(start, end)
    total = len(history)
    if total < 10:
        return _thin(name, m, history, period, "the history")
    if days < 21:
        return _short(name, m, history, period,
                      why=["A forecast learns a weekday pattern and a trend. %s of history (%s) is not enough to "
                           "tell either from noise." % (_pl(days, "day"), _pl(total, "lead")),
                           "At today's pace of %.1f a day, 30 days would bring about %s, but treat that as a guess." % (
                               total / float(days), n(_about(total / float(days) * 30)))],
                      ins_title="A forecast needs *3 weeks* of history.",
                      title="%s is too little *history* to forecast." % _pl(days, "day"),
                      next_title="Next: re-run the forecast with at least *4 weeks* of history.")
    m["sources"] = [{"name": "UTM Grabber", "detail": "%s over %d days" % (_pl(total, "lead"), days)}]
    labels, daily = daily_counts(history, start, end)
    W = days // 7
    weeks = [sum(daily[days - 7 * (W - i): days - 7 * (W - i - 1)]) for i in range(W)]
    # weekday pattern, averaged over the whole history and normalized to an average of 1
    wd_sum, wd_n = [0.0] * 7, [0] * 7
    for i, v in enumerate(daily):
        wd = (start + i * _ONE_DAY).weekday()
        wd_sum[wd] += v
        wd_n[wd] += 1
    wd_mean = [wd_sum[i] / wd_n[i] if wd_n[i] else 0.0 for i in range(7)]
    base_mean = sum(wd_mean) / 7.0
    factor = [x / base_mean if base_mean else 1.0 for x in wd_mean]
    level, slope, sig_w, trending = _fit(weeks)

    def wk(t):                       # weekly level t weeks after the last full week
        return max(0.0, level + slope * t)

    # in-sample daily residuals for the daily band
    resid = []
    for i in range(days - 7 * W, days):
        t = (i - (days - 1)) / 7.0
        fit_d = wk(t) / 7.0 * factor[(start + i * _ONE_DAY).weekday()]
        resid.append(daily[i] - fit_d)
    sig_d = math.sqrt(sum(r * r for r in resid) / max(1, len(resid) - 2)) if resid else 0.0
    fc = []
    for j in range(1, 31):
        fc.append(wk(j / 7.0) / 7.0 * factor[(end + j * _ONE_DAY).weekday()])
    f7, f30 = sum(fc[:7]), sum(fc)

    def rng(k, f):
        half = 1.2816 * max(sig_w * math.sqrt(k / 7.0), math.sqrt(max(f, 0.0)))
        return _about(max(0.0, f - half)), _about(f + half)

    lo7, hi7 = rng(7, f7)
    lo30, hi30 = rng(30, f30)
    last30 = sum(daily[-30:]) if days >= 30 else None
    pace30 = total / float(days) * 30
    ref30 = last30 if last30 is not None else pace30
    ref_label = "the last 30 days" if last30 is not None else "today's pace"
    m["compare_label"] = compare_label or ref_label
    g30 = _growth(f30, ref30) if ref30 else None
    peak_wd = max(range(7), key=lambda i: wd_mean[i])
    low_wd = min(range(7), key=lambda i: wd_mean[i])
    wd_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    second = sorted(wd_mean, reverse=True)[1]
    clear_peak = second > 0 and wd_mean[peak_wd] >= 1.1 * second
    wkday = sum(wd_mean[:5]) / 5.0
    wkend = sum(wd_mean[5:]) / 2.0
    busy_short = wd_names[peak_wd][:3] if clear_peak else ("Mon to Fri" if wkday and wkend < 0.7 * wkday else "Even")
    busy_phrase = ("%ss busiest" % wd_names[peak_wd]) if clear_peak else (
        "weekdays busiest" if wkday and wkend < 0.7 * wkday else "an even spread across the week")

    # headline
    headline = "Expect about *%s* in the next 30 days." % _pl(_about(f30), "lead")
    sub = ["The likely range is %s to %s, based on %d weeks of history." % (n(lo30), n(hi30), W)]
    if g30 is not None and abs(g30) >= 3:
        sub.append("That is about %s %s than %s." % (pct(abs(g30)), "more" if g30 > 0 else "fewer", ref_label))
    else:
        sub.append("That is level with %s." % ref_label)
    trend_word = ("%s by about %s a week" % ("rising" if slope > 0 else "falling", _pl(abs(round(slope)), "lead"))
                  if trending and round(slope) else "flat")
    trend_pct = 100.0 * slope / level if level else 0.0

    # chart: last 12 weeks of actuals + 30 forecast days
    show = min(days, 84)
    lab_h = labels[-show:]
    lab_f = ["%s %d" % ((end + j * _ONE_DAY).strftime("%b"), (end + j * _ONE_DAY).day) for j in range(1, 31)]
    act = daily[-show:] + [None] * 30
    fser = [None] * (show - 1) + [daily[-1]] + [round(x, 1) for x in fc]
    upper = [None] * show + [round(x + 1.2816 * max(sig_d, math.sqrt(x)), 1) for x in fc]
    lower = [None] * show + [round(max(0.0, x - 1.2816 * max(sig_d, math.sqrt(x))), 1) for x in fc]

    secs = [{"type": "title-block", "kicker": "Lead forecast · Next 30 days", "title": headline, "subtitle": " ".join(sub),
             "meta_bits": [b for b in [customer_domain, "History: %s" % period, "%s" % _pl(total, "lead")] if b]},
            {"type": "stat-strip", "stats": [
                stat("Next 7 days (about)", n(_about(f7)), good="neutral", note="Likely %s to %s" % (n(lo7), n(hi7)),
                     spark=weeks[-12:]),
                stat("Next 30 days (about)", n(_about(f30)), f30, ref30, good="up",
                     note="%s %s" % (n(round(ref30)), ref_label)),
                stat("Likely range, 30 days", "\u00b1%s" % n(_about((hi30 - lo30) / 2.0)), good="neutral",
                     note="%s to %s: where 4 in 5 periods like your past ones land" % (n(lo30), n(hi30))),
                stat("Trend, leads a week", _sn(int(round(slope))) if trending and round(slope) else "Flat",
                     good="neutral", note=("About %s%% a week, fitted on %s weekly totals" % (
                         ("%.1f" % abs(trend_pct)) if abs(trend_pct) < 10 else n(abs(round(trend_pct))), n(W)))
                     if trending and round(slope) else "Fitted on %s weekly totals" % n(W))]}]

    secs.append({"type": "section-header", "number": "01", "kicker": "The forecast",
                 "title": "The next 30 days, *day* by day.",
                 "dek": "Actual leads, then the forecast. The band is the likely range for each day."})
    secs.append({"type": "chart", "chart": {"type": "line-multi", "labels": lab_h + lab_f, "end_labels": False,
                                            "series": [{"label": "Actual", "values": act},
                                                       {"label": "Forecast", "values": fser}],
                                            "band": {"upper": upper, "lower": lower},
                                            "forecast_start": show, "forecast_label": "Forecast"},
                 "chart_title": "Leads per *day*: actual and forecast",
                 "caption": "Last %d days of history, then 30 forecast days. The weekly trend is %s." % (show, trend_word)})

    # weekday pattern
    order = list(range(7))
    secs.append({"type": "chart-insight",
                 "chart": {"type": "bar-vertical", "labels": [wd_names[i][:3] for i in order],
                           "values": [round(wd_mean[i], 1) for i in order],
                           "highlight": peak_wd if clear_peak else None},
                 "caption": "Average leads per weekday across the history",
                 "insight_kicker": "The weekly rhythm",
                 "insight_title": ("*%s* is your busiest day." % wd_names[peak_wd]) if clear_peak else (
                     ("*Weekends* run at %s of a weekday." % pct(100.0 * wkend / wkday)) if wkday and wkend < 0.7 * wkday
                     else "Leads arrive evenly through the *week*."),
                 "insight_body": ["%ss average %.1f leads; %ss average %.1f." % (
                     wd_names[peak_wd], wd_mean[peak_wd], wd_names[low_wd], wd_mean[low_wd]),
                     "The forecast repeats this pattern, so plan follow-up capacity around it."]})

    # 02 by channel
    ch_rows, ch_fc = [], {}
    for ch in CHANNELS:
        _, dch = daily_counts(history, start, end, predicate=lambda e, c=ch: last_touch(e) == c)
        if not sum(dch):
            continue
        wch = [sum(dch[days - 7 * (W - i): days - 7 * (W - i - 1)]) for i in range(W)]
        lv, sl, _s, tr = _fit(wch)
        raw = sum(max(0.0, lv + sl * (j / 7.0)) / 7.0 for j in range(1, 31))
        ch_fc[ch] = (raw, sl, tr, sum(dch[-30:]) if days >= 30 else sum(dch) / float(days) * 30)
    raw_sum = sum(v[0] for v in ch_fc.values()) or 1.0
    for ch, (raw, sl, tr, recent) in sorted(ch_fc.items(), key=lambda kv: -kv[1][0]):
        f = raw * f30 / raw_sum                   # scale so channels add up to the total forecast
        state = ({"state": "rising", "label": "Rising"} if sl > 0 else {"state": "cooling", "label": "Cooling"}) \
            if tr and round(sl) else {"state": "steady", "label": "Steady"}
        fr = _about(f)                            # compare what the reader sees
        ch_rows.append({"ch": ch, "recent": n(round(recent)), "fc": {"value": f, "label": n(fr)},
                        "change": {"label": _signed(_growth(fr, recent)), "direction": "up" if fr > recent else "down"}
                        if recent and abs(_growth(fr, recent)) >= 3 else {"label": "Flat", "direction": "flat"},
                        "trend": state})
    secs.append({"type": "section-header", "number": "02", "kicker": "By channel",
                 "title": "Where the next 30 days of *leads* come from.",
                 "dek": "Each channel's own weekly trend, scaled so the channels add up to the total forecast."})
    secs.append({"type": "ranked-list", "title": "Channel *forecast*",
                 "columns": [{"key": "ch", "label": "Channel", "type": "name"},
                             {"key": "recent", "label": "Last 30 days" if days >= 30 else "Pace over 30 days",
                              "type": "number", "align": "right"},
                             {"key": "fc", "label": "Next 30 days (about)", "type": "bar"},
                             {"key": "change", "label": "Change", "type": "delta", "align": "right"},
                             {"key": "trend", "label": "Weekly trend", "type": "trend"}],
                 "rows": ch_rows,
                 "caption": "Rising or Cooling only when the channel's weekly trend is bigger than its week-to-week noise."})

    # 03 method
    secs.append({"type": "section-header", "number": "03", "kicker": "Method", "title": "How the *forecast* works."})
    secs.append({"type": "notes", "title": "Method, in plain words", "items": [
        "We counted leads per day for %d days (%s, %s)." % (days, period, _pl(total, "lead")),
        "Weekday pattern: each weekday's average against the overall average. %ss run %.1fx an average day; %ss "
        "run %.1fx." % (wd_names[peak_wd], factor[peak_wd], wd_names[low_wd], factor[low_wd]),
        ("Trend: a straight line through %d weekly totals. It %s about %s a week and is bigger than the "
         "week-to-week noise, so the forecast follows it." % (W, "adds" if slope > 0 else "takes away",
                                                             _pl(abs(int(round(slope))), "lead"))) if trending else
        ("Trend: a straight line through %d weekly totals was too small to tell from noise, so the forecast holds "
         "the recent level of about %s leads a week." % (W, n(_about(level)))),
        "Range: past weeks varied by about %s leads around the fitted line. The range covers roughly 4 in 5 "
        "outcomes and is never narrower than normal count noise." % n(round(sig_w)),
        "It assumes campaigns, budgets and tracking stay as they are. A launch, a paused campaign or a tracking fix "
        "will break the pattern."]})

    # next steps
    recs = [{"label": "This month", "title": "Plan follow-up for about *%s*" % _pl(_about(f30), "lead"),
             "body": "Staff for the low end (%s) and keep room for %s. That is about %.0f a day, with %s." % (
                 n(lo30), n(hi30), f30 / 30.0, busy_phrase), "impact": "High", "effort": "Low",
             "metric": "%s to %s" % (n(lo30), n(hi30))}]
    rising_ch = [r for r in ch_rows if r["trend"]["state"] == "rising"]
    cooling_ch = [r for r in ch_rows if r["trend"]["state"] == "cooling"]
    if rising_ch:
        r = rising_ch[0]
        recs.append({"label": "This month", "title": "Budget for more *%s* leads" % r["ch"].lower(),
                     "body": "%s is trending up. Make sure campaigns and follow-up can absorb about %s leads in the "
                             "next 30 days, against %s in %s." % (r["ch"], r["fc"]["label"], r["recent"],
                                                                  "the last 30" if days >= 30 else "a 30-day pace"),
                     "impact": "Medium", "effort": "Medium"})
    if cooling_ch:
        r = cooling_ch[0]
        recs.append({"label": "This week", "title": "Find what is slowing *%s*" % r["ch"].lower(),
                     "body": "It is trending down. If nothing changes, expect about %s leads in the next 30 days "
                             "against %s." % (r["fc"]["label"], r["recent"]), "impact": "High", "effort": "Low"})
    recs.append({"label": "After big changes", "title": "Re-run the forecast after a *launch* or pause",
                 "body": "A new campaign, a budget shift or a tracking fix changes the pattern this forecast learns from.",
                 "impact": "Low", "effort": "Low"})
    secs.append({"type": "section-header", "number": "04", "kicker": "Next steps", "title": "Plan for the likely *path*."})
    secs.append({"type": "recommendations", "items": recs[:4]})
    secs.append({"type": "closing", "kicker": "The forecast in one line",
                 "title": "Next: plan for about *%s*. Expect %s to %s in the next 30 days." % (
                     _pl(_about(f30), "lead"), n(lo30), n(hi30)),
                 "summary_stats": [{"value": n(_about(f7)), "label": "Next 7 days"},
                                   {"value": n(_about(f30)), "label": "Next 30 days"},
                                   {"value": "%s to %s" % (n(lo30), n(hi30)), "label": "Likely range"},
                                   {"value": busy_short, "label": "Busiest days" if not clear_peak else "Busiest day"}],
                 "bullets": [x for x in [
                     ("About %s %s than %s." % (pct(abs(g30)), "more" if g30 > 0 else "fewer", ref_label))
                     if g30 is not None and abs(g30) >= 3 else "Level with %s." % ref_label,
                     "Weekly trend: %s." % trend_word,
                     ("%s is trending up." % rising_ch[0]["ch"]) if rising_ch else
                     (("%s is trending down." % cooling_ch[0]["ch"]) if cooling_ch else "Every channel is steady.")] if x]})
    return {"meta": m, "sections": secs}


REGISTRY = {
    "paid-vs-organic": build_paid_vs_organic, "paid-organic": build_paid_vs_organic,
    "source-to-crm": build_source_to_crm, "source-crm": build_source_to_crm, "crm": build_source_to_crm,
    "anomaly": build_anomaly, "anomalies": build_anomaly, "what-changed": build_anomaly,
    "forecast": build_forecast, "predictive-forecast": build_forecast, "predict": build_forecast,
}
