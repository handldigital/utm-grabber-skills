"""
Core v2 recipes: the monthly flagship (reference implementation for every other
recipe), plus weekly, campaign leaderboard, campaign deep dive, side-by-side and
agency rollup.

Pattern every recipe follows:
  1. Guard empty input -> common.empty_report().
  2. Compute every number from the inputs (never invent one).
  3. Write the headline from the data: outcome first, one *accent* noun.
  4. Sections in reading order; each section answers one question.
  5. Recommendations are derived from thresholds in the data, highest impact first.
  6. Closing title is a concrete next step with the number that justifies it.
"""
import datetime as _dt
import re
from collections import Counter
from statistics import median

from .common import (CHANNELS, daily_counts, delta, empty_report, entry_dt, first_touch, get_field, last_touch,
                     lead_campaign, meta, money, n, norm_key, pct, period_label, period_name, pretty, prior_name,
                     share, source_label, span, stat, top_with_other)

# ---------------------------------------------------------------------------
# helpers shared by the core recipes
# ---------------------------------------------------------------------------
def _sources(entries):
    c = Counter()
    for e in entries:
        s = get_field(e, "utm_source (HandL)", "utm_source").lower()
        if s:
            c[s] += 1
    return c


def _campaigns(entries):
    c = Counter()
    for e in entries:
        k = lead_campaign(e)
        if k:
            c[k.lower()] += 1
    return c


def _coverage(entries):
    if not entries:
        return 0.0
    full = sum(1 for e in entries if get_field(e, "utm_source (HandL)", "utm_source")
               and get_field(e, "utm_medium (HandL)", "utm_medium") and lead_campaign(e))
    return share(full, len(entries))


def _channel_counts(entries, fn=last_touch):
    c = Counter(fn(e) for e in entries)
    return [(ch, c.get(ch, 0)) for ch in CHANNELS]


def _has_first_touch(entries):
    hits = sum(1 for e in entries[:200] if get_field(e, "utm_source (first touch, HandL)",
                                                    "traffic_source (first touch, HandL)"))
    return hits >= max(5, len(entries[:200]) // 10)


def _trend_state(cur, prev):
    if prev == 0 and cur > 0:
        return {"state": "rising", "label": "New"}
    if prev == 0:
        return {"state": "cold", "label": "No leads"}
    ch = (cur - prev) / float(prev)
    if ch >= 0.15:
        return {"state": "rising", "label": "Rising"}
    if ch <= -0.5:
        return {"state": "cold", "label": "Stalling"}
    if ch <= -0.15:
        return {"state": "cooling", "label": "Cooling"}
    return {"state": "steady", "label": "Steady"}


def _delta_cell(cur, prev):
    d = delta(cur, prev)
    if "delta_label" not in d:
        return {"label": "–", "direction": "flat"}
    return {"label": d["delta_label"], "direction": d["delta_direction"]}


# ---------------------------------------------------------------------------
# MONTHLY PERFORMANCE REVIEW (flagship)
# ---------------------------------------------------------------------------
def build_monthly(current, prior=None, brand_profile=None, customer_name=None, customer_domain="",
                  form_label=None, compare_label=None, prepared_by=None, prepared_for=None, **_):
    """The 30-day story: volume, channel mix, sources, campaigns, rhythm, next steps."""
    prior = prior or []
    start, end = span(current)
    period = period_label(start, end)
    pstart0, pend0 = span(prior) if prior else (None, None)
    m = meta(brand_profile, customer_name, customer_domain,
             compare_label=compare_label or (prior_name(pstart0, pend0) if prior else "last period"),
             sources=None, prepared_by=prepared_by, prepared_for=prepared_for)
    if not current:
        return empty_report("Monthly performance review", m)
    total, total_prior = len(current), len(prior)
    days = max(1, (end - start).days + 1)
    per_day = total / float(days)
    pstart, pend = span(prior) if prior else (None, None)
    pdays = max(1, (pend - pstart).days + 1) if prior else days
    per_day_prior = total_prior / float(pdays) if prior else None

    chans = _channel_counts(current)
    chans_prior = dict(_channel_counts(prior)) if prior else {}
    paid_share = share(dict(chans)["Paid"], total)
    paid_share_prior = share(chans_prior.get("Paid", 0), total_prior) if prior else None
    cov, cov_prior = _coverage(current), (_coverage(prior) if prior else None)

    src = _sources(current)
    src_prior = _sources(prior)
    top_src, top_src_n = (src.most_common(1)[0] if src else ("direct", 0))
    camps = _campaigns(current)
    camps_prior = _campaigns(prior)
    labels, daily = daily_counts(current, start, end)
    _, daily_prior = daily_counts(prior, pstart, pend) if prior else ([], [])
    m["sources"] = [{"name": "UTM Grabber", "detail": "%s leads" % n(total)}]

    # headline
    if prior:
        d = delta(total, total_prior)
        if d.get("delta_direction") == "up":
            headline = "%s brought %s *leads*, %s more than %s." % (
                end.strftime("%B"), n(total), d["delta_label"].lstrip("+"), m["compare_label"])
        elif d.get("delta_direction") == "down":
            headline = "%s brought %s *leads*, %s fewer than %s." % (
                end.strftime("%B"), n(total), d["delta_label"].lstrip("−"), m["compare_label"])
        else:
            headline = "%s held steady at %s *leads*." % (end.strftime("%B"), n(total))
    else:
        headline = "%s brought in %s *leads*." % (end.strftime("%B"), n(total))
    top_chan = max(chans, key=lambda x: x[1])
    subtitle = "%s was the biggest source with %s leads (%s). %s of leads arrived fully tagged." % (
        source_label(top_src), n(top_src_n), pct(share(top_src_n, total)), pct(cov))

    secs = [{"type": "title-block", "kicker": "Monthly performance review · %s" % period,
             "title": headline, "subtitle": subtitle,
             "meta_bits": [b for b in [customer_domain, form_label, "%s submissions" % n(total), "%d days" % days] if b]},
            {"type": "stat-strip", "stats": [
                stat("Leads captured", n(total), total, total_prior if prior else None, spark=daily),
                stat("Leads per day", "%.1f" % per_day, per_day, per_day_prior),
                stat("Paid share", pct(paid_share), paid_share, paid_share_prior, kind="pts", good="neutral"),
                stat("Fully tagged", pct(cov), cov, cov_prior, kind="pts")]}]

    # takeaway
    body = ["%s alone sent %s leads, %s of the month." % (source_label(top_src), n(top_src_n), pct(share(top_src_n, total)))]
    if cov < 80:
        body.append("%s of leads arrived without a full source, medium and campaign tag, so their campaign is unknown." % pct(100 - cov))
    secs.append({"type": "insight-card", "kicker": "The takeaway",
                 "title": "*%s* drove %s of your %s leads." % (top_chan[0] + " traffic", pct(share(top_chan[1], total)), n(total)),
                 "body": body})

    # 01 channel mix
    secs.append({"type": "section-header", "number": "01", "kicker": "Channel mix",
                 "title": "Where your *leads* come from.", "dek": "Each lead's last touch before the form."})
    mix = [(c, v) for c, v in chans if v > 0]
    mover = None
    if prior:
        changes = [(c, share(v, total) - share(chans_prior.get(c, 0), total_prior)) for c, v in chans]
        mover = max(changes, key=lambda x: abs(x[1]))
    ins_body = ["%s is %s of leads, %s." % (top_chan[0], pct(share(top_chan[1], total)),
                                             "the largest channel")]
    if mover and abs(mover[1]) >= 3:
        ins_body.append("%s moved the most: %s%s pts vs %s." % (mover[0], "+" if mover[1] > 0 else "−",
                                                                 n(abs(round(mover[1]))), m["compare_label"]))
    secs.append({"type": "chart-insight",
                 "chart": {"type": "doughnut", "labels": [c for c, _ in mix],
                           "values": [round(share(v, total), 1) for _, v in mix], "unit": "%"},
                 "caption": "Share of form submissions by last-touch channel",
                 "insight_kicker": "The mix",
                 "insight_title": "%s is *%s* of the funnel." % (top_chan[0], pct(share(top_chan[1], total))),
                 "insight_body": ins_body})
    if _has_first_touch(current):
        ft = dict(_channel_counts(current, first_touch))
        lt = dict(chans)
        opener = max(CHANNELS, key=lambda c: ft.get(c, 0) - lt.get(c, 0))
        secs.append({"type": "chart-insight",
                     "chart": {"type": "bar-grouped", "labels": CHANNELS,
                               "groups": [{"label": "First touch", "values": [ft.get(c, 0) for c in CHANNELS]},
                                          {"label": "Last touch", "values": [lt.get(c, 0) for c in CHANNELS]}]},
                     "caption": "Leads credited to each channel by first touch vs last touch",
                     "insight_kicker": "Openers vs closers",
                     "insight_title": "*%s* starts more journeys than it gets credit for." % opener,
                     "insight_body": ["%s was the first touch for %s leads but the last touch for %s." % (
                         opener, n(ft.get(opener, 0)), n(lt.get(opener, 0))),
                         "Judge it on first touch, or it will look weaker than it is."]})

    # 02 sources and campaigns
    secs.append({"type": "section-header", "number": "02", "kicker": "Sources and campaigns",
                 "title": "Which *sources* sent leads."})
    top6 = src.most_common(6)
    secs.append({"type": "chart-insight",
                 "chart": {"type": "bar-horizontal", "labels": [source_label(s) for s, _ in top6],
                           "values": [v for _, v in top6], "x_title": "Leads", "highlight": 0, "total": total},
                 "caption": "Leads per utm_source, top 6",
                 "insight_kicker": "The leader",
                 "insight_title": "*%s* leads with %s." % (source_label(top_src), n(top_src_n)),
                 "insight_body": ["The top three sources (%s) sent %s of all leads." % (
                     ", ".join(source_label(s) for s, _ in top6[:3]), pct(share(sum(v for _, v in top6[:3]), total)))]})
    rows = []
    for i, (c, v) in enumerate(camps.most_common(8)):
        pv = camps_prior.get(c, 0)
        rows.append({"rank": str(i + 1), "campaign": pretty(c), "tag": c,
                     "leads": {"value": v, "label": n(v)}, "share": pct(share(v, total)),
                     "change": _delta_cell(v, pv) if prior else {"label": "–", "direction": "flat"},
                     "trend": _trend_state(v, pv) if prior else {"state": "steady", "label": "Steady"}})
    if rows:
        secs.append({"type": "ranked-list", "title": "Top *campaigns* this month",
                     "columns": [{"key": "rank", "label": "#", "type": "rank"},
                                 {"key": "campaign", "label": "Campaign", "type": "name"},
                                 {"key": "tag", "label": "utm_campaign", "type": "source"},
                                 {"key": "leads", "label": "Leads", "type": "bar"},
                                 {"key": "share", "label": "Share", "type": "pct", "align": "right"},
                                 {"key": "change", "label": "vs %s" % m["compare_label"], "type": "delta", "align": "right"},
                                 {"key": "trend", "label": "Trend", "type": "trend"}],
                     "rows": rows,
                     "caption": "%s of leads carried a campaign tag." % pct(share(sum(camps.values()), total))})

    # 03 rhythm
    secs.append({"type": "section-header", "number": "03", "kicker": "Volume",
                 "title": "The daily *rhythm* of leads."})
    peak_i = max(range(len(daily)), key=lambda i: daily[i]) if daily else 0
    series = [{"label": period_name(start, end, short=True), "values": daily}]
    if prior and daily_prior:
        aligned = daily_prior[-len(daily):] if len(daily_prior) >= len(daily) else daily_prior + [None] * (len(daily) - len(daily_prior))
        series.append({"label": prior_name(pstart, pend).capitalize(), "values": aligned, "style": "dashed"})
    secs.append({"type": "chart",
                 "chart": {"type": "line-multi" if len(series) > 1 else "area", "labels": labels,
                           "series": series} if len(series) > 1 else
                 {"type": "area", "labels": labels, "values": daily},
                 "chart_title": "Leads per *day*",
                 "caption": "Peak of %s on %s. Average %.1f a day." % (n(daily[peak_i]) if daily else 0,
                                                                      labels[peak_i] if labels else "", per_day)})

    # 04 next steps
    recs = []
    if cov < 85:
        recs.append({"label": "This week", "title": "Tag every link with a full *UTM* set",
                     "body": "%s of leads arrived without source, medium and campaign. Fix the top landing pages and ad URLs first." % pct(100 - cov),
                     "impact": "High", "effort": "Low"})
    rising = [(c, v, camps_prior.get(c, 0)) for c, v in camps.most_common(10) if v > camps_prior.get(c, 0) * 1.15 and v >= 5]
    if rising:
        c, v, pv = rising[0]
        recs.append({"label": "This month", "title": "Put more budget behind *%s*" % pretty(c),
                     "body": "It sent %s leads, up from %s: the most of any growing campaign." % (n(v), n(pv)),
                     "impact": "High", "effort": "Medium"})
    falling = [(c, v, camps_prior.get(c, 0)) for c, v in camps_prior.most_common(10)
               if camps.get(c, 0) < v * 0.6 and v >= 5]
    if falling:
        c, pv, _ = falling[0]
        recs.append({"label": "This week", "title": "Check why *%s* slowed down" % pretty(c),
                     "body": "It fell from %s leads to %s. Look for a paused ad, a broken link or a changed landing page." % (n(pv), n(camps.get(c, 0))),
                     "impact": "Medium", "effort": "Low"})
    recs.append({"label": "Ongoing", "title": "Feed the *%s* channel" % top_chan[0].lower(),
                 "body": "%s traffic delivered %s leads. Keep it funded and test one new message there." % (top_chan[0], n(top_chan[1])),
                 "impact": "Medium", "effort": "Medium"})
    if len(recs) < 2:
        recs.append({"label": "Next month", "title": "Run the *anomaly* check weekly",
                     "body": "Catch a sudden drop in any channel within days, not at month end.", "impact": "Low", "effort": "Low"})
    secs.append({"type": "section-header", "number": "04", "kicker": "Next steps", "title": "What to do *next*."})
    secs.append({"type": "recommendations", "items": recs[:4]})
    secs.append({"type": "closing", "kicker": "The month in one line",
                 "title": "Next: feed *%s*. It sent %s of your leads." % (source_label(top_src), pct(share(top_src_n, total))),
                 "summary_stats": [{"value": n(total), "label": "Leads"},
                                   {"value": "%.1f" % per_day, "label": "Per day"},
                                   {"value": pct(cov), "label": "Fully tagged"},
                                   {"value": source_label(top_src), "label": "Top source"}],
                 "bullets": ["%s paid, %s from all other channels." % (pct(paid_share), pct(100 - paid_share)),
                             "Busiest day: %s with %s leads." % (labels[peak_i] if labels else "", n(daily[peak_i]) if daily else 0),
                             "%s sent %s leads." % (source_label(top_src), n(top_src_n))]})
    return {"meta": m, "sections": secs}


REGISTRY = {
    "monthly": build_monthly, "monthly-review": build_monthly, "monthly-performance-review": build_monthly,
}


# ===========================================================================
# Shared private helpers for the weekly, leaderboard, deep dive, side-by-side
# and agency rollup recipes (channels.py imports a few of them too).
# ===========================================================================
_NULLS = {"none", "null", "undefined", "nan", "n/a"}
_ONE_DAY = _dt.timedelta(days=1)
_SOON = re.compile(r"\b(this week|this month|asap|immediately|right away|today|urgent|within 30|next 30|"
                   r"30 days|1 month|one month|2 weeks|two weeks)\b", re.I)


def _clean(s):
    """A data string that is safe in titles and cells: no em dash, no accent marker, single spaces."""
    return " ".join(str(s if s is not None else "").replace("\u2014", "-").replace("*", "").split())


def _val(e, *keys):
    s = _clean(get_field(e, *keys))
    return "" if s.lower() in _NULLS else s


def _src(e):
    return _val(e, "utm_source (HandL)", "utm_source").lower()


def _med(e):
    return _val(e, "utm_medium (HandL)", "utm_medium").lower()


def _camp(e):
    return _val(e, "utm_campaign (HandL)", "utm_campaign").lower()


def _ad(e):
    return _val(e, "utm_content (HandL)", "utm_content")


def _path(url):
    u = re.sub(r"^[a-z][a-z0-9+.\-]*://[^/]+", "", str(url or ""), flags=re.I)
    u = u.split("?")[0].split("#")[0]
    if not u or u == "/":
        return "/"
    return u.rstrip("/") or "/"


def _page(e):
    u = _val(e, "handl_landing_page (HandL)", "landing_page (HandL)", "Source URL", "source_url")
    return _path(u) if u else ""


def _pname(p):
    """A landing-page path for prose: '/' reads as 'the home page'."""
    return "the home page" if p == "/" else p


def _sm(e):
    s, md = _src(e), _med(e)
    if not s and not md:
        return ""
    return "%s / %s" % (s or "(not set)", md or "(not set)")


def _tagged(e):
    return bool(_src(e) and _med(e) and _camp(e))


def _cov(entries):
    return share(sum(1 for e in entries if _tagged(e)), len(entries)) if entries else 0.0


def _day(e):
    d = entry_dt(e)
    return d.date() if d else None


def _between(entries, start, end):
    out = []
    for e in entries or []:
        d = _day(e)
        if d is not None and start <= d <= end:
            out.append(e)
    return out


def _counts(entries, key):
    c = Counter()
    for e in entries:
        k = key(e)
        if k:
            c[k] += 1
    return c


def _pl(k, word, plural=None):
    return "%s %s" % (n(k), word if k == 1 else (plural or word + "s"))


def _md(d):
    return "%s %d" % (d.strftime("%b"), d.day)


def _trim(s, k=24):
    s = _clean(s)
    return s if len(s) <= k else s[:k - 1].rstrip() + "…"


def _growth(cur, prev):
    return None if not prev else 100.0 * (cur - prev) / prev


def _sn(k):
    """+9 / −9 / 0 with a real minus sign."""
    return ("+" if k > 0 else ("\u2212" if k < 0 else "")) + n(abs(k))


def _signed(g):
    """68.2 -> '+68%', -27 -> '−27%'."""
    return "%s%d%%" % ("+" if g >= 0 else "−", int(round(abs(g))))


def _momentum(values, min_total=5):
    """Second half of the period vs the first half, as a trend pill."""
    if not values or sum(values) < min_total:
        return {"state": "steady", "label": "Low volume"}
    h = len(values) // 2
    a, b = sum(values[:h]), sum(values[len(values) - h:])
    if a == 0:
        return {"state": "rising", "label": "Rising"}
    if b == 0:
        return {"state": "cold", "label": "Stalled"}
    if abs(b - a) < (a + b) ** 0.5:          # within normal random swing for this volume
        return {"state": "steady", "label": "Steady"}
    ch = (b - a) / float(a)
    if ch >= 0.15:
        return {"state": "rising", "label": "Rising"}
    if ch <= -0.5:
        return {"state": "cold", "label": "Stalling"}
    if ch <= -0.15:
        return {"state": "cooling", "label": "Cooling"}
    return {"state": "steady", "label": "Steady"}


def _halves(values):
    h = len(values) // 2
    return sum(values[:h]), sum(values[len(values) - h:])


def _stat_count(label, cur, prev, spark=None, note=None, good="up", source=None):
    """Count KPI. A zero or missing prior gets no delta pill (avoids an 'Up New' pill)."""
    if prev:
        return stat(label, n(cur), cur, prev, good=good, spark=spark, note=note, source=source)
    return stat(label, n(cur), good=good, spark=spark, note=note, source=source)


def _prior_label(start, end):
    """prior_name() with a one-day period read as 'the previous day'."""
    if start and end and start == end:
        return "the previous day"
    return prior_name(start, end)


def _usable(prior):
    """A comparison period needs 10+ leads; below that, growth rates are noise (+900% on 1 lead)."""
    prior = list(prior or [])
    return prior if len(prior) >= 10 else []


def _cell(cur, prev, has_prior):
    return _delta_cell(cur, prev) if has_prior else {"label": "–", "direction": "flat"}


def _short(report, m, entries, period, why, next_title, next_body=None, title=None,
           ins_title="Rankings need at least *10 leads*."):
    """Honest short report for thin data: what we have, why we stop, what to do next."""
    total = len(entries)
    top = _counts(entries, _src).most_common(1)
    m["sources"] = [{"name": "UTM Grabber", "detail": _pl(total, "lead")}]
    top_stat = (stat("Leads from %s" % _trim(source_label(top[0][0]), 22), n(top[0][1]), note="Top source")
                if top else stat("Tagged sources", "0", note="No lead carried a utm_source"))
    rows = []
    for i, e in enumerate(sorted(entries, key=lambda x: entry_dt(x) or _dt.datetime.min)[:9]):
        d = _day(e)
        rows.append({"rank": str(i + 1), "date": _md(d) if d else "–", "sm": _sm(e) or "no UTM tags",
                     "campaign": pretty(_camp(e)) if _camp(e) else "–", "page": _page(e) or "–"})
    secs = [{"type": "title-block", "kicker": report + (" · " + period if period else ""),
             "title": title or "Only %s so far: too few to read a *trend*." % _pl(total, "lead"),
             "subtitle": "Here is what arrived, and what this report needs before it can rank anything.",
             "meta_bits": [b for b in [m.get("customer_domain"), "%s submissions" % n(total)] if b]},
            {"type": "stat-strip", "stats": [
                stat("Leads", n(total)), stat("Fully tagged", pct(_cov(entries))), top_stat]},
            {"type": "insight-card", "kicker": "Why this report is short", "title": ins_title, "body": why}]
    if rows:
        secs.append({"type": "ranked-list", "title": "The *leads* we found",
                     "columns": [{"key": "rank", "label": "#", "type": "rank"},
                                 {"key": "date", "label": "Date", "type": "text"},
                                 {"key": "sm", "label": "Source / medium", "type": "source"},
                                 {"key": "campaign", "label": "Campaign", "type": "name"},
                                 {"key": "page", "label": "Landing page", "type": "source"}],
                     "rows": rows,
                     "caption": ("Shown without names or emails." if total <= 9 else
                                 "The first 9 of %s, shown without names or emails." % n(total))})
    secs.append({"type": "closing", "kicker": "Next step", "title": next_title,
                 "body": next_body or "Nothing is broken: the report fills itself in as submissions arrive."})
    return {"meta": m, "sections": secs}


def _thin(report, m, entries, period, subject="this period"):
    """The standard short version for fewer than 10 leads."""
    total = len(entries)
    return _short(report, m, entries, period,
                  why=["%s brought %s. With so few, one extra lead moves any share by %s points, so a "
                       "ranking would be noise." % (subject[:1].upper() + subject[1:], _pl(total, "lead"),
                                                     n(round(100.0 / max(total, 1)))),
                       "Widen the date range, or run this again once more submissions arrive."],
                  next_title="Next: widen the *date range* and run this again. %s is too few to rank." %
                             _pl(total, "lead").capitalize())


def _undated(report, m, entries):
    return _short(report, m, entries, "",
                  why=["Not one of the %s entries carried a readable submission date, so we can't split them "
                       "into periods." % n(len(entries)),
                       "Pull the entries again with the Date Created field included."],
                  ins_title="We need a *date* on every lead.",
                  title="We couldn't read the *dates* on these %s." % _pl(len(entries), "lead"),
                  next_title="Next: re-pull the leads with their *dates* and run this again.")


# --- form quality signals (budget and timeframe questions, when a form asks them) ---
def _find_field(entries, words, min_share=0.2):
    """The form field whose label contains one of `words` and that most leads answered."""
    c = Counter()
    sample = entries[:600]
    for e in sample:
        for k, v in e.items():
            kl = str(k).lower()
            if "utm" in kl or "handl" in kl or "date" in kl:
                continue
            if any(w in kl for w in words) and str(v if v is not None else "").strip():
                c[k] += 1
    if not c:
        return None
    k, hits = c.most_common(1)[0]
    return k if hits >= max(3, min_share * len(sample)) else None


def _budget_floor(v):
    """'$5,000-$25,000/mo' -> 5000; '<$1,000' -> 0; '$100k+' -> 100000; unreadable -> None."""
    s = str(v or "").lower().replace(",", "").strip()
    m = re.search(r"(\d+(?:\.\d+)?)(?:\s*([km])\b)?", s)
    if not m:
        return None
    if s.startswith(("<", "under", "less", "up to", "below")):
        return 0.0
    return float(m.group(1)) * {"k": 1e3, "m": 1e6}.get(m.group(2) or "", 1.0)


def _quality_rules(pool):
    """Find budget and timeframe questions and turn them into share-of-leads rules.

    Returns a list of (label, test, field) where test(entry) is True/False for answered
    entries and None when the lead skipped the question. Thresholds come from the data:
    'high budget' is the median declared bracket or above."""
    rules = []
    bkey = _find_field(pool, ("budget", "ad spend", "monthly spend"))
    if bkey:
        floors = [f for f in (_budget_floor(e.get(bkey)) for e in pool) if f is not None]
        if len(floors) >= 5:
            cut = median(floors)
            if cut <= min(floors):
                higher = sorted(set(f for f in floors if f > cut))
                cut = higher[0] if higher else cut
            if cut > 0:
                label = "Budget %s+ a month" % money(cut, 0)
                rules.append((label, lambda e, k=bkey, c=cut: (None if _budget_floor(e.get(k)) is None
                                                               else _budget_floor(e.get(k)) >= c), bkey))
    tkey = _find_field(pool, ("timeframe", "time frame", "timeline", "how soon", "urgency"))
    if tkey:
        rules.append(("Ready within 30 days",
                      lambda e, k=tkey: (None if not str(e.get(k) or "").strip()
                                         else bool(_SOON.search(str(e.get(k))))), tkey))
    return rules


def _rule_share(entries, test):
    vals = [test(e) for e in entries]
    vals = [v for v in vals if v is not None]
    return (share(sum(1 for v in vals if v), len(vals)), len(vals)) if vals else (None, 0)


# ---------------------------------------------------------------------------
# WEEKLY EXECUTIVE SUMMARY
# ---------------------------------------------------------------------------
def _week_windows(current, prior):
    """(this week, last week, start, end, has_prior). A longer `current` is cut to its last 7 days."""
    cstart, cend = span(current)
    if cend is None:
        return current, [], None, None, False
    start = cend - 6 * _ONE_DAY
    if (cend - cstart).days < 7:
        last = list(prior or [])
        ps, pe = span(last)
        if ps and (pe - ps).days >= 7:            # a longer prior: keep only the 7 days before this week
            last = _between(last, start - 7 * _ONE_DAY, start - _ONE_DAY)
        return current, last, start, cend, prior is not None
    pstart, pend = cend - 13 * _ONE_DAY, cend - 7 * _ONE_DAY
    week = _between(current, start, cend)
    last = _between(current, pstart, pend)
    covered = cstart <= pstart
    if not covered and prior:
        last += _between(prior, pstart, pend)
    return week, last, start, cend, covered or prior is not None


_AI = ("chatgpt", "perplexity", "claude", "gemini", "copilot", "openai", "bard")


def _check_advice(src, entries):
    """What to check when a source drops, by the kind of traffic it sends."""
    if any(a in src for a in _AI):
        return "AI assistant answers shift often. Check whether it still recommends you for your main questions."
    ch = Counter(last_touch(e) for e in entries if _src(e) == src).most_common(1)
    ch = ch[0][0] if ch else ""
    return {"Paid": "Look for a paused ad, a spent budget or a broken link.",
            "Organic": "Check its rankings and that its landing pages still load.",
            "Social": "Check whether posting slowed, or a link in a post or bio broke.",
            "Referral": "Check that the page or email that links to you still does."}.get(
        ch, "Check that the link behind it still works.")


def _camp_advice(camp, entries):
    """What to check when a campaign slows, by the channel its leads come through."""
    ch = Counter(last_touch(e) for e in entries if _camp(e) == camp).most_common(1)
    ch = ch[0][0] if ch else ""
    return {"Paid": "Check for a paused ad set, an ended offer or a changed landing page.",
            "Referral": "Check the send schedule and that the email or partner links still work.",
            "Social": "Check whether posting slowed or the link in the post broke.",
            "Organic": "Check the rankings of the pages it points to."}.get(
        ch, "Check that its links still work and the landing page still loads.")


def _is_paid_source(src, entries):
    ch = Counter(last_touch(e) for e in entries if _src(e) == src).most_common(1)
    return bool(ch) and ch[0][0] == "Paid"


def build_weekly(current, prior=None, brand_profile=None, customer_name=None, customer_domain="",
                 form_label=None, compare_label=None, prepared_by=None, prepared_for=None, **_):
    """The last 7 days vs the 7 before: one tight page for leadership."""
    current = list(current or [])
    m = meta(brand_profile, customer_name, customer_domain, compare_label=compare_label or "last week",
             sources=None, prepared_by=prepared_by, prepared_for=prepared_for)
    name = "Weekly executive summary"
    if not current:
        return empty_report(name, m)
    week, last, start, end, has_prior = _week_windows(current, prior)
    if start is None:
        return _undated(name, m, current)
    period = period_label(start, end)
    cmp_ = m["compare_label"]
    total, total_prior = len(week), len(last)
    if total < 10:
        return _thin(name, m, week, period, "this week")
    m["sources"] = [{"name": "UTM Grabber", "detail": _pl(total, "lead")}]

    is_paid = lambda e: last_touch(e) == "Paid"  # noqa: E731
    paid, paid_prior = sum(1 for e in week if is_paid(e)), sum(1 for e in last if is_paid(e))
    cov, cov_prior = _cov(week), (_cov(last) if last else None)
    _, d14 = daily_counts(week + last, start - 7 * _ONE_DAY, end)
    _, p14 = daily_counts(week + last, start - 7 * _ONE_DAY, end, predicate=is_paid)
    daily = d14[7:]
    peak_i = max(range(len(daily)), key=lambda i: daily[i])
    peak_day = start + peak_i * _ONE_DAY

    src_w = Counter(_src(e) for e in week)          # "" collects untagged leads
    src_l = Counter(_src(e) for e in last)
    tagged_src = [(k, v) for k, v in src_w.most_common() if k]
    untagged, untagged_prior = src_w.get("", 0), src_l.get("", 0)
    top_k, top_v = tagged_src[0] if tagged_src else ("", 0)

    # what changed, tagged source by tagged source. Callouts show moves of 3+ leads;
    # recommendations and the headline only act on moves of 5+ leads and 10%+.
    moves = [(k, src_w.get(k, 0), src_l.get(k, 0)) for k in set(src_w) | set(src_l) if k]
    risers, drops, news, gone = [], [], [], []
    if has_prior:
        def big(c, p, k=3):
            return abs(c - p) >= k and abs(c - p) >= 0.1 * max(p, 1)
        risers = sorted([x for x in moves if x[2] > 0 and x[1] > x[2] and big(x[1], x[2])],
                        key=lambda x: (-(x[1] - x[2]), x[0]))
        drops = sorted([x for x in moves if x[1] > 0 and x[1] < x[2] and big(x[1], x[2])],
                       key=lambda x: (-(x[2] - x[1]), x[0]))
        news = sorted([x for x in moves if x[2] == 0 and x[1] >= 2], key=lambda x: (-x[1], x[0]))
        gone = sorted([x for x in moves if x[1] == 0 and x[2] >= 3], key=lambda x: (-x[2], x[0]))
    riser = risers[0] if risers else None
    drop = drops[0] if drops else None
    act_rise = riser if riser and riser[1] - riser[2] >= 5 else None
    act_drop = drop if drop and drop[2] - drop[1] >= 5 else None
    leak = has_prior and untagged - untagged_prior >= 3 and untagged - untagged_prior >= 0.1 * max(untagged_prior, 1)
    leak_rec = leak and untagged - untagged_prior >= 5

    # headline: outcome first; name a driver only when it explains most of the move
    d = delta(total, total_prior) if has_prior else {}
    direction = d.get("delta_direction")
    net = total - total_prior
    if direction == "up" and total_prior:
        if act_rise and act_rise[1] - act_rise[2] >= 0.4 * net:
            headline = "Leads rose %s to %s this week, led by *%s*." % (
                d["delta_label"].lstrip("+"), n(total), source_label(act_rise[0]))
        else:
            headline = "This week brought *%s*, %s more than %s." % (_pl(total, "lead"), d["delta_label"].lstrip("+"), cmp_)
    elif direction == "down":
        dl = d["delta_label"].lstrip("−")
        if act_drop and act_drop[2] - act_drop[1] >= 0.4 * -net:
            headline = "Leads fell %s to %s this week, mostly from *%s*." % (dl, n(total), source_label(act_drop[0]))
        else:
            headline = "This week brought *%s*, %s fewer than %s." % (_pl(total, "lead"), dl, cmp_)
    elif has_prior and total_prior:
        headline = "Lead flow held steady at *%s* this week." % _pl(total, "lead")
    else:
        headline = "This week brought *%s*." % _pl(total, "lead")
    sub = []
    if top_k:
        sub.append("%s sent the most leads (%s, %s of the week)." % (source_label(top_k), n(top_v), pct(share(top_v, total))))
    else:
        sub.append("Not one lead this week carried a UTM source.")
    big_moves = sorted([x for x in (riser, drop) if x], key=lambda x: -abs(x[1] - x[2]))
    if big_moves:
        x = big_moves[0]
        sub.append("The biggest move: %s, %s from %s to %s." % (source_label(x[0]), "up" if x[1] > x[2] else "down",
                                                               n(x[2]), n(x[1])))
    else:
        sub.append("Paid clicks brought %s of leads; %s arrived fully tagged." % (pct(share(paid, total)), pct(cov)))

    secs = [{"type": "title-block", "kicker": "Weekly executive summary · %s" % period,
             "title": headline, "subtitle": " ".join(sub),
             "meta_bits": [b for b in [customer_domain, form_label, "%s submissions" % n(total), "7 days"] if b]},
            {"type": "stat-strip", "stats": [
                _stat_count("Leads", total, total_prior if has_prior else None, spark=d14,
                            note="%s %s" % (n(total_prior), cmp_) if has_prior else "Daily, last 14 days"),
                _stat_count("Paid leads", paid, paid_prior if has_prior else None, spark=p14,
                            note="%s of the week" % pct(share(paid, total))),
                stat("Fully tagged", pct(cov), cov, cov_prior if has_prior else None, kind="pts",
                     note="%s of %s leads" % (n(sum(1 for e in week if _tagged(e))), n(total))),
                (stat("Leads from %s" % _trim(source_label(top_k), 22), n(top_v), top_v,
                      src_l.get(top_k) if has_prior and src_l.get(top_k) else None,
                      note="Top source, %s of the week" % pct(share(top_v, total))) if top_k else
                 stat("Tagged sources", "0", good="neutral", note="No lead carried a utm_source"))]}]

    # 01 what changed
    items = []
    if riser:
        items.append({"kicker": "Biggest riser", "value": "+%s" % n(riser[1] - riser[2]), "tone": "good",
                      "title": "more leads from %s (%s vs %s)" % (source_label(riser[0]), n(riser[1]), n(riser[2]))})
    if drop:
        items.append({"kicker": "Biggest drop", "value": "−%s" % n(drop[2] - drop[1]), "tone": "bad",
                      "title": "fewer leads from %s (%s vs %s)" % (source_label(drop[0]), n(drop[1]), n(drop[2]))})
    if news:
        k, c, _p = news[0]
        items.append({"kicker": "New source", "value": n(c), "tone": "neutral",
                      "title": "leads from %s, which sent none %s" % (source_label(k), cmp_)})
    elif gone:
        k, _c, p = gone[0]
        items.append({"kicker": "Went quiet", "value": "0", "tone": "warn",
                      "title": "leads from %s, down from %s %s" % (source_label(k), n(p), cmp_)})
    if leak:
        items.append({"kicker": "Untagged leads", "value": "+%s" % n(untagged - untagged_prior), "tone": "warn",
                      "title": "more leads with no UTM source (%s vs %s)" % (n(untagged), n(untagged_prior))})
    items.append({"kicker": "Busiest day", "value": n(daily[peak_i]), "tone": "neutral",
                  "title": "leads on %s, %s" % (peak_day.strftime("%A"), _md(peak_day))})
    if len(items) < 3:
        items.insert(0, {"kicker": "Paid share", "value": pct(share(paid, total)), "tone": "neutral",
                         "title": "of leads came from a paid click (%s %s)" % (
                             pct(share(paid_prior, total_prior)), cmp_) if has_prior and total_prior else
                         "of leads came from a paid click"})
    changed = bool(riser or drop or news or gone or leak)
    secs.append({"type": "section-header", "number": "01", "kicker": "What changed",
                 "title": ("What *changed* since %s." % cmp_) if has_prior else "The week at a *glance*.",
                 "dek": ("Source by source against %s. Moves under 3 leads are left out." % cmp_) if changed else
                 ("No source moved by 3 leads or more against %s." % cmp_ if has_prior
                  else "There is no earlier week in the data to compare against.")})
    secs.append({"type": "callouts", "items": items[:4]})

    # 02 sources and campaigns
    secs.append({"type": "section-header", "number": "02", "kicker": "Sources",
                 "title": "Where this week's *leads* came from."})
    if tagged_src:
        top6 = tagged_src[:5]               # five rows keep the weekly at two printed pages
        top3 = sum(v for _, v in top6[:3])
        body = ["The top %s sent %s of the week's leads." % (
            "three sources" if len(top6) >= 3 else "sources", pct(share(top3, total)))]
        if untagged:
            body.append("%s (%s) arrived with no UTM source, so they can't be credited to a source." % (
                _pl(untagged, "lead").capitalize(), pct(share(untagged, total))))
        chart = {"type": "bar-horizontal", "labels": [source_label(k) for k, _ in top6],
                 "values": [v for _, v in top6], "x_title": "Leads", "highlight": 0, "total": total}
        if has_prior:
            chart["notes"] = [("%s %s" % (n(src_l.get(k, 0)), cmp_)) if src_l.get(k, 0) else "new this week"
                              for k, _ in top6]
        secs.append({"type": "chart-insight", "chart": chart,
                     "caption": "Leads per utm_source this week, top %d" % len(top6),
                     "insight_kicker": "The leader",
                     "insight_title": "*%s* sent %s of %s leads." % (source_label(top_k), n(top_v), n(total)),
                     "insight_body": body})
    else:
        secs.append({"type": "insight-card", "kicker": "Tracking gap", "tone": "warn",
                     "title": "Not one *lead* this week carried a UTM source.",
                     "body": ["All %s leads arrived without utm_source, so the week can't be split by source." % n(total),
                              "Add UTM tags to every ad, email and social link, then this section fills in."]})
    camps_w = _counts(week, _camp)

    # 03 this week's moves
    recs = []
    if act_drop:
        k, c, p = act_drop
        recs.append({"label": "This week", "title": "Check what changed on *%s*" % source_label(k),
                     "body": "It sent %s, down from %s %s. %s" % (_pl(c, "lead"), n(p), cmp_,
                                                                   _check_advice(k, week + last)),
                     "impact": "High" if p - c >= 0.1 * total else "Medium", "effort": "Low"})
    if gone and len(recs) < 2:
        k, _c, p = gone[0]
        recs.append({"label": "This week", "title": "Find out why *%s* went quiet" % source_label(k),
                     "body": "It sent %s %s and none this week. %s" % (_pl(p, "lead"), cmp_, _check_advice(k, week + last)),
                     "impact": "Medium", "effort": "Low"})
    if leak_rec:
        recs.append({"label": "This week", "title": "Tag the new *links* sending leads",
                     "body": "Leads with no UTM source rose from %s to %s. An ad, email or post probably went out "
                             "without tags." % (n(untagged_prior), n(untagged)),
                     "impact": "Medium", "effort": "Low"})
    if act_rise:
        k, c, p = act_rise
        paid_src = _is_paid_source(k, week + last)
        recs.append({"label": "This week", "title": ("Keep *%s* funded" if paid_src else "Do more of what works on *%s*")
                     % source_label(k),
                     "body": "It sent %s, up from %s %s. %s" % (
                         _pl(c, "lead"), n(p), cmp_, "Check that daily budgets are not capping it." if paid_src else
                         "Find the post, page or mention behind the rise and repeat it."),
                     "impact": "Medium", "effort": "Low"})
    if news and len(recs) < 3:
        k, c, _p = news[0]
        recs.append({"label": "This week", "title": "Find what sent the *%s* leads" % source_label(k),
                     "body": "%s arrived from %s, which sent none %s. If it's a mention or a partner, follow up "
                             "while it's fresh." % (_pl(c, "lead").capitalize(), source_label(k), cmp_),
                     "impact": "Low", "effort": "Low"})
    if share(untagged, total) >= 25 and not leak_rec and len(recs) < 3:
        recs.append({"label": "This week", "title": "Tag the links behind *untagged* leads",
                     "body": "%s of %s leads (%s) had no UTM source. Start with the ads and emails that ran this "
                             "week." % (n(untagged), n(total), pct(share(untagged, total))),
                     "impact": "Medium", "effort": "Low"})
    if len(recs) < 2 and top_k:
        recs.append({"label": "This week", "title": "Keep feeding *%s*" % source_label(top_k),
                     "body": "It sent %s of the week's leads (%s). Keep it funded and test one new message "
                             "there." % (pct(share(top_v, total)), _pl(top_v, "lead")),
                     "impact": "Medium", "effort": "Medium"})
    if len(recs) < 2:
        recs.append({"label": "This week", "title": "Tag every ad and email *link*",
                     "body": "Only %s of leads arrived fully tagged. Full tags turn next week's report into a "
                             "source-by-source story." % pct(cov), "impact": "Medium", "effort": "Low"})
    recs = recs[:3]
    secs.append({"type": "section-header", "number": "03", "kicker": "This week",
                 "title": "%s *moves* for this week." % ("Three" if len(recs) == 3 else "Two")})
    secs.append({"type": "recommendations", "items": recs})

    # closing
    if act_drop:
        ctitle = "Next: check *%s* this week. It fell from %s to %s." % (
            source_label(act_drop[0]), _pl(act_drop[2], "lead"), n(act_drop[1]))
    elif act_rise:
        ctitle = "Next: %s *%s*. It grew from %s to %s." % (
            "keep funding" if _is_paid_source(act_rise[0], week + last) else "build on", source_label(act_rise[0]),
            _pl(act_rise[2], "lead"), n(act_rise[1]))
    elif top_k:
        ctitle = "Next: keep feeding *%s*. It sent %s of the week's leads." % (
            source_label(top_k), pct(share(top_v, total)))
    else:
        ctitle = "Next: add UTM tags to every *link*. No lead carried a source this week."
    bullets = []
    bullets.append("Busiest day: %s, %s, with %s." % (peak_day.strftime("%A"), _md(peak_day), _pl(daily[peak_i], "lead")))
    if camps_w:
        c, v = camps_w.most_common(1)[0]
        bullets.append("Top campaign: %s with %s." % (pretty(c), _pl(v, "lead")))
    # no summary_stats here: on a one-pager they would repeat the KPI strip and push the close onto page 3
    secs.append({"type": "closing", "kicker": "The week in one line", "title": ctitle,
                 "bullets": bullets})
    return {"meta": m, "sections": secs}


# ---------------------------------------------------------------------------
# CAMPAIGN LEADERBOARD
# ---------------------------------------------------------------------------
def build_leaderboard(current, prior=None, brand_profile=None, customer_name=None, customer_domain="",
                      form_label=None, compare_label=None, prepared_by=None, prepared_for=None, **_):
    """Every campaign ranked by leads, with growth vs the prior period, momentum and a scale/fix map."""
    current, prior = list(current or []), _usable(prior)
    start, end = span(current)
    pstart, pend = span(prior) if prior else (None, None)
    m = meta(brand_profile, customer_name, customer_domain,
             compare_label=compare_label or (_prior_label(pstart, pend) if prior else "last period"),
             sources=None, prepared_by=prepared_by, prepared_for=prepared_for)
    name = "Campaign leaderboard"
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
    camps, camps_p = _counts(current, _camp), _counts(prior, _camp)
    if not camps:
        return _short(name, m, current, period,
                      why=["Not one of the %s leads carried a utm_campaign tag, so there is nothing to rank." % n(total),
                           "Add utm_campaign to every ad, email and social link. The leaderboard fills in from "
                           "the next tagged lead."],
                      ins_title="Campaigns need a *utm_campaign* tag.",
                      title="No lead carried a *campaign* tag this period.",
                      next_title="Next: add *utm_campaign* to every link, then run this again.")
    m["sources"] = [{"name": "UTM Grabber", "detail": _pl(total, "lead")}]
    ranked = camps.most_common()
    tagged_total, tagged_p = sum(camps.values()), sum(camps_p.values())
    by = {}
    for e in current:
        c = _camp(e)
        if c:
            by.setdefault(c, []).append(e)
    info = {}
    for c, v in ranked:
        _, dl = daily_counts(by[c], start, end)
        sm = Counter(_sm(e) for e in by[c] if _sm(e)).most_common(1)
        pv = camps_p.get(c, 0)
        info[c] = {"v": v, "pv": pv, "g": _growth(v, pv), "daily": dl, "mom": _momentum(dl),
                   "sm": sm[0][0] if sm else "(not set)"}
    top_c, top_v = ranked[0]
    top3 = sum(v for _, v in ranked[:3])
    top3_p = sum(v for _, v in camps_p.most_common(3))
    n_new = sum(1 for c in camps if not camps_p.get(c)) if has_prior else 0
    _, tag_daily = daily_counts(current, start, end, predicate=lambda e: bool(_camp(e)))
    untag = total - tagged_total

    # growth groups (vs prior) and momentum groups (within the period)
    big = median([v for _, v in ranked[:12]])       # "big" = at or above the median listed campaign
    growers = [c for c, _ in ranked if has_prior and info[c]["pv"] and info[c]["g"] >= 15 and info[c]["v"] >= 5]
    fallers = [c for c, _ in camps_p.most_common() if has_prior and camps_p[c] >= 5 and camps.get(c, 0) <= 0.85 * camps_p[c]]
    rising = [c for c, _ in ranked if info[c]["mom"]["state"] == "rising" and info[c]["mom"]["label"] != "Low volume"]
    cooling = [c for c, _ in ranked if info[c]["mom"]["state"] in ("cooling", "cold")]
    scale_c = max(growers, key=lambda c: (info[c]["v"] - info[c]["pv"], c)) if growers else None
    big_fall = [c for c in fallers if camps.get(c, 0) >= big]
    fix_c = max(big_fall, key=lambda c: (camps_p[c] - camps.get(c, 0), c)) if big_fall else None
    small_fall = [c for c in fallers if c not in big_fall]
    watch_c = max(small_fall, key=lambda c: (camps_p[c] - camps.get(c, 0), c)) if small_fall else None
    new_bets = [c for c, _ in ranked if has_prior and not info[c]["pv"] and info[c]["v"] >= 3]

    # headline
    tied = [c for c, v in ranked if v == top_v]
    if len(tied) > 1:
        headline = "*%s* and %s tied at %s." % (
            pretty(tied[0]), pretty(tied[1]) if len(tied) == 2 else "%s others" % n(len(tied) - 1), _pl(top_v, "lead"))
    else:
        headline = "*%s* led %s with %s." % (pretty(top_c), _pl(len(camps), "campaign"), _pl(top_v, "lead"))
    sub = ["The top three campaigns sent %s of all leads." % pct(share(top3, total))]
    if has_prior:
        sub.append("Against %s, %s grew 15%% or more and %s fell as much." % (
            cmp_, _pl(len(growers), "campaign"), n(len(fallers))))

    secs = [{"type": "title-block", "kicker": "Campaign leaderboard · %s" % period, "title": headline,
             "subtitle": " ".join(sub),
             "meta_bits": [b for b in [customer_domain, form_label, _pl(len(camps), "campaign"), _pl(days, "day")] if b]},
            {"type": "stat-strip", "stats": [
                _stat_count("Campaign leads", tagged_total, tagged_p if has_prior else None, spark=tag_daily,
                            note="%s of all leads" % pct(share(tagged_total, total))),
                stat("Campaigns with leads", n(len(camps)), len(camps), len(camps_p) if has_prior and camps_p else None,
                     kind="abs", good="neutral", note=("%s new this period" % n(n_new)) if has_prior else None),
                stat("Top 3 share", pct(share(top3, total)), share(top3, total),
                     share(top3_p, len(prior)) if has_prior else None, kind="pts", good="neutral", note="of all leads"),
                stat("%s leads" % _trim(pretty(top_c), 24), n(top_v), top_v,
                     info[top_c]["pv"] if has_prior and info[top_c]["pv"] else None,
                     note="Top campaign, %s of all leads" % pct(share(top_v, total)))]}]

    # 01 the standings
    secs.append({"type": "section-header", "number": "01", "kicker": "The standings",
                 "title": "Every *campaign*, ranked by leads.",
                 "dek": ("Last-touch utm_campaign. Change is against %s; momentum compares the second half of "
                         "the period with the first." % cmp_) if has_prior else
                 "Last-touch utm_campaign. Momentum compares the second half of the period with the first."})
    rows = []
    for i, (c, v) in enumerate(ranked[:12]):
        x = info[c]
        row = {"rank": str(i + 1), "campaign": pretty(c), "sm": x["sm"], "leads": {"value": v, "label": n(v)},
               "share": pct(share(v, total)), "momentum": x["mom"], "daily": x["daily"]}
        if has_prior:
            row["change"] = _delta_cell(v, x["pv"])
        if c == scale_c:
            row["_highlight"] = True
        rows.append(row)
    cols = [{"key": "rank", "label": "#", "type": "rank"},
            {"key": "campaign", "label": "Campaign", "type": "name"},
            {"key": "sm", "label": "Source / medium", "type": "source"},
            {"key": "leads", "label": "Leads", "type": "bar"},
            {"key": "share", "label": "Share", "type": "pct", "align": "right"}]
    if has_prior:
        cols.append({"key": "change", "label": "Change", "type": "delta", "align": "right"})
    cols += [{"key": "momentum", "label": "Momentum", "type": "trend"},
             {"key": "daily", "label": "Daily", "type": "spark"}]
    cap = []
    if len(ranked) > 12:
        rest = ranked[12:]
        cap.append("%s more with %s are not shown." % (_pl(len(rest), "campaign"), _pl(sum(v for _, v in rest), "lead")))
    cap.append("Share is of all %s leads; %s carried no campaign tag." % (n(total), pct(share(untag, total))))
    if scale_c:
        cap.append("Highlighted: the campaign to scale.")
    secs.append({"type": "ranked-list", "title": "Campaigns by *leads*", "columns": cols, "rows": rows,
                 "caption": " ".join(cap)})

    # 02 growth map
    if has_prior:
        pts_src = [(c, info[c]["v"], info[c]["pv"]) for c, _ in ranked[:12]]
        for c, pv in camps_p.most_common():
            if c not in camps and pv >= 5 and len(pts_src) < 14:
                pts_src.append((c, 0, pv))
        pts_src = [p for p in pts_src if max(p[1], p[2]) >= 3]
        if len(pts_src) >= 3:
            points = []
            for c, v, pv in pts_src:
                new = pv == 0
                y = 200.0 if new else max(-100.0, min(200.0, _growth(v, pv)))
                points.append({"label": pretty(c), "x": v, "y": round(y, 1), "size": max(v, 1),
                               "group": "New this period" if new else "Ran in both periods"})
            x_ref = median([p["x"] for p in points])
            capped = any(p["y"] >= 200 for p in points)
            ins_body = []
            if scale_c:
                x = info[scale_c]
                ins_title = "*%s* is the one to scale." % pretty(scale_c)
                ins_body.append("It sent %s, up %s from %s, with more volume than most campaigns." % (
                    _pl(x["v"], "lead"), _signed(x["g"])[1:], n(x["pv"])))
            elif fix_c:
                ins_title = "*%s* is big but losing ground." % pretty(fix_c)
                ins_body.append("It sent %s, down from %s (%s)." % (
                    _pl(camps.get(fix_c, 0), "lead"), n(camps_p[fix_c]), _signed(_growth(camps.get(fix_c, 0), camps_p[fix_c]))))
            else:
                ins_title = "No campaign broke away from the *pack*."
                ins_body.append("Every campaign with real volume stayed within 15%% of %s." % cmp_)
            if fix_c and scale_c:
                ins_body.append("%s is big but falling: %s, down from %s." % (
                    pretty(fix_c), _pl(camps.get(fix_c, 0), "lead"), n(camps_p[fix_c])))
            elif watch_c:
                ins_body.append("%s fell from %s to %s: watch it before it slides further." % (
                    pretty(watch_c), _pl(camps_p[watch_c], "lead"), n(camps.get(watch_c, 0))))
            if new_bets:
                ins_body.append("%s new campaign%s sit at the top of the map; give them time before judging." % (
                    n(len(new_bets)), "" if len(new_bets) == 1 else "s") if len(new_bets) > 1 else
                    "%s is new this period and sits at the top of the map." % pretty(new_bets[0]))
            secs.append({"type": "section-header", "number": "02", "kicker": "Growth map",
                         "title": "Where to *scale* and where to fix.",
                         "dek": "Each dot is a campaign. Across: leads this period. Up: change against %s." % cmp_})
            secs.append({"type": "matrix", "chart_title": "Volume vs *growth*", "points": points,
                         "x_label": "Leads this period", "y_label": "Change vs %s" % cmp_, "y_unit": "%",
                         "x_ref": x_ref, "y_ref": 0,
                         "quadrants": {"tr": "Scale", "br": "Fix", "tl": "New bets", "bl": "Watch"},
                         "insight_kicker": "Read the map", "insight_title": ins_title, "insight_body": ins_body,
                         "caption": ("The vertical line is the median campaign (%s leads). " % n(x_ref)) +
                                    ("Growth is capped at +200%; new campaigns sit on that line." if capped else
                                     "Bubble size is leads this period.")})

    # next steps
    recs = []
    if scale_c:
        x = info[scale_c]
        recs.append({"label": "This month", "title": "Scale *%s*" % pretty(scale_c),
                     "body": "It sent %s, up from %s (%s). Raise its budget in steps and check that lead quality "
                             "holds." % (_pl(x["v"], "lead"), n(x["pv"]), _signed(x["g"])),
                     "impact": "High", "effort": "Medium", "metric": "%s leads vs %s" % (_sn(x["v"] - x["pv"]), cmp_)})
    for c, imp in ((fix_c, "High"), (watch_c, "Medium")):
        if c and len(recs) < 3:
            recs.append({"label": "This week", "title": ("Fix *%s* before it slips further" if imp == "High"
                                                         else "Find out why *%s* slowed") % pretty(c),
                         "body": "It fell from %s to %s. %s" % (_pl(camps_p[c], "lead"), n(camps.get(c, 0)),
                                                                 _camp_advice(c, current + prior)),
                         "impact": imp, "effort": "Low",
                         "metric": "%s leads vs %s" % (_sn(camps.get(c, 0) - camps_p[c]), cmp_)})
    if new_bets:
        c = new_bets[0]
        recs.append({"label": "Next %s" % _pl(days, "day"), "title": "Give *%s* a fair test" % pretty(c),
                     "body": "It is new this period with %s. Judge it after another %s, not on its first "
                             "run." % (_pl(info[c]["v"], "lead"), _pl(days, "day")), "impact": "Medium", "effort": "Low"})
    cool_big = [c for c in cooling if info[c]["v"] >= max(8, big) and c not in (fix_c, watch_c)]
    if cool_big and len(recs) < 4:
        c = cool_big[0]
        a, b = _halves(info[c]["daily"])
        recs.append({"label": "This week", "title": "Refresh the creative in *%s*" % pretty(c),
                     "body": "Its second half brought %s against %s in the first half. Swap in new ad copy "
                             "before it stalls." % (_pl(b, "lead"), n(a)), "impact": "Medium", "effort": "Medium"})
    if share(untag, total) >= 25 and len(recs) < 4:
        recs.append({"label": "This week", "title": "Add a *campaign* tag to every link",
                     "body": "%s of leads (%s) had no utm_campaign, so they can't be ranked here." % (
                         pct(share(untag, total)), n(untag)), "impact": "Medium", "effort": "Low"})
    if len(recs) < 2:
        recs.append({"label": "Ongoing", "title": "Protect *%s*" % pretty(top_c),
                     "body": "It is your top campaign with %s of all leads. Keep its budget steady and test one "
                             "new ad at a time." % pct(share(top_v, total)), "impact": "Medium", "effort": "Low"})
    if len(recs) < 2:
        recs.append({"label": "Next period", "title": "Run the leaderboard against a *prior* period",
                     "body": "With a comparison period, each campaign gets a growth rate and a place on the "
                             "scale/fix map.", "impact": "Low", "effort": "Low"})
    secs.append({"type": "section-header", "number": "03" if len(secs) and secs[-1]["type"] == "matrix" else "02",
                 "kicker": "Next steps", "title": "What to do with the *standings*."})
    secs.append({"type": "recommendations", "items": recs[:4]})

    if scale_c:
        ctitle = "Next: scale *%s*. It grew %s to %s." % (pretty(scale_c), _signed(info[scale_c]["g"])[1:],
                                                         _pl(info[scale_c]["v"], "lead"))
    elif fix_c or watch_c:
        c = fix_c or watch_c
        ctitle = ("Next: fix *%s*. It fell from %s to %s." if fix_c else
                  "Next: find out why *%s* slowed. It fell from %s to %s.") % (
            pretty(c), _pl(camps_p[c], "lead"), n(camps.get(c, 0)))
    else:
        ctitle = "Next: protect *%s*. It sent %s of all leads." % (pretty(top_c), pct(share(top_v, total)))
    bullets = ["%s led with %s (%s of all leads)." % (pretty(top_c), _pl(top_v, "lead"), pct(share(top_v, total)))]
    if has_prior:
        bullets.append("%s grew 15%% or more; %s fell 15%% or more against %s." % (
            _pl(len(growers), "campaign"), n(len(fallers)), cmp_))
    else:
        bullets.append("%s gained momentum through the period; %s cooled." % (_pl(len(rising), "campaign"), n(len(cooling))))
    bullets.append("%s of leads carried a campaign tag." % pct(share(tagged_total, total)))
    secs.append({"type": "closing", "kicker": "The standings in one line", "title": ctitle,
                 "summary_stats": [{"value": n(len(camps)), "label": "Campaigns"},
                                   {"value": _trim(pretty(top_c), 18), "label": "Top campaign"},
                                   {"value": pct(share(top3, total)), "label": "Top 3 share"},
                                   {"value": pct(share(tagged_total, total)), "label": "Campaign-tagged"}],
                 "bullets": bullets})
    return {"meta": m, "sections": secs}


# ---------------------------------------------------------------------------
# CAMPAIGN DEEP DIVE
# ---------------------------------------------------------------------------
_VERDICTS = {
    "scale": ("good", "Verdict: *scale* it.", "Scale when leads grow 15% or more on at least 10 leads."),
    "refresh": ("warn", "Verdict: *refresh* the creative.",
                "Refresh when leads fall 15% to 50%, or when the second half of the period runs 15% or more "
                "below the first."),
    "sunset": ("bad", "Verdict: *pause* it and move the budget.",
               "Pause when leads fall by half or more, or when no lead arrives in the last 7 days."),
    "hold": ("neutral", "Verdict: *hold* steady.",
             "Hold when leads stay within 15% of the earlier period and the period ends as strong as it started."),
    "test": ("neutral", "Verdict: keep *testing*.", "Judge a new campaign after two full periods, not one."),
}


def _not_found(name, m, current, want, period):
    import difflib
    camps = _counts(current, _camp)
    close = difflib.get_close_matches(want.lower(), list(camps), n=2, cutoff=0.6)
    body = ([("We looked for utm_campaign “%s” (ignoring letter case, spaces and underscores) across %s "
              "from %s." % (want, _pl(len(current), "lead"), period))] if want else
            ["No campaign name was given, so there is nothing to look up."])
    if close:
        body.append("The closest tag%s %s." % ("s are" if len(close) > 1 else " is",
                                              " and ".join("\u201c%s\u201d" % c for c in close)))
    elif camps:
        body.append("Pick one of the campaigns below and run the deep dive again.")
    else:
        body.append("No lead in this period carried a campaign tag at all.")
    secs = [{"type": "title-block", "kicker": "%s · %s" % (name, period),
             "title": ("No leads were tagged *%s* in this period." % want) if want else
             "Pick a *campaign* for the deep dive.",
             "meta_bits": [b for b in [m.get("customer_domain"), "%s submissions" % n(len(current))] if b]},
            {"type": "insight-card", "kicker": "What we searched",
             "title": "The *campaign* name didn't match." if want else "No *campaign* was named.",
             "body": body, "tone": "warn"}]
    if camps:
        secs.append({"type": "ranked-list", "title": "Campaigns that did bring *leads*",
                     "columns": [{"key": "rank", "label": "#", "type": "rank"},
                                 {"key": "tag", "label": "utm_campaign", "type": "source"},
                                 {"key": "leads", "label": "Leads", "type": "bar"}],
                     "rows": [{"rank": str(i + 1), "tag": c, "leads": {"value": v, "label": n(v)}}
                              for i, (c, v) in enumerate(camps.most_common(10))]})
    secs.append({"type": "closing", "kicker": "Next step",
                 "title": "Next: re-run the deep dive with %s." % (
                     "*%s*" % close[0] if close else "a *campaign* from this list"),
                 "body": "The deep dive matches the utm_campaign tag, ignoring letter case, spaces and underscores."})
    m["sources"] = [{"name": "UTM Grabber", "detail": _pl(len(current), "lead")}]
    return {"meta": m, "sections": secs}


def build_campaign_deep_dive(current, campaign_name, prior=None, brand_profile=None, customer_name=None,
                             customer_domain="", form_label=None, compare_label=None, prepared_by=None,
                             prepared_for=None, **_):
    """One campaign in depth: volume, where its leads came from, ads, pages and a verdict with its rule."""
    current, prior = list(current or []), _usable(prior)
    want = _clean(campaign_name)
    want = "" if want.lower() in _NULLS else want
    key, nk = want.lower(), norm_key(want)

    def match(e):
        c = _camp(e)
        return bool(c) and (c == key or norm_key(c) == nk)

    start, end = span(current)
    pstart, pend = span(prior) if prior else (None, None)
    m = meta(brand_profile, customer_name, customer_domain,
             compare_label=compare_label or (_prior_label(pstart, pend) if prior else "last period"),
             sources=None, prepared_by=prepared_by, prepared_for=prepared_for)
    label = _trim(pretty(key), 40) if key else "This campaign"
    name = "Campaign deep dive"
    if not current:
        return empty_report("%s · %s" % (name, label), m)
    if start is None:
        return _undated(name, m, current)
    period = period_label(start, end)
    camp = [e for e in current if match(e)]
    if not camp:
        return _not_found(name, m, current, want, period)
    camp_p = [e for e in prior if match(e)]
    cur, prev = len(camp), len(camp_p)
    if cur < 10:
        return _thin("%s · %s" % (name, label), m, camp, period, "this campaign")
    cmp_ = m["compare_label"]
    has_prior = bool(prior)
    total_all = len(current)
    days = (end - start).days + 1
    tag = Counter(_val(e, "utm_campaign (HandL)", "utm_campaign") for e in camp).most_common(1)[0][0]
    m["sources"] = [{"name": "UTM Grabber", "detail": "%s of %s" % (_pl(cur, "lead"), n(total_all))}]

    labels, daily = daily_counts(camp, start, end)
    _, others = daily_counts([e for e in current if not match(e)], start, end)
    active = sum(1 for v in daily if v)
    peak_i = max(range(len(daily)), key=lambda i: daily[i])
    camps = _counts(current, _camp)
    rank = 1 + sum(1 for v in camps.values() if v > cur)
    sh = share(cur, total_all)
    sh_p = share(prev, len(prior)) if has_prior else None
    g = _growth(cur, prev) if has_prior else None
    a, b = _halves(daily)
    sig = abs(b - a) >= (a + b) ** 0.5
    mom = (100.0 * (b - a) / a if a else 100.0) if a + b >= 6 else 0.0
    last7 = sum(daily[-7:])
    weekly_avg = cur * 7.0 / days

    # verdict, from explicit rules
    if has_prior and prev == 0:
        verdict = "test"
    elif (g is not None and g <= -50) or (last7 == 0 and days >= 14):
        verdict = "sunset"
    elif g is not None and g >= 15 and cur >= 10:
        verdict = "scale"
    elif (g is not None and g <= -15) or (mom <= -15 and sig):
        verdict = "refresh"
    elif g is None and mom >= 15 and sig:
        verdict = "scale"
    else:
        verdict = "hold"
    tone, vtitle, rule = _VERDICTS[verdict]
    what = []
    if has_prior and prev:
        what.append("%s %s against %s (%s to %s)." % (
            label, "grew %s" % _signed(g)[1:] if g >= 3 else ("fell %s" % _signed(g)[1:] if g <= -3 else "held level"),
            cmp_, n(prev), _pl(cur, "lead")))
    elif has_prior:
        what.append("%s is new this period with %s." % (label, _pl(cur, "lead")))
    if a + b >= 6:
        what.append("The second half of the period brought %s against %s in the first half." % (_pl(b, "lead"), n(a)))
    if last7 == 0:
        what.append("No lead arrived in the last 7 days.")
    what.append("The rule: " + rule[:1].lower() + rule[1:])

    # headline
    if has_prior and prev:
        if g >= 3:
            headline = "*%s* grew %s to %s." % (label, _signed(g)[1:], _pl(cur, "lead"))
        elif g <= -3:
            headline = "*%s* fell %s to %s." % (label, _signed(g)[1:], _pl(cur, "lead"))
        else:
            headline = "*%s* held steady at %s." % (label, _pl(cur, "lead"))
    elif has_prior:
        headline = "*%s* brought %s in its first period." % (label, _pl(cur, "lead"))
    else:
        headline = "*%s* brought %s, %s of all leads." % (label, _pl(cur, "lead"), pct(sh))
    sms = Counter(_sm(e) or "(not set)" for e in camp)
    pages = _counts(camp, _page)
    ads = Counter(_ad(e) for e in camp)
    top_sm = sms.most_common(1)[0]
    sub = ["%s of all leads in the period, #%d of %s." % (pct(sh), rank, _pl(len(camps), "campaign"))]
    if pages:
        sub.append("Most came through %s and landed on %s." % (top_sm[0], _pname(pages.most_common(1)[0][0])))
    else:
        sub.append("Most came through %s." % top_sm[0])

    stats = [_stat_count("Leads", cur, prev if has_prior else None, spark=daily,
                         note=("%s %s" % (n(prev), cmp_)) if has_prior else "Daily, %s" % _pl(days, "day")),
             stat("Share of all leads", pct(sh), sh, sh_p, kind="pts", good="neutral",
                  note="#%d of %s" % (rank, _pl(len(camps), "campaign"))),
             stat("Active days", "%d of %d" % (active, days), good="neutral",
                  note="%.1f leads per active day" % (cur / float(active or 1))),
             dict(stat("Last 7 days", n(last7), last7, weekly_avg, good="up",
                       note="Weekly average %.1f" % weekly_avg), compare="its weekly average")]
    secs = [{"type": "title-block", "kicker": "Campaign deep dive · %s" % period, "title": headline,
             "subtitle": " ".join(sub),
             "meta_bits": [b for b in [customer_domain, "utm_campaign: %s" % tag, _pl(days, "day")] if b]},
            {"type": "stat-strip", "stats": stats},
            {"type": "insight-card", "kicker": "The verdict", "title": vtitle, "body": what, "tone": tone}]

    # 01 volume
    tagged_others = [e for e in current if _camp(e) and not match(e)]
    n_other = len(set(_camp(e) for e in tagged_others))
    if n_other >= 2 and (total_all - cur) > 4 * cur:
        _, oc = daily_counts(tagged_others, start, end)
        ref = {"label": "Average campaign", "values": [round(v / float(n_other), 2) for v in oc], "style": "dashed"}
        dek = "This campaign against the average of the other %s, per day." % _pl(n_other, "campaign")
        ref_note = " The dashed line is all other campaign leads divided by %s campaigns." % n(n_other)
    else:
        ref = {"label": "All other leads", "values": others, "style": "dashed"}
        dek = "This campaign against every other lead on the site, per day."
        ref_note = ""
    secs.append({"type": "section-header", "number": "01", "kicker": "Volume",
                 "title": "How *%s* moved, day by day." % label, "dek": dek})
    secs.append({"type": "chart",
                 "chart": {"type": "line-multi", "labels": labels,
                           "series": [{"label": _trim(label, 22), "values": daily}, ref]},
                 "chart_title": "Leads per *day*",
                 "caption": "Peak of %s on %s. Leads arrived on %d of %s.%s" % (
                     _pl(daily[peak_i], "lead"), labels[peak_i], active, _pl(days, "day"), ref_note)})

    # 02 where the leads came from
    has_ft = _has_first_touch(camp)
    if len(sms) >= 2 or has_ft:
        secs.append({"type": "section-header", "number": "02", "kicker": "Sources",
                     "title": "Where its *leads* came from.",
                     "dek": ("Source and medium at the last touch%s." % (
                         ", then the channel that first brought each lead to the site" if has_ft else ""))
                     if len(sms) >= 2 else
                     "Every lead came through %s. Below: the channel that first brought each lead to the site." % top_sm[0]})
        if len(sms) >= 2:
            top = sms.most_common(6)
            secs.append({"type": "chart-insight",
                         "chart": {"type": "bar-horizontal", "labels": [k for k, _ in top],
                                   "values": [v for _, v in top], "x_title": "Leads", "highlight": 0, "total": cur},
                         "caption": "Leads per utm_source / utm_medium inside this campaign",
                         "insight_kicker": "The mix",
                         "insight_title": "*%s* sent %s of its leads." % (top_sm[0], pct(share(top_sm[1], cur))),
                         "insight_body": ["%s of %s leads came through %s." % (n(top_sm[1]), n(cur), top_sm[0]),
                                          "The campaign tag is shared by %s source and medium pairs. Make sure "
                                          "that is on purpose." % n(len(sms))]})
        if has_ft:
            ft = Counter(first_touch(e) for e in camp)
            items = [(c, ft.get(c, 0)) for c in CHANNELS if ft.get(c, 0)]
            opened = Counter(first_touch(e) for e in camp if first_touch(e) != last_touch(e))
            n_open = sum(opened.values())
            if opened and share(n_open, cur) >= 20:
                oc, ov = opened.most_common(1)[0]
                hl = oc
                ft_title = "*%s* opened %s of these journeys." % (oc, pct(share(ov, cur)))
                body = ["%s of %s leads first found the site through %s, then converted on this campaign." % (
                            n(ov), n(cur), oc.lower()),
                        "Last-touch reports give the campaign all the credit for them."]
            else:
                hl = ft.most_common(1)[0][0]
                ft_title = "Most of these journeys started on *%s* too." % hl.lower()
                body = ["%s of %s leads started and finished on the same channel; %s were warmed up elsewhere first." % (
                    n(cur - n_open), n(cur), n(n_open))]
            secs.append({"type": "chart-insight",
                         "chart": {"type": "bar-horizontal", "labels": [c for c, _ in items],
                                   "values": [v for _, v in items], "x_title": "Leads",
                                   "highlight": hl, "total": cur},
                         "caption": "First-touch channel of the leads this campaign converted",
                         "insight_kicker": "First touch", "insight_title": ft_title, "insight_body": body})

    # 03 ads and pages
    ad_rows = []
    known_ads = [(k, v) for k, v in ads.most_common() if k]
    ads_p = Counter(_ad(e) for e in camp_p)
    for i, (k, v) in enumerate(known_ads[:8]):
        es = [e for e in camp if _ad(e) == k]
        _, dl = daily_counts(es, start, end)
        row = {"rank": str(i + 1), "ad": k, "leads": {"value": v, "label": n(v)}, "share": pct(share(v, cur)),
               "momentum": _momentum(dl)}
        if has_prior:
            row["change"] = _delta_cell(v, ads_p.get(k, 0))
        ad_rows.append(row)
    page_rows = [{"rank": str(i + 1), "page": k, "leads": {"value": v, "label": n(v)}, "share": pct(share(v, cur))}
                 for i, (k, v) in enumerate(pages.most_common(8))]
    no_ad = ads.get("", 0)
    if ad_rows or page_rows:
        secs.append({"type": "section-header", "number": "03" if len(sms) >= 2 or has_ft else "02",
                     "kicker": "Ads and pages", "title": "Which *ads* and pages did the work.",
                     "dek": "Ads are utm_content values. Pages are where the visit started, without query strings."})
    if ad_rows:
        cols = [{"key": "rank", "label": "#", "type": "rank"}, {"key": "ad", "label": "Ad (utm_content)", "type": "source"},
                {"key": "leads", "label": "Leads", "type": "bar"}, {"key": "share", "label": "Share", "type": "pct", "align": "right"}]
        if has_prior:
            cols.append({"key": "change", "label": "Change", "type": "delta", "align": "right"})
        cols.append({"key": "momentum", "label": "Momentum", "type": "trend"})
        secs.append({"type": "ranked-list", "title": "Leads by *ad*", "columns": cols, "rows": ad_rows,
                     "caption": ("%s had no utm_content, so their ad is unknown." % _pl(no_ad, "lead").capitalize())
                     if no_ad else "Every lead carried a utm_content value."})
    if page_rows:
        secs.append({"type": "ranked-list", "title": "Leads by landing *page*",
                     "columns": [{"key": "rank", "label": "#", "type": "rank"},
                                 {"key": "page", "label": "Landing page", "type": "source"},
                                 {"key": "leads", "label": "Leads", "type": "bar"},
                                 {"key": "share", "label": "Share", "type": "pct", "align": "right"}],
                     "rows": page_rows,
                     "caption": "Leads per page, not conversion rates: pages with more visits will show more leads."})

    # next steps
    recs = []
    others_c = [(c, v) for c, v in camps.most_common() if c != key and norm_key(c) != nk]
    if verdict == "scale":
        recs.append({"label": "This month", "title": "Raise the budget on *%s* in steps" % label,
                     "body": "It %s. Add budget in small steps and stop if lead quality slips." % (
                         ("grew %s to %s" % (_signed(g)[1:], _pl(cur, "lead"))) if g is not None else
                         ("ran %s stronger in its second half" % _signed(mom)[1:])),
                     "impact": "High", "effort": "Medium"})
    elif verdict == "refresh":
        recs.append({"label": "This week", "title": "Refresh the *creative* in %s" % label,
                     "body": "%s Swap in new ad copy and images, and keep the best performer running." % what[0],
                     "impact": "High", "effort": "Medium"})
    elif verdict == "sunset":
        dest = None
        if has_prior:
            prior_c = _counts(prior, _camp)
            up = [(c, v) for c, v in others_c if prior_c.get(c) and _growth(v, prior_c[c]) >= 15 and v >= 5]
            dest = up[0][0] if up else None
        where = (" Move the budget to %s, which is growing." % pretty(dest)) if dest else (
            (" Move the budget to %s, your top campaign." % pretty(others_c[0][0])) if others_c else "")
        recs.append({"label": "This week", "title": "Pause *%s* and move its budget" % label,
                     "body": what[0] + where, "impact": "High", "effort": "Low"})
    elif verdict == "test":
        recs.append({"label": "Next %s" % _pl(days, "day"), "title": "Give *%s* another period" % label,
                     "body": "It is new with %s. Keep it running %s more before you judge it." % (
                         _pl(cur, "lead"), _pl(days, "day")), "impact": "Medium", "effort": "Low"})
    else:
        recs.append({"label": "Ongoing", "title": "Keep *%s* running as it is" % label,
                     "body": "It delivered %s, %s of all leads. Change one thing at a time so you can see what "
                             "works." % (_pl(cur, "lead"), pct(sh)), "impact": "Medium", "effort": "Low"})
    if len(known_ads) >= 2 and known_ads[0][1] >= 5 and known_ads[0][1] >= 2 * known_ads[-1][1]:
        (bk, bv), (wk, wv) = known_ads[0], known_ads[-1]
        recs.append({"label": "This week", "title": "Shift spend to the *%s* ad" % _trim(bk, 28),
                     "body": "It brought %s of %s leads (%s). The weakest ad, %s, brought %s." % (
                         n(bv), n(cur), pct(share(bv, cur)), _trim(wk, 28), n(wv)),
                     "impact": "Medium", "effort": "Low"})
    if len(pages) >= 2 and share(pages.most_common(1)[0][1], cur) >= 40:
        pk, pv = pages.most_common(1)[0]
        recs.append({"label": "This week", "title": "Check the message match on *%s*" % _trim(_pname(pk), 30),
                     "body": "%s of this campaign's leads landed there. Make sure its headline repeats the ad's "
                             "promise." % pct(share(pv, cur)), "impact": "Medium", "effort": "Low"})
    if share(no_ad, cur) >= 30:
        recs.append({"label": "This week", "title": "Tag every ad with *utm_content*",
                     "body": "%s of this campaign's leads had no utm_content, so you can't tell which ad worked." % (
                         pct(share(no_ad, cur))), "impact": "Medium", "effort": "Low"})
    if len(recs) < 2:
        recs.append({"label": "Next period", "title": "Re-run this deep dive in *%s*" % _pl(days, "day"),
                     "body": "One more period shows whether %s's pattern holds." % label,
                     "impact": "Low", "effort": "Low"})
    n_sec = sum(1 for x in secs if x["type"] == "section-header") + 1
    secs.append({"type": "section-header", "number": "%02d" % n_sec, "kicker": "Next steps",
                 "title": "What to do with *%s*." % label})
    secs.append({"type": "recommendations", "items": recs[:4]})
    secs.append({"type": "notes", "title": "How we built this report", "items": [
        "Leads counted where utm_campaign matches “%s” (ignoring letter case, spaces and underscores), %s." % (
            tag, period),
        ("Change compares with %s (%s for this campaign)." % (cmp_, _pl(prev, "lead"))) if has_prior else
        "No earlier period was supplied, so the verdict uses the first and second half of this period.",
        ("Momentum and the verdict's second-half test compare the last %s with the first %d." % (
            _pl(days // 2, "day"), days // 2)) if days >= 2 else "The period is a single day, so there is no momentum test."]})

    if verdict == "scale":
        ctitle = "Next: scale *%s*. %s" % (label, ("It grew %s to %s." % (_signed(g)[1:], _pl(cur, "lead"))) if g is not None
                                            else "Its second half beat its first by %s." % _signed(mom)[1:])
    elif verdict == "refresh":
        ctitle = "Next: refresh *%s*. %s" % (label, ("Leads fell %s to %s." % (_signed(g)[1:], n(cur))) if g is not None and g <= -15
                                              else "Its second half brought %s, down from %s." % (n(b), n(a)))
    elif verdict == "sunset":
        ctitle = "Next: pause *%s* and move the budget. %s" % (
            label, "It fell from %s to %s." % (_pl(prev, "lead"), n(cur)) if has_prior and prev else
            "No lead arrived in the last 7 days.")
    elif verdict == "test":
        ctitle = "Next: give *%s* another %s. It is new, with %s." % (label, _pl(days, "day"), _pl(cur, "lead"))
    else:
        ctitle = "Next: keep *%s* running. It holds at %s." % (label, _pl(cur, "lead"))
    bullets = ["Busiest day: %s with %s." % (labels[peak_i], _pl(daily[peak_i], "lead"))]
    if known_ads:
        bullets.append("Top ad: %s with %s." % (_trim(known_ads[0][0], 32), _pl(known_ads[0][1], "lead")))
    if pages:
        bullets.append("Top landing page: %s with %s." % (_trim(_pname(pages.most_common(1)[0][0]), 32),
                                                          _pl(pages.most_common(1)[0][1], "lead")))
    secs.append({"type": "closing", "kicker": "The campaign in one line", "title": ctitle,
                 "summary_stats": [{"value": n(cur), "label": "Leads"},
                                   {"value": pct(sh), "label": "Share of all leads"},
                                   {"value": "%d of %d" % (active, days), "label": "Active days"},
                                   {"value": verdict.capitalize() if verdict != "sunset" else "Pause", "label": "Verdict"}],
                 "bullets": bullets})
    return {"meta": m, "sections": secs}


# ---------------------------------------------------------------------------
# SIDE BY SIDE
# ---------------------------------------------------------------------------
def _profile(es, days=None):
    st, en = span(es)
    d = days or (((en - st).days + 1) if st else 1)
    tot = len(es)
    src, camps = _counts(es, _src), _counts(es, _camp)
    chans = Counter(last_touch(x) for x in es)
    return {"total": tot, "days": d, "per_day": tot / float(d), "paid": share(chans.get("Paid", 0), tot),
            "cov": _cov(es), "src": src, "camps": camps, "chans": chans, "start": st, "end": en,
            "top_src": src.most_common(1)[0] if src else ("", 0), "top_camp": camps.most_common(1)[0] if camps else ("", 0)}


def build_side_by_side(a_entries, a_label, b_entries, b_label, brand_profile=None, customer_name=None,
                       customer_domain="", form_label=None, compare_label=None, prepared_by=None,
                       prepared_for=None, **_):
    """Two subjects (campaigns, sources, forms or periods) on the same measures, with a verdict per measure."""
    A, B = list(a_entries or []), list(b_entries or [])
    la, lb = _clean(a_label), _clean(b_label)
    la = la if la and la.lower() not in _NULLS else "A"
    lb = lb if lb and lb.lower() not in _NULLS else "B"
    if la.lower() == lb.lower():
        la, lb = la + " (A)", lb + " (B)"
    m = meta(brand_profile, customer_name, customer_domain, compare_label=compare_label or lb,
             sources=None, prepared_by=prepared_by, prepared_for=prepared_for)
    name = "Side by side"
    if not A and not B:
        return empty_report("%s · %s vs %s" % (name, la, lb), m)
    sa, ea = span(A)
    sb, eb = span(B)
    if not (sa or sb):
        return _undated(name, m, A + B)
    overlap = bool(sa and sb and sa <= eb and sb <= ea)
    if overlap or not (sa and sb):
        lo, hi = min(d for d in (sa, sb) if d), max(d for d in (ea, eb) if d)
        period = period_label(lo, hi)
    else:
        period = "%s vs %s" % (period_label(sa, ea), period_label(sb, eb))
    kicker = "Side by side · %s" % period
    if len(A) + len(B) < 10:
        return _thin(name, m, A + B, period, "%s and %s together" % (la, lb))
    if not A or not B:
        empty_side, full_side = (la, lb) if not A else (lb, la)
        return _short(name, m, A or B, period,
                      why=["%s had no leads in this window, so there is nothing to compare %s against." % (
                          empty_side, full_side),
                           "Check the filter or date range for %s, then run the comparison again." % empty_side],
                      ins_title="One side of the comparison is *empty*.",
                      title="%s had no leads to compare with *%s*." % (empty_side, full_side),
                      next_title="Next: check the filter for *%s* and compare again." % empty_side)
    m["sources"] = [{"name": "UTM Grabber", "detail": "%s vs %s leads" % (n(len(A)), n(len(B)))}]
    if overlap:
        lo, hi = min(sa, sb), max(ea, eb)
        days = (hi - lo).days + 1
        pa, pb = _profile(A, days), _profile(B, days)
    else:
        pa, pb = _profile(A), _profile(B)
    single_src = (share(pa["top_src"][1], pa["total"]) >= 95 and share(pb["top_src"][1], pb["total"]) >= 95)

    rows, wins = [], {"a": [], "b": []}

    def add(label, av, bv, ad, bd, better=None, tally=True, rate=False):
        row = {"label": label, "a": round(av, 2), "b": round(bv, 2), "a_display": ad, "b_display": bd}
        # a win must be material: 3+ points on a rate, 3%+ on a count
        gap_ok = abs(av - bv) >= 3 if rate else abs(av - bv) >= 0.03 * max(abs(av), abs(bv), 1e-9)
        if better and gap_ok:
            w = ("a" if av > bv else "b") if better == "high" else ("a" if av < bv else "b")
            row["better"] = w
            if tally:
                wins[w].append(label.lower())
        rows.append(row)

    add("Leads", pa["total"], pb["total"], n(pa["total"]), n(pb["total"]), "high")
    if pa["days"] != pb["days"]:
        add("Leads per day", pa["per_day"], pb["per_day"], "%.1f" % pa["per_day"], "%.1f" % pb["per_day"], "high")
    add("Fully tagged", pa["cov"], pb["cov"], pct(pa["cov"]), pct(pb["cov"]), "high", rate=True)
    if not ((pa["paid"] >= 99 and pb["paid"] >= 99) or (pa["paid"] <= 1 and pb["paid"] <= 1)):
        add("Paid share", pa["paid"], pb["paid"], pct(pa["paid"]), pct(pb["paid"]))
    if not single_src:
        add("Sources with leads", len(pa["src"]), len(pb["src"]), n(len(pa["src"])), n(len(pb["src"])))
        sa_, sb_ = share(pa["top_src"][1], pa["total"]), share(pb["top_src"][1], pb["total"])
        add("Top source share", sa_, sb_,
            "%s %s" % (_trim(source_label(pa["top_src"][0]), 10), pct(sa_)) if pa["top_src"][0] else "\u2013",
            "%s %s" % (_trim(source_label(pb["top_src"][0]), 10), pct(sb_)) if pb["top_src"][0] else "\u2013")
    ca, cb = share(pa["top_camp"][1], pa["total"]), share(pb["top_camp"][1], pb["total"])
    if pa["top_camp"][0] or pb["top_camp"][0]:
        add("Top campaign share", ca, cb, pct(ca) if pa["top_camp"][0] else "–", pct(cb) if pb["top_camp"][0] else "–")
    quality = []
    for qlabel, test, _field in _quality_rules(A + B):
        qa, na = _rule_share(A, test)
        qb, nb = _rule_share(B, test)
        if na >= 5 and nb >= 5:
            add(qlabel, qa, qb, pct(qa), pct(qb), "high", rate=True)
            quality.append((qlabel, qa, qb))

    # verdict
    ka, kb = len(wins["a"]), len(wins["b"])
    tally = ka + kb
    if ka == kb:
        v_title = ("A split *decision*: %s each." % _pl(ka, "win")) if ka else "Too close to *call* on every measure."
    else:
        w = la if ka > kb else lb
        v_title = ("*%s* wins on %s; the rest is close." % (w, (wins["a"] or wins["b"])[0])) if tally == 1 else (
            "*%s* wins %s of %s measures." % (w, n(max(ka, kb)), n(tally)))
    v_body = []
    for side, lab in (("a", la), ("b", lb)):
        if wins[side] and tally > 1:
            v_body.append("%s wins on %s." % (lab, ", ".join(wins[side])))
    v_body.append("Gaps under 3 points (or 3% on counts) don't count as wins. Paid share and concentration are "
                  "context, not wins.")

    # headline
    if pa["total"] != pb["total"]:
        big, small = (pa, pb) if pa["total"] > pb["total"] else (pb, pa)
        lbig, lsmall = (la, lb) if big is pa else (lb, la)
        gap = 100.0 * (big["total"] - small["total"]) / small["total"]
        headline = ("*%s* brought %s more leads than %s." % (lbig, pct(gap), lsmall)) if gap < 100 else (
            "*%s* brought %.1fx the leads of %s." % (lbig, big["total"] / float(small["total"]), lsmall))
    else:
        headline = "*%s* and %s brought the same number of leads." % (la, lb)
    sub = ["%s: %s, %s fully tagged. %s: %s, %s fully tagged." % (
        la, _pl(pa["total"], "lead"), pct(pa["cov"]), lb, _pl(pb["total"], "lead"), pct(pb["cov"]))]

    lead_gap = _growth(pa["total"], pb["total"])
    lead_s, trail_s = (la, lb) if pa["total"] >= pb["total"] else (lb, la)
    lead_adv = _growth(max(pa["total"], pb["total"]), min(pa["total"], pb["total"]))
    tag_s = la if pa["cov"] >= pb["cov"] else lb
    tag_adv = abs(round(pa["cov"] - pb["cov"]))
    secs = [{"type": "title-block", "kicker": kicker, "title": headline, "subtitle": " ".join(sub),
             "meta_bits": [b for b in [customer_domain, "%s vs %s" % (la, lb)] if b]}]
    if overlap:
        lo, hi = min(sa, sb), max(ea, eb)
        lab_d, da = daily_counts(A, lo, hi)
        _, db = daily_counts(B, lo, hi)
    else:
        _, da = daily_counts(A, sa, ea)
        _, db = daily_counts(B, sb, eb)
        k = max(len(da), len(db))
        lab_d = ["Day %d" % (i + 1) for i in range(k)]
        da = da + [None] * (k - len(da))
        db = db + [None] * (k - len(db))
    secs.append({"type": "stat-strip", "stats": [
        stat("%s leads" % _trim(la, 18), n(pa["total"]), spark=[x for x in da if x is not None], good="neutral",
             note="%.1f a day" % pa["per_day"]),
        stat("%s leads" % _trim(lb, 18), n(pb["total"]), spark=[x for x in db if x is not None], good="neutral",
             note="%.1f a day" % pb["per_day"]),
        stat("Lead gap", ("+" + pct(lead_adv)) if lead_adv else "Even", good="neutral",
             note=("%s over %s" % (_trim(lead_s, 22), _trim(trail_s, 22))) if lead_adv else "Same number of leads"),
        stat("Tagging gap", ("+%s pts" % n(tag_adv)) if tag_adv else "Even", good="neutral",
             note=("%s tags more, %s vs %s" % (_trim(tag_s, 18), pct(max(pa["cov"], pb["cov"])),
                                               pct(min(pa["cov"], pb["cov"])))) if tag_adv else
             "Both tag %s of leads" % pct(pa["cov"]))]})

    # 01 head to head
    secs.append({"type": "section-header", "number": "01", "kicker": "Head to head",
                 "title": "The same *measures*, side by side.",
                 "dek": "A tick marks the better side where higher is better. The rest is context."})
    secs.append({"type": "comparison", "a": {"label": la, "sub": _pl(pa["total"], "lead")},
                 "b": {"label": lb, "sub": _pl(pb["total"], "lead")}, "rows": rows,
                 "caption": ("Both sides cover %s." % period) if overlap else
                 ("%s covers %s; %s covers %s." % (la, period_label(sa, ea), lb, period_label(sb, eb)))})
    secs.append({"type": "insight-card", "kicker": "The verdict", "title": v_title, "body": v_body,
                 "tone": "neutral"})

    # 02 rhythm
    secs.append({"type": "section-header", "number": "02", "kicker": "Rhythm", "title": "Day by *day*.",
                 "dek": "Leads per day on the same calendar." if overlap else
                 "Leads per day, lined up from each side's first day."})
    secs.append({"type": "chart", "chart": {"type": "line-multi", "labels": lab_d,
                                            "series": [{"label": _trim(la, 20), "values": da},
                                                       {"label": _trim(lb, 20), "values": db, "style": "dashed"}]},
                 "chart_title": "Leads per *day*",
                 "caption": "Busiest day: %s for %s, %s for %s." % (
                     _pl(max(x for x in da if x is not None), "lead"), la,
                     _pl(max(x for x in db if x is not None), "lead"), lb)})

    # 03 channel mix
    chans = [c for c in CHANNELS if pa["chans"].get(c) or pb["chans"].get(c)]
    gaps = sorted(((c, share(pa["chans"].get(c, 0), pa["total"]) - share(pb["chans"].get(c, 0), pb["total"]))
                   for c in chans), key=lambda x: -abs(x[1]))
    if len(chans) >= 2:
        gc, gv = gaps[0]
        secs.append({"type": "section-header", "number": "03", "kicker": "Channel mix",
                     "title": "Where each side's *leads* come from."})
        secs.append({"type": "chart-insight",
                     "chart": {"type": "bar-grouped", "labels": chans, "unit": "%",
                               "groups": [{"label": _trim(la, 20), "values": [round(share(pa["chans"].get(c, 0), pa["total"]), 1) for c in chans]},
                                          {"label": _trim(lb, 20), "values": [round(share(pb["chans"].get(c, 0), pb["total"]), 1) for c in chans]}]},
                     "caption": "Share of each side's leads by last-touch channel",
                     "insight_kicker": "The biggest gap",
                     "insight_title": "*%s* is the biggest difference: %s pts." % (gc, n(abs(round(gv)))),
                     "insight_body": ["%s gets %s of its leads from %s; %s gets %s." % (
                         la, pct(share(pa["chans"].get(gc, 0), pa["total"])), gc.lower(), lb,
                         pct(share(pb["chans"].get(gc, 0), pb["total"])))]})

    # next steps
    recs = []
    win_v = la if pa["total"] >= pb["total"] else lb
    lose_v = lb if win_v == la else la
    gap_pts = pa["cov"] - pb["cov"]
    if abs(gap_pts) >= 10:
        good_s, bad_s = (la, lb) if gap_pts > 0 else (lb, la)
        recs.append({"label": "This week", "title": "Bring *%s* tagging up to match %s" % (_trim(bad_s, 26), _trim(good_s, 26)),
                     "body": "%s tags %s of leads fully; %s tags %s. Copy the link template that works." % (
                         good_s, pct(max(pa["cov"], pb["cov"])), bad_s, pct(min(pa["cov"], pb["cov"]))),
                     "impact": "Medium", "effort": "Low"})
    gap_words = ("%.1fx the leads" % (max(pa["total"], pb["total"]) / float(min(pa["total"], pb["total"])))
                 if lead_adv and lead_adv >= 100 else "%s more leads" % pct(lead_adv or 0))
    if lead_adv is not None and lead_adv >= 10:
        recs.append({"label": "This month", "title": "Study what *%s* does differently" % _trim(win_v, 30),
                     "body": "It brought %s (%s vs %s). Compare its offer, landing page and audience against %s." % (
                         gap_words, n(max(pa["total"], pb["total"])), n(min(pa["total"], pb["total"])), lose_v),
                     "impact": "High", "effort": "Medium"})
    if not single_src and pa["top_src"][0] and pa["top_src"][0] != pb["top_src"][0]:
        wp, lp, wl, ll = (pa, pb, la, lb) if pa["total"] >= pb["total"] else (pb, pa, lb, la)
        k = wp["top_src"][0]
        recs.append({"label": "Next test", "title": "Test *%s* for %s" % (source_label(k), _trim(ll, 26)),
                     "body": "It is the top source for %s (%s of leads) but sends only %s of %s leads." % (
                         wl, pct(share(wp["top_src"][1], wp["total"])), pct(share(lp["src"].get(k, 0), lp["total"])), ll),
                     "impact": "Medium", "effort": "Medium"})
    for qlabel, qa, qb in quality:
        if abs(qa - qb) >= 10 and len(recs) < 4:
            hi_s, lo_s = (la, lb) if qa > qb else (lb, la)
            recs.append({"label": "Lead quality", "title": "Weigh *%s* for lead quality too" % _trim(hi_s, 26),
                         "body": "%s of its leads answered “%s” vs %s for %s." % (
                             pct(max(qa, qb)), qlabel.lower(), pct(min(qa, qb)), lo_s),
                         "impact": "Medium", "effort": "Low"})
    if max(pa["cov"], pb["cov"]) < 80 and len(recs) < 4:
        recs.append({"label": "This week", "title": "Tag every *link* on both sides",
                     "body": "Only %s of leads from %s and %s from %s arrived fully tagged. Untagged leads can't "
                             "be traced to a campaign." % (pct(pa["cov"]), la, pct(pb["cov"]), lb),
                     "impact": "Medium", "effort": "Low"})
    if len(recs) < 2:
        close = lead_adv is None or lead_adv < 10
        recs.append({"label": "Next period", "title": "Run this comparison again in *%d days*" % max(pa["days"], 7),
                     "body": ("The two sides are within 10% on leads. Another period shows whether either pulls "
                              "ahead.") if close else
                             ("%s leads by %s. Another period shows whether the lead holds." % (lead_s, pct(lead_adv))),
                     "impact": "Low", "effort": "Low"})
    secs.append({"type": "section-header", "number": "%02d" % (sum(1 for x in secs if x["type"] == "section-header") + 1),
                 "kicker": "Next steps", "title": "What to do with the *verdict*."})
    secs.append({"type": "recommendations", "items": recs[:4]})
    first = recs[0]
    ctitle = "Next: %s." % (first["title"][0].lower() + first["title"][1:])
    if first["title"].startswith("Tag every"):
        ctitle = "Next: tag every *link* on both sides. Only %s to %s of leads arrive fully tagged." % (
            pct(min(pa["cov"], pb["cov"])), pct(max(pa["cov"], pb["cov"])))
    elif first["title"].startswith("Run this comparison"):
        ctitle = "Next: compare again in *%d days*. %s" % (max(pa["days"], 7), (
            "The two sides are within %s on leads." % pct(lead_adv)) if lead_adv else "The two sides are level on leads.")
    elif first["title"].startswith("Test "):
        ctitle = "Next: %s. %s" % (first["title"][0].lower() + first["title"][1:], first["body"].split(". ")[0] + ".")
    elif first["title"].startswith("Weigh"):
        ctitle = "Next: %s. %s" % (first["title"][0].lower() + first["title"][1:], first["body"])
    if lead_adv is not None and lead_adv >= 10 and first["title"].startswith("Study"):
        ctitle = "Next: study what *%s* does differently. It brought %s." % (_trim(win_v, 30), gap_words)
    elif first["title"].startswith("Bring"):
        ctitle = "Next: lift *%s* tagging. It trails by %s pts." % (
            _trim(lb if gap_pts > 0 else la, 26), n(abs(round(gap_pts))))
    secs.append({"type": "closing", "kicker": "The verdict in one line", "title": ctitle,
                 "summary_stats": [{"value": n(pa["total"]), "label": "%s leads" % _trim(la, 16)},
                                   {"value": n(pb["total"]), "label": "%s leads" % _trim(lb, 16)},
                                   {"value": ("%d of %d" % (max(ka, kb), tally)) if ka != kb else "%d each" % ka,
                                    "label": ("Won by %s" % _trim(la if ka > kb else lb, 16)) if ka != kb else "Measures won"},
                                   {"value": "+%s pts" % n(tag_adv) if tag_adv else "Even", "label": "Tagging gap"}],
                 "bullets": [x for x in [
                     "%s: %s, %.1f a day, %s fully tagged." % (la, _pl(pa["total"], "lead"), pa["per_day"], pct(pa["cov"])),
                     "%s: %s, %.1f a day, %s fully tagged." % (lb, _pl(pb["total"], "lead"), pb["per_day"], pct(pb["cov"])),
                     ("Biggest channel gap: %s, %s pts." % (gaps[0][0].lower(), n(abs(round(gaps[0][1])))))
                     if len(chans) >= 2 else None] if x]})
    return {"meta": m, "sections": secs}


# ---------------------------------------------------------------------------
# AGENCY ROLLUP
# ---------------------------------------------------------------------------
def build_agency_rollup(brand_data_list, brand_profile=None, customer_name=None, customer_domain="",
                        form_label=None, compare_label=None, prepared_by=None, prepared_for=None, **_):
    """Every client on one page: who grew, who slipped, whose tagging needs work, and who to call."""
    items = [b for b in (brand_data_list or []) if isinstance(b, dict)]
    m = meta(brand_profile, customer_name, customer_domain, compare_label=compare_label or "the earlier period",
             sources=None, prepared_by=prepared_by, prepared_for=prepared_for)
    name = "Agency portfolio"
    clients = []
    for i, b in enumerate(items):
        es = list(b.get("entries") or b.get("leads") or [])
        raw_p = b.get("entries_prior", b.get("leads_prior"))
        nm = _clean(b.get("brand_name") or b.get("name") or b.get("customer_name") or "")
        clients.append({"name": nm if nm and nm.lower() not in _NULLS else "Client %d" % (i + 1),
                        "entries": es, "prior": list(raw_p) if raw_p is not None else None,
                        "domain": _clean(b.get("domain") or b.get("customer_domain") or "")})
    every = [e for c in clients for e in c["entries"]]
    if not every:
        return empty_report(name, m, reason="No client in this rollup had form submissions in the period.",
                            hint="Check each client's UTM Grabber connection, or add clients with /brand.")
    start, end = span(every)
    if start is None:
        return _undated(name, m, every)
    period = period_label(start, end)
    total = len(every)
    if total < 10:
        return _thin(name, m, every, period, "the whole portfolio")
    cmp_ = m["compare_label"]
    days = (end - start).days + 1
    m["sources"] = [{"name": "UTM Grabber", "detail": "%s across %s" % (_pl(total, "lead"), _pl(len(clients), "client"))}]
    for c in clients:
        es = c["entries"]
        c["v"] = len(es)
        c["pv"] = len(c["prior"]) if c["prior"] is not None else None
        c["g"] = _growth(c["v"], c["pv"]) if c["pv"] else None
        c["cov"] = _cov(es)
        src = _counts(es, _src)
        c["top"] = src.most_common(1)[0] if src else ("", 0)
        c["paid"] = share(sum(1 for e in es if last_touch(e) == "Paid"), len(es)) if es else 0.0
        _, c["daily"] = daily_counts(es, start, end)
        moved = bool(c["pv"]) and abs(c["v"] - c["pv"]) >= 5 and abs(c["v"] - c["pv"]) >= 0.1 * c["pv"]
        c["dir"] = ("up" if c["v"] > c["pv"] else "down") if moved else ("new" if c["pv"] == 0 and c["v"] else "flat")
    clients.sort(key=lambda c: (-c["v"], c["name"]))
    with_prior = [c for c in clients if c["pv"] is not None]
    up = [c for c in with_prior if c["dir"] == "up"]
    down = [c for c in with_prior if c["dir"] == "down"]
    avg_cov = sum(c["cov"] for c in clients if c["v"]) / float(max(1, sum(1 for c in clients if c["v"])))
    low_cov = min([c for c in clients if c["v"]], key=lambda c: (c["cov"], c["name"]))
    best = max(up, key=lambda c: (c["v"] - c["pv"], c["name"])) if up else None
    worst = max(down, key=lambda c: (c["pv"] - c["v"], c["name"])) if down else None
    all_prior = len(with_prior) == len(clients)
    total_p = sum(c["pv"] for c in with_prior) if all_prior else None
    _, port_daily = daily_counts(every, start, end)
    top_c = clients[0]

    # headline
    if all_prior and total_p:
        d = delta(total, total_p)
        if d.get("delta_direction") in ("up", "down"):
            headline = "The portfolio %s %s to *%s*." % (
                "grew" if d["delta_direction"] == "up" else "fell", d["delta_label"].lstrip("+\u2212"), _pl(total, "lead"))
        else:
            headline = "The portfolio held steady at *%s*." % _pl(total, "lead")
    else:
        headline = "%s brought *%s* across the portfolio." % (period_name(start, end), _pl(total, "lead"))
    sub = []
    if with_prior:
        sub.append("%s grew and %s slipped against %s." % (_pl(len(up), "client"), n(len(down)), cmp_))
    sub.append("%s is the biggest client with %s of portfolio leads." % (top_c["name"], pct(share(top_c["v"], total))))
    if worst:
        sub.append("%s slipped the most: %s, down from %s." % (worst["name"], _pl(worst["v"], "lead"), n(worst["pv"])))
    elif best:
        sub.append("%s grew the most: %s, up from %s." % (best["name"], _pl(best["v"], "lead"), n(best["pv"])))

    secs = [{"type": "title-block", "kicker": "Agency portfolio · %s" % period, "title": headline,
             "subtitle": " ".join(sub),
             "meta_bits": [b for b in [_pl(len(clients), "client"), "%s leads" % n(total), _pl(days, "day")] if b]},
            {"type": "stat-strip", "stats": [
                _stat_count("Portfolio leads", total, total_p, spark=port_daily,
                            note=("%s %s" % (n(total_p), cmp_)) if total_p is not None else "across %s" % _pl(len(clients), "client")),
                stat("Clients up", n(len(up)), good="neutral",
                     note=("of %s with an earlier period" % n(len(with_prior))) if with_prior else "No earlier period supplied"),
                stat("Clients down", n(len(down)), good="neutral",
                     note=("Biggest drop: %s" % _trim(worst["name"], 28)) if worst else "No client fell by 5+ leads"),
                stat("Avg. tagging", pct(avg_cov), good="neutral",
                     note="Lowest: %s, %s" % (_trim(low_cov["name"], 28), pct(low_cov["cov"])))]}]

    # 01 every client
    secs.append({"type": "section-header", "number": "01", "kicker": "The book",
                 "title": "Every *client* at a glance.",
                 "dek": "Leads this period, change against %s, and how many leads arrived fully tagged." % cmp_
                 if with_prior else "Leads this period and how many arrived fully tagged."})
    rows = []
    for i, c in enumerate(clients[:12]):
        tone = "good" if c["cov"] >= 80 else ("warn" if c["cov"] >= 50 else "bad")
        row = {"rank": str(i + 1), "client": c["name"], "leads": {"value": c["v"], "label": n(c["v"])},
               "tagged": {"label": pct(c["cov"]), "tone": tone},
               "top": ("%s, %s" % (source_label(c["top"][0]), pct(share(c["top"][1], c["v"])))) if c["top"][0] else "Not tagged",
               "daily": c["daily"]}
        if with_prior:
            row["change"] = _delta_cell(c["v"], c["pv"]) if c["pv"] is not None else {"label": "–", "direction": "flat"}
        if worst is c:
            row["_highlight"] = True
        rows.append(row)
    cols = [{"key": "rank", "label": "#", "type": "rank"}, {"key": "client", "label": "Client", "type": "name"},
            {"key": "leads", "label": "Leads", "type": "bar"}]
    if with_prior:
        cols.append({"key": "change", "label": "Change", "type": "delta", "align": "right"})
    cols += [{"key": "tagged", "label": "Tagged", "type": "badge"}, {"key": "top", "label": "Top source", "type": "text"},
             {"key": "daily", "label": "Daily", "type": "spark"}]
    secs.append({"type": "ranked-list", "title": "Clients by *leads*", "columns": cols, "rows": rows,
                 "caption": "Tagged: leads with source, medium and campaign. Green 80% or more, amber 50% to 79%, red "
                            "under 50%." +
                            (" Highlighted: the client that slipped the most." if worst else "")})

    # callouts
    calls = []
    if best:
        calls.append({"kicker": "Best client", "value": _signed(best["g"]), "tone": "good",
                      "title": "%s: %s, up from %s" % (best["name"], _pl(best["v"], "lead"), n(best["pv"]))})
    if worst:
        calls.append({"kicker": "Needs attention", "value": _signed(worst["g"]), "tone": "bad",
                      "title": "%s: %s, down from %s" % (worst["name"], _pl(worst["v"], "lead"), n(worst["pv"]))})
    if low_cov["cov"] < 60:
        calls.append({"kicker": "Tagging gap", "value": pct(low_cov["cov"]), "tone": "warn",
                      "title": "of leads from %s arrived fully tagged" % low_cov["name"]})
    calls.append({"kicker": "Biggest client", "value": pct(share(top_c["v"], total)), "tone": "neutral",
                  "title": "of portfolio leads come from %s" % top_c["name"]})
    if len(calls) < 2:
        calls.append({"kicker": "Average client", "value": n(round(total / float(len(clients)))), "tone": "neutral",
                      "title": "leads per client this period"})
    secs.append({"type": "callouts", "items": calls[:4]})

    # 02 growth map
    plotted = [c for c in with_prior if c["pv"] and max(c["v"], c["pv"]) >= 3]
    if len(plotted) >= 3:
        x_ref = median([c["v"] for c in plotted])
        pts = [{"label": _trim(c["name"], 24), "x": c["v"], "y": round(max(-100.0, min(200.0, c["g"])), 1),
                "size": max(c["v"], 1)} for c in plotted]
        ins = []
        if best:
            ins.append("%s grew %s to %s." % (best["name"], _signed(best["g"])[1:], _pl(best["v"], "lead")))
        if worst:
            ins.append("%s fell %s to %s." % (worst["name"], _signed(worst["g"])[1:], _pl(worst["v"], "lead")))
        secs.append({"type": "section-header", "number": "02", "kicker": "Growth map",
                     "title": "Which *clients* are growing.",
                     "dek": "Across: leads this period. Up: change against %s." % cmp_})
        secs.append({"type": "matrix", "chart_title": "Volume vs *growth*", "points": pts,
                     "x_label": "Leads this period", "y_label": "Change vs %s" % cmp_, "y_unit": "%",
                     "x_ref": x_ref, "y_ref": 0,
                     "quadrants": {"tr": "Growing", "br": "Big, slipping", "tl": "Small, growing", "bl": "At risk"},
                     "insight_kicker": "Read the map",
                     "insight_title": ("*%s* is the account to grow." % best["name"]) if best else (
                         ("*%s* is the account at risk." % worst["name"]) if worst else "Every *client* held steady."),
                     "insight_body": ins or ["No client moved by 5 leads or more against %s." % cmp_],
                     "caption": "The vertical line is the median client (%s leads).%s" % (
                         n(x_ref), " Growth is capped at +200%." if any(p["y"] >= 200 for p in pts) else "")})

    # next steps
    recs = []
    if worst:
        recs.append({"label": "This week", "title": "Call *%s*" % worst["name"],
                     "body": "Leads fell %s to %s (from %s). Check paused campaigns, budget caps and form errors%s "
                             "before the next report goes out." % (_signed(worst["g"])[1:], n(worst["v"]), n(worst["pv"]),
                                                                   (" on %s" % worst["domain"]) if worst["domain"] else ""),
                     "impact": "High", "effort": "Low", "metric": "%s leads vs %s" % (_sn(worst["v"] - worst["pv"]), cmp_)})
    if low_cov["cov"] < 60:
        recs.append({"label": "This week", "title": "Fix UTM tagging for *%s*" % low_cov["name"],
                     "body": "Only %s of its leads arrived with source, medium and campaign, so its campaigns can't "
                             "be credited. Run the UTM hygiene audit for them." % pct(low_cov["cov"]),
                     "impact": "Medium", "effort": "Low"})
    if best:
        recs.append({"label": "This month", "title": "Pitch more work to *%s*" % best["name"],
                     "body": "Leads grew %s to %s. A growing account is the easiest one to expand." % (
                         _signed(best["g"])[1:], n(best["v"])), "impact": "High", "effort": "Medium"})
    if share(top_c["v"], total) >= 40 and len(clients) >= 3:
        recs.append({"label": "This quarter", "title": "Lower the portfolio's reliance on *%s*" % top_c["name"],
                     "body": "It sends %s of all leads. Grow two smaller accounts so one client's dip can't sink "
                             "the month." % pct(share(top_c["v"], total)), "impact": "Medium", "effort": "High"})
    if len(recs) < 2:
        recs.append({"label": "This month", "title": "Send *%s* its monthly review" % top_c["name"],
                     "body": "It is your biggest client with %s. A per-client review keeps the account close." % (
                         _pl(top_c["v"], "lead")), "impact": "Medium", "effort": "Low"})
    if len(recs) < 2:
        recs.append({"label": "Next period", "title": "Add each client's *earlier period*",
                     "body": "With last period's leads, this rollup shows who is growing and who is slipping.",
                     "impact": "Low", "effort": "Low"})
    secs.append({"type": "section-header", "number": "%02d" % (sum(1 for x in secs if x["type"] == "section-header") + 1),
                 "kicker": "Next steps", "title": "Who to *call* first."})
    secs.append({"type": "recommendations", "items": recs[:4]})
    secs.append({"type": "notes", "title": "How we built this report", "items": [
        "Each client's leads come from its own UTM Grabber site, %s." % period,
        ("Change compares each client with %s; a client counts as up or down when it moved by 5 leads and 10%% or more." % cmp_)
        if with_prior else "No earlier period was supplied, so the rollup shows this period only.",
        "Avg. tagging is the plain average of the clients' fully tagged shares."]})
    if worst:
        ctitle = "Next: call *%s*. Its leads fell %s this period." % (worst["name"], _signed(worst["g"])[1:])
    elif low_cov["cov"] < 60:
        ctitle = "Next: fix tagging for *%s*. Only %s of its leads are tagged." % (low_cov["name"], pct(low_cov["cov"]))
    elif best:
        ctitle = "Next: pitch more work to *%s*. Its leads grew %s." % (best["name"], _signed(best["g"])[1:])
    else:
        ctitle = "Next: send *%s* its review. It brings %s of portfolio leads." % (top_c["name"], pct(share(top_c["v"], total)))
    secs.append({"type": "closing", "kicker": "The book in one line", "title": ctitle,
                 "summary_stats": [{"value": n(len(clients)), "label": "Clients"},
                                   {"value": n(total), "label": "Portfolio leads"},
                                   {"value": "%d up, %d down" % (len(up), len(down)) if with_prior else "–",
                                    "label": "vs %s" % cmp_},
                                   {"value": pct(avg_cov), "label": "Avg. tagging"}],
                 "bullets": [x for x in [
                     "%s leads the book with %s." % (top_c["name"], _pl(top_c["v"], "lead")),
                     ("%s slipped from %s to %s." % (worst["name"], n(worst["pv"]), n(worst["v"]))) if worst else None,
                     "Lowest tagging: %s at %s." % (low_cov["name"], pct(low_cov["cov"]))] if x]})
    return {"meta": m, "sections": secs}


REGISTRY.update({
    "weekly": build_weekly, "weekly-summary": build_weekly, "weekly-executive-summary": build_weekly,
    "leaderboard": build_leaderboard, "campaigns": build_leaderboard, "campaign-leaderboard": build_leaderboard,
    "top-campaign-leaderboard": build_leaderboard,
    "campaign-deep-dive": build_campaign_deep_dive, "campaign": build_campaign_deep_dive,
    "deep-dive": build_campaign_deep_dive,
    "side-by-side": build_side_by_side, "compare": build_side_by_side, "comparison": build_side_by_side,
    "agency-rollup": build_agency_rollup, "rollup": build_agency_rollup, "portfolio": build_agency_rollup,
})
