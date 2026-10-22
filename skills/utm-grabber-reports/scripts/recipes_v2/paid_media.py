"""
Paid media v2 recipes: ad creatives, keywords, landing pages and the budget
simulator.

Same pattern as core.py:
  1. Guard empty input -> common.empty_report(). Fewer than 10 leads to work with
     -> a short, honest version that says why.
  2. Compute every number from the inputs (never invent one).
  3. Outcome-first headline with exactly one *accent*.
  4. Sections in reading order; each answers one question.
  5. Recommendations come from thresholds in the data, highest impact first.
  6. The closing title is a concrete next step with the number behind it.

Ad spend is optional everywhere: pass normalized AdRow dicts as ad_rows=
(see connectors.normalize_ad_rows). Without it the reports say spend is not
connected instead of guessing.
"""
import datetime as _dt
import math
import re
from collections import Counter, defaultdict
from statistics import median

from .common import (MINUS, daily_counts, delta, empty_report, entry_dt, get_field, last_touch, lead_campaign,
                     lead_content, lead_platform, lead_source_medium, lead_term, meta, money, n, norm_key, pct,
                     period_label, period_name, pretty, prior_name, share, source_label, span, stat)
from connectors import normalize_ad_rows  # noqa: E402  (common puts scripts/ on sys.path)
from helpers import compute_hygiene  # noqa: E402

MIN_LEADS = 10       # below this a report switches to its short, honest version
MAX_ROWS = 12        # table rows (keywords allow 15)

# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------
_BAD = {"None": "none", "NaN": "n/a", "null": "empty", "undefined": "not set"}


def _safe(s, limit=None):
    """User data -> display text: no em or en dashes, no stray accents, no literal None."""
    s = re.sub(r"\s+", " ", str(s if s is not None else "")).strip()
    s = re.sub("\\s*[\u2014\u2013]\\s*", " - ", s).replace("*", "")
    s = re.sub(r"\b(None|NaN|null|undefined)\b", lambda mm: _BAD[mm.group(1)], s)
    if limit and len(s) > limit:
        s = s[:limit - 1].rstrip() + "…"
    return s


def _label(raw, limit=40):
    return _safe(pretty(raw), limit)


def _src_name(src):
    """utm_source for prose: 'Google', but domains stay lowercase ('alderbayparents.org')."""
    return _safe(str(src).lower(), 40) if "." in str(src) else source_label(src)


def _md(d):
    return "%s %d" % (d.strftime("%b"), d.day)


def _kick(name, period):
    return "%s · %s" % (name, period) if period else name


def _days(start, end):
    return (end - start).days + 1 if start and end else 0


def _plural(k, word, many=None):
    return "%s %s" % (n(k), word if k == 1 else (many or word + "s"))


def _in_period(start, end):
    """'in September', 'in the last 30 days', 'this week'."""
    if start and end and start == end:
        return "on %s" % _md(start)
    nm = period_name(start, end)
    if nm == "This week":
        return "this week"
    if nm == "This period":
        return "in this period"
    if nm.startswith("The "):
        return "in t" + nm[1:]
    return "in " + nm


def _vs(cmp_label):
    """Short column header for a delta column: 'vs August', 'vs prior 30 days'."""
    c = str(cmp_label or "last period")
    if c.startswith("the previous "):
        return "vs prior " + c[len("the previous "):]
    return "vs " + c


def _setup(current, prior, brand_profile, customer_name, customer_domain, compare_label, prepared_by,
           prepared_for):
    prior = prior or []
    start, end = span(current or [])
    pstart, pend = span(prior) if prior else (None, None)
    m = meta(brand_profile, customer_name, customer_domain,
             compare_label=compare_label or (prior_name(pstart, pend) if prior else "last period"),
             prepared_by=prepared_by, prepared_for=prepared_for)
    return prior, start, end, m


def _weeks(start, end):
    """Full 7-day windows ending on the last day of data, oldest first.
    Leftover days at the start are left out so a partial week never looks like a drop."""
    if not start or not end:
        return []
    k = _days(start, end) // 7
    out = []
    for i in range(k):
        wend = end - _dt.timedelta(days=7 * i)
        out.append((wend - _dt.timedelta(days=6), wend))
    out.reverse()
    return out


def _weekly(entries, weeks):
    counts = [0] * len(weeks)
    if not weeks:
        return counts
    first, last = weeks[0][0], weeks[-1][1]
    for e in entries:
        d = entry_dt(e)
        if not d:
            continue
        d = d.date()
        if first <= d <= last:
            counts[(d - first).days // 7] += 1
    return counts


def _fatigue(wk):
    """(is_fatiguing, reason) from weekly lead counts, oldest first.

    Fatiguing = leads fell three weeks in a row, or the latest week is more than
    40% below the creative's own first week with leads (that week needs 4+ leads)."""
    if len(wk) < 2 or sum(wk) < 4:
        return False, ""
    if len(wk) >= 4 and wk[-4] > wk[-3] > wk[-2] > wk[-1]:
        return True, "weekly leads fell three weeks in a row, from %s to %s" % (n(wk[-4]), n(wk[-1]))
    first_i = next((i for i, v in enumerate(wk) if v > 0), None)
    if first_i is not None and first_i < len(wk) - 1:
        f, last = wk[first_i], wk[-1]
        if f >= 4 and last < 0.6 * f:
            return True, "the latest week brought %s, %s below the first week's %s" % (
                _plural(last, "lead"), pct(100.0 * (f - last) / f), n(f))
    return False, ""


def _delta_cell(cur, prev):
    d = delta(cur, prev)
    if "delta_label" not in d:
        return {"label": "–", "direction": "flat"}
    return {"label": d["delta_label"], "direction": d["delta_direction"]}


def _change_badge(cur, prev):
    """Status pill from the change vs the prior period (min volume before calling a trend)."""
    if prev == 0:
        return {"label": "New", "tone": "brand"} if cur > 0 else {"label": "No leads", "tone": "neutral"}
    if cur + prev < 6:
        return {"label": "Low volume", "tone": "neutral"}
    ch = (cur - prev) / float(prev)
    if ch >= 0.15:
        return {"label": "Rising", "tone": "good"}
    if ch <= -0.5:
        return {"label": "Stalling", "tone": "bad"}
    if ch <= -0.15:
        return {"label": "Cooling", "tone": "warn"}
    return {"label": "Steady", "tone": "neutral"}


def _signed(v):
    v = int(round(v))
    if v > 0:
        return "+" + n(v)
    if v < 0:
        return MINUS + n(abs(v))
    return "0"


def _ad_rows(ad_rows):
    """Normalized AdRow list (normalize_ad_rows is idempotent on already-normalized rows)."""
    if not ad_rows:
        return []
    try:
        return normalize_ad_rows(ad_rows)
    except Exception:
        return []


_PLATFORMS = (("Google Ads", ("google", "googleads", "adwords", "googlecpc", "googlesearch")),
              ("Microsoft Ads", ("bing", "bingads", "microsoft", "microsoftads", "msads")),
              ("Meta Ads", ("facebook", "fb", "instagram", "ig", "meta", "metaads", "facebookads")),
              ("LinkedIn Ads", ("linkedin", "linkedinads")),
              ("TikTok Ads", ("tiktok", "tiktokads")))


def _as_platform(s):
    k = norm_key(s).replace("_", "")
    for name, aliases in _PLATFORMS:
        if k in aliases:
            return name
    return None


def _row_platform(r):
    return _as_platform(r.get("platform")) or _safe(r.get("platform") or "Ads")


def _spend_chips(total_leads, ads):
    chips = [{"name": "UTM Grabber", "detail": "%s leads" % n(total_leads)}]
    by = Counter()
    for r in ads:
        by[_row_platform(r)] += r.get("spend", 0.0)
    for plat, sp in by.most_common():
        if sp > 0:
            chips.append({"name": plat, "detail": "%s spend" % money(sp)})
    return chips


def _ad_dates(ads):
    ds = sorted(r["date"] for r in ads if r.get("date"))
    if not ds:
        return "the ad rows provided"
    try:
        a = _dt.datetime.strptime(ds[0][:10], "%Y-%m-%d").date()
        b = _dt.datetime.strptime(ds[-1][:10], "%Y-%m-%d").date()
        return period_label(a, b)
    except ValueError:
        return "the ad rows provided"


def _short(m, kicker, title, why_title, why_body, stats=None, extra=None, close_title="", close_body=None,
           bits=None):
    """Short, honest report for thin data: what we saw, why it is short, what to do."""
    secs = [{"type": "title-block", "kicker": kicker, "title": title, "meta_bits": [b for b in (bits or []) if b]}]
    if stats and 2 <= len(stats) <= 6:
        secs.append({"type": "stat-strip", "stats": stats})
    secs.extend(extra or [])
    secs.append({"type": "insight-card", "kicker": "Why this report is short", "title": why_title,
                 "body": why_body, "tone": "neutral"})
    close = {"type": "closing", "kicker": "Next step", "title": close_title}
    if close_body:
        close["body"] = close_body
    secs.append(close)
    return {"meta": m, "sections": secs}


def _top_platform(entries):
    c = Counter(lead_platform(e) or "Other" for e in entries)
    return c.most_common(1)[0][0] if c else "Other"


def _fold_groups(points, k=3):
    """Matrix groups: at most k (the k-1 biggest platforms + 'Other platforms')."""
    sizes = Counter()
    for p in points:
        sizes[p["group"]] += p["x"]
    keep = [g for g, _ in sizes.most_common()]
    if len(keep) <= k:
        return points
    keep = set(keep[:k - 1])
    for p in points:
        if p["group"] not in keep:
            p["group"] = "Other platforms"
    return points


# ---------------------------------------------------------------------------
# AD CREATIVE PERFORMANCE
# ---------------------------------------------------------------------------
def _ckey(e):
    return norm_key(lead_content(e))


def _camp_text(counter):
    if not counter:
        return "–"
    top = counter.most_common(1)[0][0]
    more = len(counter) - 1
    return _safe(top, 18) + (" +%d" % more if more else "")


def build_ad_creative(current, prior=None, ad_rows=None, brand_profile=None, customer_name=None,
                      customer_domain="", compare_label=None, prepared_by=None, prepared_for=None, **_):
    """Which ads (utm_content values) bring leads, which are wearing out, what each lead costs."""
    prior, start, end, m = _setup(current, prior, brand_profile, customer_name, customer_domain,
                                  compare_label, prepared_by, prepared_for)
    name = "Ad creative performance"
    if not current:
        return empty_report(name, m)
    period = period_label(start, end)
    kicker = _kick(name, period)
    days = _days(start, end)
    when = _in_period(start, end)
    has_prior = bool(prior)
    vs = _vs(m["compare_label"])
    ads = _ad_rows(ad_rows)
    spend_total = round(sum(r["spend"] for r in ads), 2)
    has_spend = spend_total > 0
    m["sources"] = _spend_chips(len(current), ads)

    paid = [e for e in current if last_touch(e) == "Paid"]
    scope_paid = any(lead_content(e) for e in paid)
    pool = paid if scope_paid else current
    scoped = [e for e in pool if lead_content(e)]
    what = "paid leads" if scope_paid else "leads"
    total = len(scoped)

    if not scoped:
        body = ["UTM Grabber saw %s %s, %s of them from paid ads. Not one carried a utm_content value." % (
            _plural(len(current), "lead"), when, n(len(paid)))]
        if has_spend:
            body.append("Your ad rows show %s of spend that no lead can be tied to an ad." % money(spend_total))
        body.append("Add utm_content with the ad's name to every ad URL. Meta fills it for you with {{ad.name}}.")
        return _short(m, kicker, "Your ads can't be ranked yet: no lead carried *utm_content*.",
                      "Creatives are read from *utm_content*.", body,
                      close_title="Next: add *utm_content* to every ad, then run this again.",
                      bits=[customer_domain, _plural(len(current), "lead"), "%d days" % days if days else ""])

    groups = defaultdict(list)
    for e in scoped:
        groups[_ckey(e)].append(e)
    raw = {k: Counter(lead_content(e).strip() for e in v).most_common(1)[0][0] for k, v in groups.items()}
    order = sorted(groups, key=lambda k: (-len(groups[k]), raw[k].lower()))

    if total < MIN_LEADS:
        rows = [{"rank": str(i + 1), "name": _label(raw[k]), "tag": _safe(raw[k], 32),
                 "leads": {"value": len(groups[k]), "label": n(len(groups[k]))}} for i, k in enumerate(order[:MAX_ROWS])]
        table = {"type": "ranked-list", "title": "Creatives seen so *far*",
                 "columns": [{"key": "rank", "label": "#", "type": "rank"},
                             {"key": "name", "label": "Creative", "type": "name"},
                             {"key": "tag", "label": "utm_content", "type": "source"},
                             {"key": "leads", "label": "Leads", "type": "bar"}], "rows": rows}
        return _short(m, kicker, "Only %s carried a creative tag, too few to rank *ads*." % _plural(total, "lead"),
                      "Rankings need at least %d *leads*." % MIN_LEADS,
                      ["With %s, one extra lead can flip the order, so we list the creatives without judging them." %
                       _plural(total, "lead"),
                       "Let more paid traffic arrive, or widen the date range, and run this again."],
                      stats=[stat("Creative leads", n(total)), stat("Creatives seen", n(len(groups)))],
                      extra=[table], close_title="Next: rerun this once you pass *%d leads*. You have %s." % (
                          MIN_LEADS, n(total)),
                      bits=[customer_domain, _plural(total, "creative lead"), "%d days" % days if days else ""])

    # prior period, same scope
    pool_p = [e for e in prior if last_touch(e) == "Paid"] if scope_paid else prior
    scoped_p = [e for e in pool_p if lead_content(e)]
    prior_c = Counter(_ckey(e) for e in scoped_p)

    # weekly shape and fatigue
    weeks = _weeks(start, end)
    has_weeks = len(weeks) >= 2
    wk = {k: _weekly(groups[k], weeks) for k in groups}

    # spend matched by ad name == utm_content (case and punctuation ignored)
    ad_spend, ad_raw, ad_camp = Counter(), {}, defaultdict(Counter)
    for r in ads:
        if r.get("ad") and r["spend"] > 0:
            k = norm_key(r["ad"])
            ad_spend[k] += r["spend"]
            ad_raw.setdefault(k, r["ad"])
            if r.get("campaign"):
                ad_camp[k][r["campaign"]] += r["spend"]
    creative_spend = has_spend and any(k in ad_spend for k in groups)
    ad_names = {}
    for r in ads:
        if r.get("ad"):
            ad_names.setdefault(norm_key(r["ad"]), r["ad"])

    def cname(k):
        return _safe(ad_names[k], 40) if k in ad_names else _label(raw.get(k) or ad_raw.get(k, k))

    items = []
    for k in order:
        v = groups[k]
        c, p = len(v), prior_c.get(k, 0)
        fat, why = _fatigue(wk[k]) if has_weeks else (False, "")
        sp = ad_spend.get(k, 0.0) if creative_spend else None
        if fat:
            status = {"label": "Fatiguing", "tone": "warn"}
        elif has_prior:
            status = _change_badge(c, p)
        else:
            w = wk[k]
            fi = next((i for i, x in enumerate(w) if x > 0), None)
            status = {"label": "Steady", "tone": "neutral"}
            if fi is not None and fi < len(w) - 1 and w[fi] >= 3 and w[-1] >= 1.25 * w[fi]:
                status = {"label": "Rising", "tone": "good"}
        camps = Counter(lead_campaign(e).strip() for e in v if lead_campaign(e))
        fi = next((i for i, x in enumerate(wk[k]) if x > 0), None)
        items.append({"key": k, "name": cname(k), "leads": c, "prior": p, "fat": fat, "why": why,
                      "status": status, "camp": _camp_text(camps), "plat": _top_platform(v), "spend": sp,
                      "cpl": (sp / c) if sp else None, "wk": wk[k],
                      "drop": (wk[k][fi] - wk[k][-1]) if fi is not None and wk[k] else 0})
    idle = []
    if creative_spend:
        for k, sp in ad_spend.most_common():
            if k not in groups:
                idle.append({"key": k, "name": cname(k), "leads": 0, "prior": prior_c.get(k, 0),
                             "fat": False, "why": "", "status": {"label": "No leads", "tone": "bad"},
                             "camp": _camp_text(ad_camp[k]), "plat": "Other", "spend": sp, "cpl": None,
                             "wk": [0] * len(weeks)})
    # steepest weekly decline first: that is the creative costing the most leads right now
    fatigued = sorted([it for it in items if it["fat"]], key=lambda it: (-it["drop"], -it["leads"]))
    top = items[0]
    top_share = share(top["leads"], total)
    tagged_cov = share(total, len(pool)) if pool else 0.0
    tagged_cov_p = share(len(scoped_p), len(pool_p)) if pool_p else None
    paid_total = len(paid)
    cpl_all = (spend_total / paid_total) if has_spend and paid_total else None
    _, daily = daily_counts(scoped, start, end)

    # ---- title
    if top["fat"]:
        headline = "*%s* still leads with %s %s, but it is wearing out." % (top["name"], n(top["leads"]), what)
    else:
        headline = "*%s* brought %s %s, %s of the total." % (top["name"], n(top["leads"]), what, pct(top_share))
    sub = ["%s brought %s %s %s." % (_plural(len(items), "creative"), n(total), what, when)]
    if fatigued:
        f = fatigued[0]
        sub.append("%s %s fatiguing. For %s, %s." % (n(len(fatigued)), "is" if len(fatigued) == 1 else "are",
                                                      f["name"], f["why"]))
    elif has_spend and cpl_all:
        sub.append("Ads spent %s, %s per paid lead." % (money(spend_total), money(cpl_all)))
    elif has_weeks:
        sub.append("No creative shows fatigue yet.")
    secs = [{"type": "title-block", "kicker": kicker, "title": headline, "subtitle": " ".join(sub),
             "meta_bits": [b for b in [customer_domain, "%s %s" % (n(total), what), _plural(len(items), "creative"),
                                       "%d days" % days if days else ""] if b]}]

    stats = [stat("Creative leads", n(total), total, len(scoped_p) if has_prior else None, spark=daily)]
    if has_spend:
        plats = sorted({_row_platform(r) for r in ads if r["spend"] > 0})
        stats.append(stat("Ad spend", money(spend_total),
                          note=plats[0] if len(plats) == 1 else "%s platforms" % n(len(plats))))
        if cpl_all:
            stats.append(stat("Cost per lead", money(cpl_all), good="down", note="spend / paid leads"))
    else:
        stats.append(stat("Creatives with leads", n(len(items)), len(items), len(prior_c) if has_prior else None))
    if has_weeks:
        stats.append(stat("Fatiguing", n(len(fatigued)), good="down", note="of %s" % _plural(len(items), "creative")))
    if scope_paid:
        stats.append(stat("Paid leads tagged", pct(tagged_cov), tagged_cov, tagged_cov_p if has_prior else None,
                          kind="pts", note="carry utm_content"))
    secs.append({"type": "stat-strip", "stats": stats[:5]})

    # ---- takeaway
    if fatigued and fatigued[0] in items[:3]:
        f = fatigued[0]
        rank = items.index(f) + 1
        secs.append({"type": "insight-card", "kicker": "The takeaway", "tone": "warn",
                     "title": "*%s* is wearing out." % f["name"],
                     "body": ["It is your number %d creative with %s leads, and %s." % (rank, n(f["leads"]), f["why"]),
                              "Rotate in a fresh hook or offer before it drags the campaign down."]})
    else:
        body = []
        if len(items) > 1:
            nxt = items[1:3]
            body.append("%s followed with %s." % (" and ".join(x["name"] for x in nxt),
                                                  " and ".join(n(x["leads"]) for x in nxt)))
        if top_share >= 50 and len(items) > 1:
            body.append("One creative carries most of the volume. Test a challenger while it still wins.")
        elif fatigued:
            body.append("%s is fatiguing, but it is not one of your top three." % fatigued[0]["name"])
        else:
            body.append("No creative shows fatigue yet." if has_weeks else
                        "This period is shorter than two full weeks, so fatigue is not measured.")
        secs.append({"type": "insight-card", "kicker": "The takeaway",
                     "title": "*%s* brought %s of your creative leads." % (top["name"], pct(top_share)),
                     "body": body})

    # ---- 01 leaderboard
    secs.append({"type": "section-header", "number": "01", "kicker": "Leaderboard",
                 "title": "Which *creatives* brought leads.",
                 "dek": "utm_content on %s, ranked by leads.%s" % (
                     what, " Weekly lines cover the last %s." % _plural(len(weeks), "full week") if has_weeks else "")})
    cols = [{"key": "rank", "label": "#", "type": "rank"},
            {"key": "name", "label": "Creative", "type": "name"},
            {"key": "camp", "label": "Campaign", "type": "source"},
            {"key": "leads", "label": "Leads", "type": "bar"}]
    if creative_spend:
        cols.append({"key": "cpl", "label": "Cost per lead", "type": "money", "align": "right"})
    else:
        cols.append({"key": "share", "label": "Share", "type": "pct", "align": "right"})
    if has_prior:
        cols.append({"key": "change", "label": vs, "type": "delta", "align": "right"})
    if has_weeks:
        cols.append({"key": "weekly", "label": "Weekly", "type": "spark"})
    cols.append({"key": "status", "label": "Status", "type": "badge"})
    room = MAX_ROWS - min(3, len(idle))
    must = [it for it in fatigued[:2] if items.index(it) >= room]
    shown = items[:room - len(must)] + must + idle[:3]
    rows = []
    for it in shown:
        rank = items.index(it) + 1 if it in items else len(items) + idle.index(it) + 1
        row = {"rank": str(rank), "name": it["name"], "camp": it["camp"],
               "leads": {"value": it["leads"], "label": n(it["leads"])},
               "share": pct(share(it["leads"], total)),
               "cpl": money(it["cpl"]) if it["cpl"] else ("%s, no leads" % money(it["spend"]) if it["spend"] else "–"),
               "change": _delta_cell(it["leads"], it["prior"]) if has_prior else {"label": "–", "direction": "flat"},
               "weekly": it["wk"], "status": it["status"]}
        if rank == 1:
            row["_highlight"] = True
        if it["leads"] == 0:
            row["_muted"] = True
        rows.append(row)
    cap = "%s of %s %s carried utm_content." % (n(total), n(len(pool)), "paid leads" if scope_paid else "leads")
    if must:
        cap += " Fatiguing creatives outside the top %d are shown with their real rank." % (room - len(must))
    if creative_spend:
        cap += " Cost per lead uses spend from ads whose name matches the utm_content value."
    secs.append({"type": "ranked-list", "title": "Leads by *creative*", "columns": cols, "rows": rows,
                 "caption": cap})

    # ---- 02 fatigue watch
    if has_weeks:
        secs.append({"type": "section-header", "number": "02", "kicker": "Fatigue watch",
                     "title": "How each *creative* held up week to week.",
                     "dek": "Leads per full week, oldest on the left."})
        show_w = weeks[-8:]
        top4 = items[:4]
        if fatigued and fatigued[0] not in top4:
            top4 = items[:3] + [fatigued[0]]
        if fatigued:
            f = fatigued[0]
            ins_title = "*%s* is fatiguing." % f["name"]
            ins_body = ["%s." % (f["why"][0].upper() + f["why"][1:])]
            if len(fatigued) > 1:
                ins_body.append("Also fatiguing: %s." % ", ".join(x["name"] for x in fatigued[1:4]))
        else:
            ins_title = "No creative shows *fatigue* yet."
            ins_body = ["Every creative kept at least 60% of its first-week pace and none fell three weeks running."]
        best_w = max(top4, key=lambda x: x["wk"][-1])
        ins_body.append("Latest week: %s led with %s." % (best_w["name"], _plural(best_w["wk"][-1], "lead")))
        secs.append({"type": "chart-insight",
                     "chart": {"type": "bar-grouped", "labels": [_md(a) for a, _ in show_w],
                               "groups": [{"label": x["name"], "values": x["wk"][-len(show_w):]} for x in top4]},
                     "caption": "Leads per week for the top %s creatives%s. Each week starts on the date shown." % (
                         3 if fatigued and fatigued[0] is top4[-1] and len(items) > 3 else len(top4),
                         " and %s" % fatigued[0]["name"] if fatigued and fatigued[0] is top4[-1] and len(items) > 3 else ""),
                     "insight_kicker": "Fatigue check", "insight_title": ins_title, "insight_body": ins_body})

        # matrix: volume vs growth
        pts = []
        for it in items:
            if it["leads"] < 3:
                continue
            if has_prior:
                if it["prior"] <= 0:
                    continue
                g = 100.0 * (it["leads"] - it["prior"]) / it["prior"]
            else:
                w = it["wk"]
                fi = next((i for i, x in enumerate(w) if x > 0), None)
                if fi is None or fi >= len(w) - 1:
                    continue
                g = 100.0 * (w[-1] - w[fi]) / w[fi]
            pts.append({"label": it["name"], "x": it["leads"], "y": round(g), "size": it["leads"],
                        "group": it["plat"], "_fat": it["fat"]})
        if len(pts) >= 3:
            pts = _fold_groups(pts)
            xr = median([p["x"] for p in pts])
            scale = [p for p in pts if p["x"] >= xr and p["y"] > 0 and not p["_fat"]]
            refresh = [p for p in pts if p["x"] >= xr and (p["y"] < 0 or p["_fat"])]
            if scale:
                b = max(scale, key=lambda p: p["x"])
                mt = "*%s* is big and still growing." % b["label"]
                mb = ["%s leads, %s%s%% %s." % (n(b["x"]), "+" if b["y"] > 0 else "", n(b["y"]),
                                                 vs if has_prior else "since its first week"),
                      "Give it budget before testing anything new."]
            else:
                mt = "Your biggest creatives are losing *momentum*."
                mb = ["Every creative above the median volume is shrinking or fatiguing.",
                      "Refresh the biggest one first; it has the most leads to lose."]
            if refresh and scale:
                r0 = max(refresh, key=lambda p: p["x"])
                mb.append("%s is big but %s. Refresh it next." % (
                    r0["label"], "fatiguing" if r0["_fat"] else "shrinking (%s%%)" % n(r0["y"])))
            for p in pts:
                p.pop("_fat", None)
            secs.append({"type": "matrix", "chart_title": "Creatives: volume vs *growth*", "points": pts,
                         "x_label": "Leads", "y_label": "Change vs prior" if has_prior else "Change since first week",
                         "y_unit": "%", "x_ref": xr, "y_ref": 0,
                         "quadrants": {"tl": "Test more", "tr": "Scale", "bl": "Cut or rework", "br": "Refresh"},
                         "insight_kicker": "Read the map", "insight_title": mt, "insight_body": mb})

    # ---- 03 next steps
    recs = []
    for f in fatigued[:1]:
        recs.append({"label": "This week", "title": "Rotate fresh creative into *%s*" % f["name"],
                     "body": "%s. Swap the hook or the offer and keep the landing page the same." % (
                         f["why"][0].upper() + f["why"][1:]),
                     "impact": "High" if f in items[:3] else "Medium", "effort": "Medium"})
    if idle:
        z = idle[0]
        tail = ""
        cheap = [it for it in items if it["cpl"]]
        if cheap:
            w = min(cheap, key=lambda x: x["cpl"])
            tail = " Move the budget to %s, which brings leads at %s." % (w["name"], money(w["cpl"]))
        recs.append({"label": "This week", "title": "Pause *%s*" % z["name"],
                     "body": "It spent %s with no leads.%s" % (money(z["spend"]), tail),
                     "impact": "High", "effort": "Low", "metric": "%s back to work" % money(z["spend"])})
    healthy = [it for it in items if not it["fat"]]
    winner = w = None
    if healthy:
        if creative_spend and any(it["cpl"] and it["leads"] >= 5 for it in healthy):
            w = min([it for it in healthy if it["cpl"] and it["leads"] >= 5], key=lambda x: x["cpl"])
            why = "It brings leads at %s, the lowest cost of any creative with 5 or more leads." % money(w["cpl"])
        else:
            def growth(it):
                if has_prior:
                    return (it["leads"] - it["prior"]) / float(it["prior"]) if it["prior"] else (1.0 if it["leads"] else 0.0)
                fi = next((i for i, x in enumerate(it["wk"]) if x > 0), None)
                return ((it["wk"][-1] - it["wk"][fi]) / float(it["wk"][fi])) if fi is not None and fi < len(it["wk"]) - 1 else 0.0
            grow = [it for it in healthy if it["leads"] >= 5 and growth(it) > 0.05]
            w = max(grow, key=lambda x: x["leads"]) if grow else None
            if w:
                why = "It brought %s, %s of creative leads, %s." % (
                    _plural(w["leads"], "lead"), pct(share(w["leads"], total)),
                    ("up %s %s" % (pct(100 * growth(w)), vs) if w["prior"] else "new this period") if has_prior else
                    "and its weekly leads are rising")
        if w:
            winner = w
            recs.append({"label": "This month", "title": "Give *%s* more budget" % w["name"], "body": why,
                         "impact": "High", "effort": "Low"})
        else:
            recs.append({"label": "This month", "title": "Brief *new creative* now",
                         "body": "No creative with 5 or more leads is growing%s. A fresh concept is the lever, "
                                 "not more budget behind the current ads." % ((" " + vs) if has_prior else ""),
                         "impact": "High", "effort": "Medium"})
    # the weakest creative with real volume: slowest growth vs prior, or the priciest leads
    pool_w = [it for it in items if it["leads"] >= 5 and not it["fat"] and it is not winner]
    if len(items) >= 3 and pool_w:
        if has_prior and all(it["prior"] for it in pool_w):
            wk_ = min(pool_w, key=lambda x: (x["leads"] - x["prior"]) / float(x["prior"]))
            g = 100.0 * (wk_["leads"] - wk_["prior"]) / wk_["prior"]
            best_g = max(100.0 * (x["leads"] - x["prior"]) / x["prior"] for x in items if x["prior"])
            if best_g - g >= 15:
                recs.append({"label": "This month", "title": "Rework *%s*" % wk_["name"],
                             "body": "It moved %s%s%% %s, the slowest of your creatives (the best grew %s%s%%). "
                                     "Test a new hook against it." % ("+" if g > 0 else MINUS, n(abs(round(g))), vs,
                                                                      "+" if best_g > 0 else MINUS, n(abs(round(best_g)))),
                             "impact": "Medium", "effort": "Medium"})
        elif creative_spend and any(it["cpl"] for it in pool_w):
            wk_ = max([it for it in pool_w if it["cpl"]], key=lambda x: x["cpl"])
            if cpl_all and wk_["cpl"] > 1.3 * cpl_all:
                recs.append({"label": "This month", "title": "Cut spend on *%s*" % wk_["name"],
                             "body": "Its leads cost %s each, vs %s across all paid leads." % (money(wk_["cpl"]), money(cpl_all)),
                             "impact": "Medium", "effort": "Low"})
    if scope_paid and tagged_cov < 90:
        miss = len(pool) - total
        recs.append({"label": "This month", "title": "Add *utm_content* to every ad",
                     "body": "%s of %s paid leads had no utm_content, so their creative is unknown. "
                             "Meta fills it with {{ad.name}}; in Google Ads add it to each ad's final URL." % (
                                 n(miss), n(len(pool))),
                     "impact": "Medium", "effort": "Low"})
    if top_share >= 50 and len(items) > 1 and not top["fat"]:
        recs.append({"label": "Next month", "title": "Test a challenger to *%s*" % top["name"],
                     "body": "It carries %s of creative leads. A proven backup protects volume when it tires." % pct(top_share),
                     "impact": "Medium", "effort": "Medium"})
    if len(recs) < 2:
        recs.append({"label": "Ongoing", "title": "Rerun this check every *two weeks*",
                     "body": "Fatigue shows up week by week. A regular check catches a tiring ad before it costs a month.",
                     "impact": "Low", "effort": "Low"})
    sec_n = "03" if has_weeks else "02"
    secs.append({"type": "section-header", "number": sec_n, "kicker": "Next steps", "title": "What to do *next*."})
    secs.append({"type": "recommendations", "items": recs[:4]})

    # ---- notes
    notes = ["Creatives are utm_content values on %s (%s of %s). Case and punctuation are ignored, so Hero_CTA and hero-cta count once." % (
        "paid leads, meaning a paid medium or an ad click ID" if scope_paid else
        "all leads, because no paid lead carried utm_content", n(total), n(len(pool)))]
    if has_weeks:
        notes.append("Weeks are full 7-day windows ending %s. Fatiguing means weekly leads fell three weeks in a row, "
                     "or the latest week is more than 40%% below the creative's first week with leads (4 or more)." % _md(end))
    if has_spend:
        notes.append("Spend: %s from %s. %s" % (money(spend_total), _ad_dates(ads),
                     "Matched to creatives where the ad name equals utm_content." if creative_spend else
                     "No ad name matched a utm_content value, so cost per creative is not shown."))
        if cpl_all:
            notes.append("Cost per lead in the summary divides all ad spend by all %s paid leads." % n(paid_total))
    else:
        notes.append("Ad spend is not connected, so cost per lead is not shown. Connect Google Ads or Meta Ads to add it.")
    if has_prior:
        notes.append("Changes compare %s with %s." % (period, m["compare_label"]))
    secs.append({"type": "notes", "items": notes})

    # ---- closing
    if fatigued:
        f = fatigued[0]
        fi = next((i for i, x in enumerate(f["wk"]) if x > 0), 0)
        close = "Next: refresh *%s*. Its weekly leads are down from %s to %s." % (
            f["name"], n(f["wk"][fi]), n(f["wk"][-1]))
    elif idle:
        close = "Next: pause *%s*. It spent %s without a lead." % (idle[0]["name"], money(idle[0]["spend"]))
    elif winner:
        close = "Next: scale *%s*. It brought %s of creative leads." % (winner["name"], pct(share(winner["leads"], total)))
    else:
        close = "Next: brief *new creative*. No current ad with 5 or more leads is growing."
    summ = [{"value": n(total), "label": "Creative leads"}, {"value": n(len(items)), "label": "Creatives"},
            {"value": pct(top_share), "label": "Top creative share"}]
    summ.append({"value": money(cpl_all), "label": "Cost per lead"} if cpl_all else
                {"value": n(len(fatigued)), "label": "Fatiguing"})
    bullets = ["%s led with %s." % (top["name"], _plural(top["leads"], "lead"))]
    if fatigued:
        more = len(fatigued) - 3
        bullets.append("%s fatiguing: %s%s." % (_plural(len(fatigued), "creative"), ", ".join(x["name"] for x in fatigued[:3]),
                                                (", and %s more" % n(more)) if more > 0 else ""))
    if scope_paid:
        bullets.append("%s of paid leads carried utm_content." % pct(tagged_cov))
    secs.append({"type": "closing", "kicker": "The creatives in one line", "title": close,
                 "summary_stats": summ, "bullets": bullets[:3]})
    return {"meta": m, "sections": secs}


# ---------------------------------------------------------------------------
# KEYWORD PERFORMANCE
# ---------------------------------------------------------------------------
INTENTS = ["Brand", "Competitor", "Problem or urgent", "Generic"]
_INTENT_TONE = {"Brand": "brand", "Competitor": "warn", "Problem or urgent": "good", "Generic": "neutral"}
URGENT_WORDS = ["emergency", "urgent", "near me", "nearby", "open now", "now", "today", "same day", "asap",
                "24/7", "24 hour", "fix", "repair", "broken", "pain", "cost", "costs", "price", "prices",
                "pricing", "how much", "quote", "cheap", "affordable"]


def _norm_text(s):
    s = str(s or "").lower()
    s = re.sub(r"[\[\]\"'+]", " ", s)
    s = re.sub(r"[^a-z0-9/&]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _domain_stem(domain):
    d = re.sub(r"^https?://", "", str(domain or "").lower()).split("/")[0]
    parts = [p for p in d.split(".") if p and p != "www"]
    if len(parts) >= 3 and parts[-2] in ("co", "com", "org", "net", "ac", "gov"):
        return parts[-3]
    if len(parts) >= 2:
        return parts[-2]
    return parts[0] if parts else ""


_COMMON_WORDS = {"dental", "dentist", "dentistry", "family", "smile", "smiles", "clinic", "center", "centre",
                 "health", "medical", "marketing", "digital", "agency", "media", "group", "studio", "studios",
                 "solutions", "services", "consulting", "partners", "company", "global", "national", "american",
                 "first", "best", "city", "north", "south", "east", "west", "united", "home", "homes", "realty",
                 "plumbing", "roofing", "legal", "law", "care", "wellness", "fitness", "design", "labs", "software",
                 "systems", "store", "shop", "goods", "supply", "insurance", "financial", "capital", "auto"}


def _brand_forms(name, domain, extra=None):
    """Brand phrases: the full name with and without spaces, the domain stem, any distinctive word of
    the name (5+ letters, not a common business word), plus brand_terms."""
    forms = []
    nm = _norm_text(name)
    words = tuple(w for w in nm.split() if len(w) >= 5 and w not in _COMMON_WORDS) if len(nm.split()) > 1 else ()
    for f in (nm, nm.replace(" ", ""), _domain_stem(domain)) + words + tuple(_norm_text(x) for x in (extra or [])):
        if len(f) >= 4 and f not in forms:
            forms.append(f)
    return forms


def _has_phrase(text, phrase):
    return re.search(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(phrase), text) is not None


def classify_intent(term, brand_forms, competitors):
    """Transparent intent rules, first match wins: brand, competitor, problem or urgent, generic."""
    t = _norm_text(term)
    flat = t.replace(" ", "")
    if any(f in t or f.replace(" ", "") in flat for f in brand_forms):
        return "Brand"
    if any(c and (_has_phrase(t, c) or c.replace(" ", "") in flat) for c in competitors):
        return "Competitor"
    if any(_has_phrase(t, w) for w in URGENT_WORDS):
        return "Problem or urgent"
    return "Generic"


def _is_paid_search(e):
    plat = lead_platform(e)
    return plat in ("Google Ads", "Microsoft Ads")


def build_keyword(current, prior=None, competitors=None, brand_terms=None, ad_rows=None, brand_profile=None,
                  customer_name=None, customer_domain="", compare_label=None, prepared_by=None, prepared_for=None,
                  **_):
    """Which search terms (utm_term) bring leads, sorted by intent, and where to push or cut."""
    prior, start, end, m = _setup(current, prior, brand_profile, customer_name, customer_domain,
                                  compare_label, prepared_by, prepared_for)
    name = "Keyword performance"
    if not current:
        return empty_report(name, m)
    period = period_label(start, end)
    kicker = _kick(name, period)
    days = _days(start, end)
    when = _in_period(start, end)
    has_prior = bool(prior)
    vs = _vs(m["compare_label"])
    ads = _ad_rows(ad_rows)
    m["sources"] = _spend_chips(len(current), ads)
    comps = [_norm_text(c) for c in (competitors or []) if _norm_text(c)]
    bforms = _brand_forms(m.get("customer_name"), customer_domain, brand_terms)

    def tkey(e):
        return _norm_text(lead_term(e))

    termed = [e for e in current if tkey(e)]
    psearch = [e for e in current if _is_paid_search(e)]
    psearch_missing = [e for e in psearch if not tkey(e)]
    total = len(termed)

    if total == 0:
        body = ["UTM Grabber saw %s %s and none carried a utm_term value." % (_plural(len(current), "lead"), when)]
        if psearch:
            body.append("%s came from paid search, so the keyword was there but never passed to the page." %
                        _plural(len(psearch), "lead"))
        body.append("Add utm_term={keyword} to the tracking template in Google Ads and Microsoft Ads.")
        return _short(m, kicker, "No lead carried a *keyword* yet.", "Keywords are read from *utm_term*.", body,
                      close_title="Next: add *utm_term* to your search ads, then run this again.",
                      bits=[customer_domain, _plural(len(current), "lead"), "%d days" % days if days else ""])

    groups = defaultdict(list)
    for e in termed:
        groups[tkey(e)].append(e)
    raw = {k: Counter(lead_term(e).strip() for e in v).most_common(1)[0][0] for k, v in groups.items()}
    intent = {k: classify_intent(k, bforms, comps) for k in groups}
    order = sorted(groups, key=lambda k: (-len(groups[k]), k))

    if total < MIN_LEADS:
        rows = [{"rank": str(i + 1), "term": _safe(raw[k], 48),
                 "intent": {"label": intent[k], "tone": _INTENT_TONE[intent[k]]},
                 "leads": {"value": len(groups[k]), "label": n(len(groups[k]))}} for i, k in enumerate(order[:15])]
        table = {"type": "ranked-list", "title": "Search terms seen so *far*",
                 "columns": [{"key": "rank", "label": "#", "type": "rank"},
                             {"key": "term", "label": "Keyword", "type": "source"},
                             {"key": "intent", "label": "Intent", "type": "badge"},
                             {"key": "leads", "label": "Leads", "type": "bar"}], "rows": rows}
        return _short(m, kicker, "Only %s carried a keyword, too few to judge *search terms*." % _plural(total, "lead"),
                      "Keyword rankings need at least %d *leads*." % MIN_LEADS,
                      ["With %s, the order can change with one search." % _plural(total, "lead"),
                       "The intent labels are still right: they come from the words in each term."],
                      stats=[stat("Keyword leads", n(total)), stat("Search terms", n(len(groups)))],
                      extra=[table], close_title="Next: rerun this once you pass *%d keyword leads*." % MIN_LEADS,
                      bits=[customer_domain, _plural(total, "keyword lead"), "%d days" % days if days else ""])

    termed_p = [e for e in prior if tkey(e)]
    prior_c = Counter(tkey(e) for e in termed_p)
    by_intent = Counter()
    terms_in = Counter()
    for k, v in groups.items():
        by_intent[intent[k]] += len(v)
        terms_in[intent[k]] += 1
    by_intent_p = Counter()
    for k, c in prior_c.items():
        by_intent_p[classify_intent(k, bforms, comps)] += c
    total_p = len(termed_p)

    # spend per keyword (match types and quotes ignored)
    kw_spend, kw_raw = Counter(), {}
    for r in ads:
        if r.get("keyword") and r["spend"] > 0:
            k = _norm_text(r["keyword"])
            kw_spend[k] += r["spend"]
            kw_raw.setdefault(k, r["keyword"])
    has_kw_spend = bool(kw_spend)
    kw_spend_total = sum(kw_spend.values())
    zero = [(k, sp) for k, sp in kw_spend.most_common() if k not in groups]
    matched = [k for k in groups if k in kw_spend]

    top_k = order[0]
    top_i = max(INTENTS, key=lambda i: (by_intent[i], -INTENTS.index(i)))
    brand_share = share(by_intent["Brand"], total)
    urgent_share = share(by_intent["Problem or urgent"], total)
    _, daily = daily_counts(termed, start, end)

    # ---- title
    ish = share(by_intent[top_i], total)
    if ish >= 99.5:
        headline = "*%s* searches brought all %s keyword leads." % (top_i, n(total))
    else:
        headline = "*%s* searches brought %s of %s keyword leads." % (top_i, pct(ish), n(total))
    sub = "\"%s\" was the top term with %s. %s search terms brought leads %s." % (
        _safe(raw[top_k], 40), _plural(len(groups[top_k]), "lead"), n(len(groups)), when)
    if psearch_missing:
        sub += " %s from paid search had no keyword at all." % _plural(len(psearch_missing), "lead")
    secs = [{"type": "title-block", "kicker": kicker, "title": headline, "subtitle": sub,
             "meta_bits": [b for b in [customer_domain, "%s keyword leads" % n(total), _plural(len(groups), "term"),
                                       "%d days" % days if days else ""] if b]}]
    top_term_share = share(len(groups[top_k]), total)
    stats = [stat("Keyword leads", n(total), total, total_p if has_prior else None, spark=daily),
             stat("Brand share", pct(brand_share), brand_share,
                  share(by_intent_p["Brand"], total_p) if has_prior and total_p else None, kind="pts", good="neutral")]
    if by_intent["Problem or urgent"] or by_intent_p["Problem or urgent"]:
        stats.append(stat("Urgent share", pct(urgent_share), urgent_share,
                          share(by_intent_p["Problem or urgent"], total_p) if has_prior and total_p else None,
                          kind="pts", note="problem or urgent"))
    if has_kw_spend:
        stats.append(stat("Keyword spend", money(kw_spend_total), note="%s per keyword lead" % money(kw_spend_total / total)))
    if psearch:
        stats.append(stat("No keyword", n(len(psearch_missing)), good="down",
                          note="of %s paid search leads" % n(len(psearch))))
    stats.append(stat("Search terms", n(len(groups)), len(groups), len(prior_c) if has_prior else None))
    stats.append(stat("Top term share", pct(top_term_share), note="\"%s\"" % _safe(raw[top_k], 22)))
    secs.append({"type": "stat-strip", "stats": stats[:5]})

    # ---- 01 intent
    secs.append({"type": "section-header", "number": "01", "kicker": "Search intent",
                 "title": "What your searchers *wanted*.",
                 "dek": "Each utm_term sorted by plain rules: brand, competitor, problem or urgent, then generic."})
    mix = sorted(INTENTS, key=lambda i: (-by_intent[i], INTENTS.index(i)))
    notes_row = []
    for i in mix:
        if i == "Competitor" and not comps:
            notes_row.append("no competitor list given")
        else:
            notes_row.append(_plural(terms_in[i], "term"))
    body = []
    if by_intent["Brand"]:
        body.append("Brand searches brought %s (%s): people who already know your name." % (
            pct(brand_share), _plural(by_intent["Brand"], "lead")))
    else:
        body.append("Not one keyword lead searched for your name (%s)." % ", ".join("\"%s\"" % f for f in bforms[:2]))
    if by_intent["Problem or urgent"]:
        body.append("Problem or urgent searches brought %s. These people need help now, so answer them first." %
                    pct(urgent_share))
    if by_intent["Generic"] and top_i != "Generic":
        body.append("Generic terms brought %s from %s." % (pct(share(by_intent["Generic"], total)),
                                                          _plural(terms_in["Generic"], "term")))
    top_in = [k for k in order if intent[k] == top_i][:2]
    if len(top_in) == 2:
        body.append("Within %s, \"%s\" and \"%s\" brought %s of all keyword leads." % (
            top_i.lower(), _safe(raw[top_in[0]], 28), _safe(raw[top_in[1]], 28),
            pct(share(len(groups[top_in[0]]) + len(groups[top_in[1]]), total))))
    secs.append({"type": "chart-insight",
                 "chart": {"type": "bar-horizontal", "labels": mix, "values": [by_intent[i] for i in mix],
                           "x_title": "Keyword leads", "highlight": 0, "notes": notes_row, "total": total},
                 "caption": "Keyword leads by search intent",
                 "insight_kicker": "The mix",
                 "insight_title": "*%s* intent leads with %s." % (top_i, pct(ish)),
                 "insight_body": body[:3]})

    # ---- 02 terms
    secs.append({"type": "section-header", "number": "02", "kicker": "Keywords",
                 "title": "Which *terms* brought leads."})
    cols = [{"key": "rank", "label": "#", "type": "rank"},
            {"key": "term", "label": "Keyword", "type": "source"},
            {"key": "intent", "label": "Intent", "type": "badge"},
            {"key": "leads", "label": "Leads", "type": "bar"},
            {"key": "share", "label": "Share", "type": "pct", "align": "right"}]
    if has_prior:
        cols.append({"key": "change", "label": vs, "type": "delta", "align": "right"})
    if matched:
        cols.append({"key": "cpl", "label": "Cost per lead", "type": "money", "align": "right"})
    rows = []
    for i, k in enumerate(order[:15]):
        c = len(groups[k])
        sp = kw_spend.get(k)
        row = {"rank": str(i + 1), "term": _safe(raw[k], 48),
               "intent": {"label": intent[k], "tone": _INTENT_TONE[intent[k]]},
               "leads": {"value": c, "label": n(c)}, "share": pct(share(c, total)),
               "change": _delta_cell(c, prior_c.get(k, 0)) if has_prior else {"label": "–", "direction": "flat"},
               "cpl": money(sp / c) if sp else "–"}
        if i == 0:
            row["_highlight"] = True
        rows.append(row)
    cap = "%s of %s leads carried a utm_term. Terms are grouped ignoring case, quotes and match-type symbols." % (
        n(total), n(len(current)))
    if len(order) > 15:
        cap = "Top 15 of %s terms. " % n(len(order)) + cap
    secs.append({"type": "ranked-list", "title": "Leads by *keyword*", "columns": cols, "rows": rows, "caption": cap})

    # ---- 03 next steps
    recs = []
    if zero:
        names = ", ".join("\"%s\"" % _safe(kw_raw[k], 30) for k, _ in zero[:3])
        zsp = sum(sp for _, sp in zero)
        recs.append({"label": "This week", "title": "Add %s zero-lead terms as *negatives*" % n(len(zero)),
                     "body": "They spent %s with no leads: %s." % (money(zsp), names),
                     "impact": "High", "effort": "Low", "metric": "%s back to work" % money(zsp)})
    if psearch and share(len(psearch_missing), len(psearch)) >= 10:
        recs.append({"label": "This week", "title": "Pass the keyword in *utm_term*",
                     "body": "%s of %s paid search leads arrived without a keyword. Add utm_term={keyword} to the "
                             "tracking template in Google Ads and Microsoft Ads." % (
                                 n(len(psearch_missing)), n(len(psearch))),
                     "impact": "High", "effort": "Low"})
    growth = []
    for k in order:
        c, p = len(groups[k]), prior_c.get(k, 0)
        if has_prior and c >= 3 and (p == 0 or c >= 1.25 * p):
            growth.append((k, c, p))
    if growth:
        k, c, p = growth[0]
        recs.append({"label": "This month", "title": "Push *\"%s\"* harder" % _safe(raw[k], 36),
                     "body": "It brought %s, %s. Raise its bid and add close variants as phrase match." % (
                         _plural(c, "lead"), "new this period" if p == 0 else "up from %s" % n(p)),
                     "impact": "High", "effort": "Low"})
    elif not has_prior:
        recs.append({"label": "This month", "title": "Push *\"%s\"* harder" % _safe(raw[top_k], 36),
                     "body": "It is your top term with %s (%s). Raise its bid and add close variants as phrase match." % (
                         _plural(len(groups[top_k]), "lead"), pct(share(len(groups[top_k]), total))),
                     "impact": "High", "effort": "Low"})
    if brand_share >= 50:
        recs.append({"label": "This month", "title": "Grow *non-brand* search",
                     "body": "Brand terms brought %s of keyword leads. Those people already know you; "
                             "generic and problem terms find new demand." % pct(brand_share),
                     "impact": "Medium", "effort": "Medium"})
    if by_intent["Problem or urgent"] and urgent_share < 50:
        recs.append({"label": "Ongoing", "title": "Answer *urgent* searchers first",
                     "body": "%s used words like emergency, near me, now or price. Route them to your fastest follow-up." %
                             _plural(by_intent["Problem or urgent"], "lead"),
                     "impact": "Medium", "effort": "Low"})
    if not by_intent["Brand"] and psearch and bforms:
        recs.append({"label": "This month", "title": "Check that brand search is *tagged*",
                     "body": "Not one keyword lead searched for \"%s\". If you bid on your name, those ads are missing "
                             "utm_term; if you don't, brand searchers only find you organically." % bforms[0],
                     "impact": "Medium", "effort": "Low"})
    if len(recs) < 2:
        recs.append({"label": "Ongoing", "title": "Review search terms every *month*",
                     "body": "New terms appear as people search differently. A monthly look keeps winners funded.",
                     "impact": "Low", "effort": "Low"})
    secs.append({"type": "section-header", "number": "03", "kicker": "Next steps", "title": "What to do *next*."})
    secs.append({"type": "recommendations", "items": recs[:4]})

    notes = ["Brand: the term contains %s." % (" or ".join("\"%s\"" % f for f in bforms) if bforms else
                                                 "your brand name (none was available)"),
             "Competitor: the term contains a name from your list (%s)." % ", ".join(comps) if comps else
             "Competitor: no competitor list was given, so no term is marked competitor.",
             "Problem or urgent: the term contains %s." % ", ".join(URGENT_WORDS),
             "Generic: everything else. Rules apply in this order and the first match wins."]
    if has_kw_spend:
        notes.append("Spend: %s across %s from %s; %s with leads matched by keyword text." % (
            money(kw_spend_total), _plural(len(kw_spend), "keyword"), _ad_dates(ads), n(len(matched))))
    else:
        notes.append("Ad spend is not connected, so negatives are not suggested. Connect Google Ads to find terms "
                     "that spend without leads.")
    if has_prior:
        notes.append("Changes compare %s with %s." % (period, m["compare_label"]))
    secs.append({"type": "notes", "items": notes})

    if zero:
        close = "Next: add %s *negatives*. They spent %s with no leads." % (n(len(zero)), money(sum(sp for _, sp in zero)))
    elif psearch and share(len(psearch_missing), len(psearch)) >= 10:
        close = "Next: add utm_term to your *search ads*. %s paid search leads had no keyword." % n(len(psearch_missing))
    else:
        g = growth[0] if growth else (top_k, len(groups[top_k]), 0)
        close = "Next: push *\"%s\"*. It brought %s." % (_safe(raw[g[0]], 36), _plural(g[1], "lead"))
    secs.append({"type": "closing", "kicker": "The terms in one line", "title": close,
                 "summary_stats": [{"value": n(total), "label": "Keyword leads"},
                                   {"value": n(len(groups)), "label": "Search terms"},
                                   {"value": pct(brand_share), "label": "Brand share"},
                                   {"value": pct(urgent_share), "label": "Problem or urgent"}],
                 "bullets": ["\"%s\" led with %s." % (_safe(raw[top_k], 40), _plural(len(groups[top_k]), "lead")),
                             "%s intent brought %s of keyword leads." % (top_i, pct(ish))] +
                            (["%s paid search leads had no keyword." % n(len(psearch_missing))] if psearch_missing else [])})
    return {"meta": m, "sections": secs}


# ---------------------------------------------------------------------------
# LANDING PAGE PERFORMANCE
# ---------------------------------------------------------------------------
def page_path(url):
    """'https://site.com/pricing/?ref=x#top' -> '/pricing'. Paths keep their own case rules lowercased."""
    u = str(url or "").strip()
    if not u:
        return ""
    u = re.sub(r"^[a-z][a-z0-9+.-]*://[^/?#]*", "", u, flags=re.I)
    u = u.split("?")[0].split("#")[0].strip()
    if not u or u == "/":
        return "/"
    if not u.startswith("/"):
        u = "/" + u
    return u.rstrip("/").lower() or "/"


def landing_of(e):
    """(path, basis) using first-touch landing page, then the converting visit's landing page, then the form page."""
    for key, basis in (("landing_page (first touch, HandL)", "first"), ("handl_landing_page (HandL)", "landing"),
                       ("Source URL", "form")):
        v = get_field(e, key)
        if v:
            return page_path(v), basis
    v = get_field(e, "source_url", "landing_page")
    return (page_path(v), "form") if v else ("", "")


def _page_name(p):
    return "your homepage" if p == "/" else p


def _src_of(e):
    s = lead_source_medium(e)[0]
    return _src_name(s) if s else last_touch(e)


def _click_platform(e):
    if get_field(e, "gclid (HandL)", "gclid", "wbraid (HandL)", "gbraid (HandL)"):
        return "Google Ads"
    if get_field(e, "msclkid (HandL)", "msclkid"):
        return "Microsoft Ads"
    if get_field(e, "fbclid (HandL)", "fbclid"):
        return "Meta Ads"
    return None


def _short_path(p, limit=24):
    """Fit a path into a chart label: keep the start and the last segment."""
    p = _safe(p)
    if len(p) <= limit:
        return p
    last = p.rsplit("/", 1)[-1]
    if len(last) + 4 <= limit:
        head = p[:limit - len(last) - 2].rstrip("/")
        return head + "…/" + last
    return p[:limit - 1] + "…"


def _untagged(e):
    """No utm_source, utm_medium or utm_campaign at all."""
    return compute_hygiene(e) in ("untagged_paid", "untagged_referrer", "direct")


def build_landing_page(current, prior=None, brand_profile=None, customer_name=None, customer_domain="",
                       compare_label=None, prepared_by=None, prepared_for=None, **_):
    """Which pages bring leads, from where, and which ones lose attribution on the way in."""
    prior, start, end, m = _setup(current, prior, brand_profile, customer_name, customer_domain,
                                  compare_label, prepared_by, prepared_for)
    name = "Landing page performance"
    if not current:
        return empty_report(name, m)
    period = period_label(start, end)
    kicker = _kick(name, period)
    days = _days(start, end)
    when = _in_period(start, end)
    has_prior = bool(prior)
    vs = _vs(m["compare_label"])
    m["sources"] = [{"name": "UTM Grabber", "detail": "%s leads" % n(len(current))}]

    groups = defaultdict(list)
    basis = Counter()
    for e in current:
        p, b = landing_of(e)
        if p:
            groups[p].append(e)
            basis[b] += 1
    paged = sum(len(v) for v in groups.values())
    if not groups:
        return _short(m, kicker, "No lead recorded a *landing page* yet.", "Pages come from the *page URL* fields.",
                      ["UTM Grabber saw %s %s, but none carried a landing page or form page URL." % (
                          _plural(len(current), "lead"), when),
                       "Check that the form sends its page URL (Source URL) with each entry."],
                      close_title="Next: check the *page URL* field on your forms.",
                      bits=[customer_domain, _plural(len(current), "lead")])
    order = sorted(groups, key=lambda p: (-len(groups[p]), p))
    if paged < MIN_LEADS:
        rows = [{"rank": str(i + 1), "page": _safe(p, 60), "leads": {"value": len(groups[p]), "label": n(len(groups[p]))}}
                for i, p in enumerate(order[:MAX_ROWS])]
        table = {"type": "ranked-list", "title": "Pages seen so *far*",
                 "columns": [{"key": "rank", "label": "#", "type": "rank"},
                             {"key": "page", "label": "Page", "type": "source"},
                             {"key": "leads", "label": "Leads", "type": "bar"}], "rows": rows}
        return _short(m, kicker, "Only %s so far, too few to rank *pages*." % _plural(paged, "lead"),
                      "Page rankings need at least %d *leads*." % MIN_LEADS,
                      ["With %s, one lead moves a page up or down the list." % _plural(paged, "lead"),
                       "Run this again once more leads arrive."],
                      stats=[stat("Leads", n(paged)), stat("Pages", n(len(groups)))], extra=[table],
                      close_title="Next: rerun this once you pass *%d leads*." % MIN_LEADS,
                      bits=[customer_domain, _plural(paged, "lead"), "%d days" % days if days else ""])

    prior_c = Counter(landing_of(e)[0] for e in prior if landing_of(e)[0])
    info = {}
    for p, v in groups.items():
        srcs = Counter(_src_of(e) for e in v)
        ts, tn = srcs.most_common(1)[0]
        untagged = [e for e in v if _untagged(e)]
        lost = [e for e in untagged if _click_platform(e)]
        info[p] = {"leads": len(v), "tagged": share(len(v) - len(untagged), len(v)), "untagged": len(untagged),
                   "lost": len(lost),
                   "lost_plat": Counter(_click_platform(e) for e in lost).most_common(1)[0][0] if lost else None,
                   "top_src": ts, "top_src_share": share(tn, len(v)), "prior": prior_c.get(p, 0)}
    total = paged
    top = order[0]
    ti = info[top]
    top_share = share(ti["leads"], total)
    top3 = share(sum(info[p]["leads"] for p in order[:3]), total)
    tag_all = share(sum(1 for e in current if not _untagged(e)), len(current))
    tag_all_p = share(sum(1 for e in prior if not _untagged(e)), len(prior)) if prior else None
    top_name = "Your homepage" if top == "/" else top

    def status(i):
        us = share(i["untagged"], i["leads"])
        if us >= 30:
            return "fail"
        if us >= 10 or i["lost"]:
            return "warn"
        return "pass"

    leakers = sorted([p for p in order if status(info[p]) != "pass" and (info[p]["untagged"] >= 2 or info[p]["lost"])],
                     key=lambda p: (status(info[p]) != "fail", -info[p]["lost"], -info[p]["untagged"], p))
    failing = [p for p in leakers if status(info[p]) == "fail"]
    lost_total = sum(i["lost"] for i in info.values())
    lost_plats = Counter()
    for p, v in groups.items():
        for e in v:
            if _untagged(e) and _click_platform(e):
                lost_plats[_click_platform(e)] += 1
    focus = (max([p for p in order if info[p]["lost"]], key=lambda p: (info[p]["lost"], info[p]["untagged"]))
             if lost_total else (failing[0] if failing else None))

    # ---- title
    if top == "/":
        headline = "Your *homepage* brought %s, %s of the total." % (_plural(ti["leads"], "lead"), pct(top_share))
    else:
        headline = "*%s* brought %s, %s of the total." % (_safe(top, 40), _plural(ti["leads"], "lead"), pct(top_share))
    sub = "%s pages brought leads %s; the top three carried %s." % (n(len(groups)), when, pct(top3))
    if failing:
        sub += " %s lost attribution on 30%% or more of their leads." % _plural(len(failing), "page")
    elif lost_total:
        sub += " %s from paid ads arrived with no UTMs." % _plural(lost_total, "click")
    else:
        sub += " No page lost attribution on the way in."
    secs = [{"type": "title-block", "kicker": kicker, "title": headline, "subtitle": sub,
             "meta_bits": [b for b in [customer_domain, _plural(total, "lead"), _plural(len(groups), "page"),
                                       "%d days" % days if days else ""] if b]}]
    _, daily = daily_counts(current, start, end)
    secs.append({"type": "stat-strip", "stats": [
        stat("Leads", n(total), total, sum(prior_c.values()) if has_prior else None, spark=daily),
        stat("Pages with leads", n(len(groups)), len(groups), len(prior_c) if has_prior else None),
        stat("Top 3 pages", pct(top3), note="of all leads"),
        stat("Tagged leads", pct(tag_all), tag_all, tag_all_p if has_prior else None, kind="pts",
             note="arrived with UTMs"),
        stat("Paid clicks untagged", n(lost_total), good="down", note="click ID, no UTMs")]})
    tk = ["Its biggest source was %s, with %s of its leads." % (ti["top_src"], pct(ti["top_src_share"]))]
    if len(order) > 1:
        sec = order[1]
        tk.append("Next came %s with %s." % (_page_name(sec), _plural(info[sec]["leads"], "lead")))
    if top3 >= 70:
        tk.append("Three pages carry %s of leads, so their forms matter most." % pct(top3))
    secs.append({"type": "insight-card", "kicker": "The takeaway",
                 "title": ("Your *homepage* leads with %s of all leads." % pct(top_share)) if top == "/" else
                 ("*%s* leads with %s of all leads." % (_safe(top, 40), pct(top_share))),
                 "body": tk})

    # ---- 01 pages
    if basis["first"] >= max(basis["landing"], basis["form"]):
        dek = "Each lead counted once, on the first page it landed on."
    elif basis["landing"] >= basis["form"]:
        dek = "Each lead counted once, on the landing page of the visit that converted."
    else:
        dek = "Each lead counted once, on the page where it filled the form."
    secs.append({"type": "section-header", "number": "01", "kicker": "Top pages",
                 "title": "Where your *leads* land.", "dek": dek})
    top8 = order[:8]
    secs.append({"type": "chart",
                 "chart": {"type": "bar-horizontal", "labels": [_short_path(p) for p in top8],
                           "values": [info[p]["leads"] for p in top8], "x_title": "Leads", "highlight": 0,
                           "notes": ["%s, %s" % (info[p]["top_src"], pct(info[p]["top_src_share"])) for p in top8],
                           "total": total},
                 "chart_title": "Leads per *page*",
                 "caption": "Top %d pages, with each page's biggest source under its name." % len(top8)})
    cols = [{"key": "rank", "label": "#", "type": "rank"},
            {"key": "page", "label": "Page", "type": "source"},
            {"key": "leads", "label": "Leads", "type": "bar"},
            {"key": "share", "label": "Share", "type": "pct", "align": "right"},
            {"key": "src", "label": "Top source", "type": "text"},
            {"key": "tagged", "label": "Tagged", "type": "badge"}]
    if has_prior:
        cols.append({"key": "change", "label": vs, "type": "delta", "align": "right"})
    tone_of = {"pass": "good", "warn": "warn", "fail": "bad"}
    rows = []
    for i, p in enumerate(order[:MAX_ROWS]):
        it = info[p]
        row = {"rank": str(i + 1), "page": _safe(p, 60), "leads": {"value": it["leads"], "label": n(it["leads"])},
               "share": pct(share(it["leads"], total)), "src": "%s, %s" % (it["top_src"], pct(it["top_src_share"])),
               "tagged": {"label": pct(it["tagged"]), "tone": tone_of[status(it)]},
               "change": _delta_cell(it["leads"], it["prior"]) if has_prior else {"label": "–", "direction": "flat"}}
        if i == 0:
            row["_highlight"] = True
        rows.append(row)
    cap = "Tagged: the share of a page's leads that arrived with at least one UTM (source, medium or campaign)."
    if len(order) > MAX_ROWS:
        cap = "Top %d of %s pages. " % (MAX_ROWS, n(len(order))) + cap
    secs.append({"type": "ranked-list", "title": "Leads by *page*", "columns": cols, "rows": rows, "caption": cap})

    # ---- 02 leaks
    secs.append({"type": "section-header", "number": "02", "kicker": "Attribution leaks",
                 "title": "Pages that lose *attribution*.",
                 "dek": "A lead with no UTMs can't be credited to any campaign."})
    items = []
    for p in leakers[:5]:
        it = info[p]
        det = "%s of %s leads had no UTMs." % (n(it["untagged"]), n(it["leads"]))
        if it["lost"]:
            det += " %s came from a %s click, so the ad URL is missing its tags." % (n(it["lost"]), it["lost_plat"])
        else:
            det += " Tag the links and ads that point here."
        items.append({"label": "/ (homepage)" if p == "/" else _safe(p, 60),
                      "value": pct(share(it["untagged"], it["leads"])), "status": status(it),
                      "detail": det, "status_label": "Fix" if status(it) == "fail" else "Watch"})
    if len(leakers) > 5:
        rest = leakers[5:]
        names = [_safe(p, 30) for p in rest[:3]]
        listed = (", ".join(names[:-1]) + " and " + names[-1]) if len(names) > 1 else names[0]
        if len(rest) > 3:
            listed = ", ".join(names) + " and %s more" % (n(len(rest) - 3))
        items.append({"label": "%s more to watch" % _plural(len(rest), "page"),
                      "value": pct(share(sum(info[p]["untagged"] for p in rest), sum(info[p]["leads"] for p in rest))),
                      "status": "warn", "detail": "Some untagged leads on %s." % listed, "status_label": "Watch"})
    clean = [p for p in order if status(info[p]) == "pass"]
    if clean:
        cl_leads = sum(info[p]["leads"] for p in clean)
        cl_tagged = sum(info[p]["leads"] - info[p]["untagged"] for p in clean)
        items.append({"label": ("All %s pass" % _plural(len(clean), "page")) if not leakers else
                      ("%s %s" % (_plural(len(clean), "other page"), "passes" if len(clean) == 1 else "pass")),
                      "value": pct(share(cl_tagged, cl_leads)), "status": "pass",
                      "detail": "Their leads arrived with UTMs at least 90%% of the time, with no untagged ad clicks (%s of %s)." % (
                          n(cl_tagged), n(cl_leads))})
    secs.append({"type": "scorecard", "title": "Leak check by *page*", "items": items})

    # ---- 03 next steps
    recs = []
    if lost_total:
        lp = lost_plats.most_common(1)[0][0]
        recs.append({"label": "This week", "title": "Add UTMs to every *%s* ad URL" % lp,
                     "body": "%s arrived with a click ID but no UTMs, on %s. The most: %s with %s. Add utm_source, "
                             "utm_medium and utm_campaign to the tracking template." % (
                                 _plural(lost_total, "paid click"), _plural(sum(1 for i in info.values() if i["lost"]), "page"),
                                 _safe(focus, 40), n(info[focus]["lost"])),
                     "impact": "High", "effort": "Low"})
    if failing:
        p = failing[0]
        it = info[p]
        recs.append({"label": "This week", "title": "Fix tagging on *%s*" % _safe(p, 40),
                     "body": "%s of %s leads landed here with no UTMs. Tag every ad, email and post that points "
                             "here." % (n(it["untagged"]), n(it["leads"])),
                     "impact": "High", "effort": "Low"})
    elif leakers and not lost_total:
        p = leakers[0]
        recs.append({"label": "This month", "title": "Tag the links into *%s*" % _safe(p, 40),
                     "body": "%s of its %s leads arrived with no UTMs." % (n(info[p]["untagged"]), n(info[p]["leads"])),
                     "impact": "Medium", "effort": "Low"})
    if has_prior:
        drops = sorted([p for p in prior_c if prior_c[p] >= 8 and info.get(p, {"leads": 0})["leads"] < 0.75 * prior_c[p]],
                       key=lambda p: -(prior_c[p] - info.get(p, {"leads": 0})["leads"]))
        if drops:
            p = drops[0]
            cur = info.get(p, {"leads": 0})["leads"]
            recs.append({"label": "This week", "title": "Check the form on *%s*" % _safe(p, 40),
                         "body": "Leads fell from %s to %s. Test the form, the offer and the links that feed it." % (
                             n(prior_c[p]), n(cur)), "impact": "Medium", "effort": "Low"})
        rises = sorted([p for p in order if p != top and info[p]["leads"] >= 5 and info[p]["prior"] >= 1
                        and info[p]["leads"] >= 1.25 * info[p]["prior"]],
                       key=lambda p: -(info[p]["leads"] - info[p]["prior"]))
        if rises:
            p = rises[0]
            recs.append({"label": "This month", "title": "Find out why *%s* grew" % _safe(p, 40),
                         "body": "It rose from %s to %s leads. Check which ads or links changed, then point more "
                                 "traffic at it." % (n(info[p]["prior"]), n(info[p]["leads"])),
                         "impact": "Medium", "effort": "Low"})
    recs.append({"label": "This month", "title": "Use *%s* as your template" % ("your homepage" if top == "/" else _safe(top, 40)),
                 "body": "It brought %s (%s). Its biggest source was %s. Start new landing pages from its headline, "
                         "offer and form placement." % (_plural(ti["leads"], "lead"), pct(top_share), ti["top_src"]),
                 "impact": "Medium", "effort": "Medium"})
    if top3 >= 70:
        recs.append({"label": "Ongoing", "title": "Test your *top three* forms weekly",
                     "body": "They carry %s of leads. A broken form there stops most of your pipeline." % pct(top3),
                     "impact": "Medium", "effort": "Low"})
    if len(recs) < 2:
        recs.append({"label": "Ongoing", "title": "Rerun this *page* check monthly",
                     "body": "Pages change with every site edit. A monthly look catches a broken form early.",
                     "impact": "Low", "effort": "Low"})
    secs.append({"type": "section-header", "number": "03", "kicker": "Next steps", "title": "What to do *next*."})
    secs.append({"type": "recommendations", "items": recs[:4]})

    parts = []
    for b, label in (("first", "the first page they landed on (first touch)"),
                     ("landing", "the landing page of the visit that converted"),
                     ("form", "the page the form was on")):
        if basis[b]:
            parts.append("%s for %s" % (label, _plural(basis[b], "lead")))
    notes = ["Pages are %s." % "; ".join(parts),
             "Query strings, fragments, trailing slashes and letter case are ignored, so /Pricing/?ref=x counts as /pricing.",
             "Tagged means the lead carried at least one of utm_source, utm_medium or utm_campaign. A page needs a fix "
             "when 30% or more of its leads arrive untagged, and is watched from 10%, or when any paid click (gclid, "
             "fbclid, msclkid) arrives untagged."]
    if not basis["first"]:
        notes.append("First-touch landing pages were not in this data, so each lead sits on the page of the visit that "
                     "converted, or where the form was submitted.")
    if has_prior:
        notes.append("Changes compare %s with %s." % (period, m["compare_label"]))
    secs.append({"type": "notes", "items": notes})

    if lost_total:
        close = "Next: add UTMs to every *%s* ad URL. %s lost their tags." % (
            lost_plats.most_common(1)[0][0], _plural(lost_total, "paid click"))
    elif failing:
        p = failing[0]
        close = "Next: fix tagging on *%s*. %s leads landed there without UTMs." % (_safe(p, 40), n(info[p]["untagged"]))
    elif top == "/":
        close = "Next: build new pages from your *homepage*. It brought %s of leads." % pct(top_share)
    else:
        close = "Next: build new pages from *%s*. It brought %s of leads." % (_safe(top, 40), pct(top_share))
    secs.append({"type": "closing", "kicker": "The pages in one line", "title": close,
                 "summary_stats": [{"value": n(len(groups)), "label": "Pages with leads"},
                                   {"value": pct(top_share), "label": "Top page share"},
                                   {"value": pct(top3), "label": "Top 3 share"},
                                   {"value": n(lost_total), "label": "Paid clicks untagged"}],
                 "bullets": ["%s brought %s." % (top_name, _plural(ti["leads"], "lead")),
                             "%s of all leads arrived with UTMs." % pct(tag_all)] +
                            (["%s lost tags on 30%% or more of their leads." % _plural(len(failing), "page")] if failing else
                             ["%s to watch for untagged leads." % _plural(len(leakers), "page")] if leakers else [])})
    return {"meta": m, "sections": secs}


# ---------------------------------------------------------------------------
# BUDGET SIMULATOR
# ---------------------------------------------------------------------------
def _resolve(key, entries, ads):
    """Scenario key -> unit dict {kind, label, pred, spend} or None.

    Order: campaign name, then ad platform (google -> Google Ads), then utm_source."""
    raw = str(key or "").strip()
    if not raw:
        return None
    ck = norm_key(raw)
    camps = Counter(norm_key(lead_campaign(e)) for e in entries if lead_campaign(e))
    ad_camps = {norm_key(r["campaign"]): r["campaign"] for r in ads if r.get("campaign")}
    if ck in camps or ck in ad_camps:
        disp = next((lead_campaign(e) for e in entries if norm_key(lead_campaign(e)) == ck), ad_camps.get(ck, raw))
        return {"kind": "campaign", "key": ck, "label": _label(disp, 32),
                "pred": lambda e, ck=ck: norm_key(lead_campaign(e)) == ck,
                "spend": sum(r["spend"] for r in ads if norm_key(r.get("campaign")) == ck),
                "has_rows": any(norm_key(r.get("campaign")) == ck for r in ads)}
    plat = _as_platform(raw)
    if plat and (any(lead_platform(e) == plat for e in entries) or any(_row_platform(r) == plat for r in ads)
                 or not any(lead_source_medium(e)[0] == raw.lower() for e in entries)):
        return {"kind": "platform", "key": plat, "label": plat,
                "pred": lambda e, plat=plat: lead_platform(e) == plat,
                "spend": sum(r["spend"] for r in ads if _row_platform(r) == plat),
                "has_rows": any(_row_platform(r) == plat for r in ads)}
    src = raw.lower()
    if any(lead_source_medium(e)[0] == src for e in entries):
        return {"kind": "source", "key": src, "label": _src_name(src),
                "pred": lambda e, src=src: lead_source_medium(e)[0] == src, "spend": 0.0, "has_rows": False}
    return None


def _default_scenario(entries):
    plats = Counter(lead_platform(e) for e in entries if lead_platform(e))
    if len(plats) >= 2:
        (a, _), (b, _) = plats.most_common(2)
        return a, b
    srcs = Counter(lead_source_medium(e)[0] for e in entries if lead_source_medium(e)[0])
    if len(srcs) >= 2:
        (a, _), (b, _) = srcs.most_common(2)
        return a, b
    return None, None


def _pct_value(v, default=20.0):
    try:
        x = float(str(v).replace("%", "").strip())
    except (TypeError, ValueError):
        return default
    return x


def _rng(lo, hi, signed=False, fmt=None):
    a, b = sorted((int(round(lo)), int(round(hi))))
    f = fmt or (_signed if signed else n)
    return f(a) if a == b else "%s to %s" % (f(a), f(b))


def build_budget_simulator(current, scenario=None, ad_rows=None, brand_profile=None, customer_name=None,
                           customer_domain="", compare_label=None, prepared_by=None, prepared_for=None, **_):
    """What-if: move pct% of budget (or effort) from one source/platform/campaign to another."""
    _, start, end, m = _setup(current, None, brand_profile, customer_name, customer_domain, compare_label,
                              prepared_by, prepared_for)
    m.pop("compare_label", None)
    name = "Budget simulator"
    if not current:
        return empty_report(name, m)
    period = period_label(start, end)
    kicker = _kick(name, period)
    days = _days(start, end)
    when = _in_period(start, end)
    ads = _ad_rows(ad_rows)
    m["sources"] = _spend_chips(len(current), ads)
    scenario = dict(scenario or {})
    defaulted = not (scenario.get("shift_from") and scenario.get("shift_to"))
    if defaulted:
        a, b = _default_scenario(current)
        scenario.setdefault("shift_from", a)
        scenario.setdefault("shift_to", b)
    p_raw = _pct_value(scenario.get("pct", 20))
    bits = [customer_domain, _plural(len(current), "lead"), "%d days" % days if days else ""]

    if len(current) < MIN_LEADS:
        return _short(m, kicker, "Only %s so far, too few to model a *budget* shift." % _plural(len(current), "lead"),
                      "A shift model needs at least %d *leads*." % MIN_LEADS,
                      ["Each channel's lead count is the baseline the model scales. With %s, one lead is a big swing." %
                       _plural(len(current), "lead"), "Widen the date range to 60 or 90 days and run it again."],
                      close_title="Next: rerun with a *wider* date range.", bits=bits)
    src_u = _resolve(scenario.get("shift_from"), current, ads)
    dst_u = _resolve(scenario.get("shift_to"), current, ads)
    if not src_u or not dst_u or src_u["key"] == dst_u["key"] or not (0 < p_raw <= 100):
        avail = Counter(lead_platform(e) for e in current if lead_platform(e))
        avail_s = Counter(_src_name(lead_source_medium(e)[0]) for e in current if lead_source_medium(e)[0])
        names = [k for k, _ in avail.most_common(4)] + [k for k, _ in avail_s.most_common(4)]
        if not (0 < p_raw <= 100):
            why = "The shift must be more than 0%% and at most 100%%; it was %s." % _safe(scenario.get("pct"))
        elif src_u and dst_u and src_u["key"] == dst_u["key"]:
            why = "The scenario moves budget from %s to itself." % src_u["label"]
        else:
            miss = [str(scenario.get(k)) for k, u in (("shift_from", src_u), ("shift_to", dst_u)) if not u]
            why = "We could not find %s in this data." % " or ".join("\"%s\"" % _safe(x, 30) for x in miss)
        return _short(m, kicker, "This *scenario* doesn't match your data yet.", "Check the *scenario*.",
                      [why, "Channels with leads: %s." % ", ".join(names[:6]) if names else
                       "No lead carried a source or an ad platform."],
                      close_title="Next: pick two *channels* from the list and run it again.", bits=bits)
    p = min(100.0, p_raw) / 100.0
    pct_txt = pct(p_raw) if float(p_raw).is_integer() else pct(p_raw, 1)
    fr, to = src_u["label"], dst_u["label"]
    T = len(current)
    Lf = sum(1 for e in current if src_u["pred"](e))
    Lt = sum(1 for e in current if dst_u["pred"](e))
    if Lf == 0:
        return _short(m, kicker, "%s sent no leads %s, so there is nothing to *shift*." % (fr, when),
                      "The model scales each channel's *leads*.",
                      ["%s has no leads in this data, so moving its budget can't be projected." % fr,
                       "Pick a source with leads, or widen the date range."],
                      close_title="Next: model a *channel* that has leads.", bits=bits)
    Sf, St = src_u["spend"], dst_u["spend"]
    use_spend = Sf > 0 and St > 0
    loss = p * Lf
    if use_spend:
        D = p * Sf
        cpl_f, cpl_t = Sf / Lf, (St / Lt if Lt else None)
        gain_hi = D * Lt / St
        gain_lo = Lt * (math.sqrt(1.0 + D / St) - 1.0)
    else:
        D = None
        cpl_f = cpl_t = None
        gain_hi = loss
        gain_lo = Lt * (math.sqrt(1.0 + loss / Lt) - 1.0) if Lt else 0.0
    ch_lo, ch_hi = gain_lo - loss, gain_hi - loss
    proj_lo, proj_hi = T + ch_lo, T + ch_hi
    gain_mid = (gain_lo + gain_hi) / 2.0
    loss_r = int(round(loss))

    # ---- verdict
    if round(ch_lo) > 0:
        verdict = "gain"
        title = "Moving %s from %s to *%s* could add %s leads." % (pct_txt, fr, to, _rng(ch_lo, ch_hi))
    elif round(ch_hi) < 0:
        verdict = "loss"
        title = "Moving %s from %s to *%s* would cost %s leads." % (pct_txt, fr, to, _rng(-ch_hi, -ch_lo))
    elif not use_spend and round(ch_hi) == 0:
        verdict = "flat"
        title = "Without spend data, a %s shift to *%s* at best holds leads flat." % (pct_txt, to)
    else:
        verdict = "wash"
        title = "Moving %s to *%s* is a coin flip: %s leads." % (pct_txt, to, _rng(ch_lo, ch_hi, signed=True))
    sub = ("%s brought %s and %s brought %s %s. " % (fr, _plural(Lf, "lead"), to, _plural(Lt, "lead"), when) +
           ("Spend: %s on %s, %s on %s." % (money(Sf), fr, money(St), to) if use_spend else
            "No ad spend was connected, so the model uses lead counts as a stand-in for effort."))
    if defaulted:
        sub = "No scenario was given, so this models your two biggest channels. " + sub
    secs = [{"type": "title-block", "kicker": kicker, "title": title, "subtitle": sub,
             "meta_bits": [b for b in [customer_domain, "Shift %s from %s to %s" % (pct_txt, fr, to),
                                       "%s baseline" % ("%d-day" % days if days else "period")] if b]}]

    _, daily = daily_counts(current, start, end)
    lo_r, hi_r = int(round(proj_lo)), int(round(proj_hi))
    stats = [stat("Leads today", n(T), spark=daily, note=("in %d days" % days) if days else None),
             dict(stat("Projected, low end", n(lo_r), lo_r, T,
                       note="%s leads if %s saturates" % (_signed(ch_lo), to)), compare="today"),
             dict(stat("Projected, high end", n(hi_r), hi_r, T,
                       note="%s leads if its yield holds" % _signed(ch_hi)), compare="today")]
    paid_all = sum(1 for e in current if last_touch(e) == "Paid")
    spend_all = sum(r["spend"] for r in ads)
    if use_spend and paid_all:
        c_now = spend_all / paid_all
        c_lo = spend_all / max(1.0, paid_all + ch_hi)
        c_hi = spend_all / max(1.0, paid_all + ch_lo)
        stats.append(stat("Cost per lead", money(c_now), good="down",
                          note="%s with the shift" % _rng(c_lo, c_hi, fmt=lambda v: money(v, 0))))
    secs.append({"type": "stat-strip", "stats": stats})

    # ---- the assumption
    if use_spend:
        a_title = "Real cost per lead, with *saturation* built in."
        a_body = ["%s loses leads at its average cost per lead, %s." % (fr, money(cpl_f)),
                  "%s gains leads with a square-root response: doubling its spend brings about 41%% more leads, "
                  "not 100%%. The high end assumes it keeps today's %s per lead." % (to, money(cpl_t) if cpl_t else "cost")]
        tone = "neutral"
    else:
        a_title = "This model assumes leads follow *effort*."
        a_body = ["No ad spend was connected, so we treat each channel's leads as proportional to the effort behind it, "
                  "and assume one unit of effort buys the same number of leads in %s and %s." % (fr, to),
                  "That makes the best case flat. The low end assumes %s saturates as it grows (a square-root response)." % to]
        if ads and not use_spend:
            a_body.append("Spend rows did not cover both %s and %s, so they were not used." % (fr, to))
        tone = "warn"
    secs.append({"type": "insight-card", "kicker": "The assumption", "title": a_title, "body": a_body, "tone": tone})

    # ---- 01 the scenario
    secs.append({"type": "section-header", "number": "01", "kicker": "The scenario",
                 "title": "Where the *leads* move.",
                 "dek": "Only %s and %s change. Every other channel stays as it is." % (fr, to)})
    both = Lf + Lt
    lose_lbl = "Less from %s" % fr
    gain_lbl = "Added in %s" % to

    def _r(x):
        return int(round(x)) if abs(x) >= 10 else round(x, 1)

    steps = [{"label": "%s + %s today" % (fr, to), "value": both, "kind": "start"},
             {"label": lose_lbl, "value": -_r(loss)},
             {"label": gain_lbl, "value": _r(gain_mid)},
             {"label": "With the shift", "value": _r(both - loss + gain_mid), "kind": "total"}]
    if use_spend:
        m_title = "%s must add *%s* to break even." % (to, _plural(loss_r, "lead"))
        m_body = ["Moving %s out of %s costs about %s at %s each." % (money(D), fr, _plural(loss_r, "lead"), money(cpl_f)),
                  ("At today's %s per lead %s would add %s; if it saturates, %s." % (
                      money(cpl_t), to, n(int(round(gain_hi))), n(int(round(gain_lo))))) if cpl_t else
                  "%s brought no leads on %s of spend, so the model expects nothing back." % (to, money(St))]
    else:
        m_title = "%s must add *%s* to break even." % (to, _plural(loss_r, "lead"))
        m_body = ["Moving %s of the effort behind %s removes about %s of its %s." % (pct_txt, fr, _plural(loss_r, "lead"), n(Lf)),
                  ("If %s turns effort into leads at the same rate, it wins them back; if it saturates, it adds %s." % (
                      to, n(int(round(gain_lo))))) if Lt else
                  "%s has no leads yet, so it could return anywhere from none to all %s." % (to, n(loss_r))]
    secs.append({"type": "chart-insight",
                 "chart": {"type": "waterfall", "steps": steps},
                 "caption": "Leads from %s and %s only, middle of the range. Other channels are unchanged." % (fr, to),
                 "insight_kicker": "The math", "insight_title": m_title, "insight_body": m_body})
    rows = [{"label": "%s leads" % fr, "a": Lf, "b": round(Lf - loss, 1), "a_display": n(Lf),
             "b_display": n(int(round(Lf - loss)))},
            {"label": "%s leads" % to, "a": Lt, "b": round(Lt + gain_mid, 1), "a_display": n(Lt),
             "b_display": _rng(Lt + gain_lo, Lt + gain_hi)},
            {"label": "All leads", "a": T, "b": round(T + (ch_lo + ch_hi) / 2.0, 1), "a_display": n(T),
             "b_display": _rng(proj_lo, proj_hi)}]
    mid_ch = (ch_lo + ch_hi) / 2.0
    if round(mid_ch) != 0:
        rows[-1]["better"] = "b" if mid_ch > 0 else "a"
    if use_spend:
        rows += [{"label": "%s spend" % fr, "a": Sf, "b": Sf - D, "a_display": money(Sf), "b_display": money(Sf - D)},
                 {"label": "%s spend" % to, "a": St, "b": St + D, "a_display": money(St), "b_display": money(St + D)}]
    secs.append({"type": "comparison", "a": {"label": "Today", "sub": period},
                 "b": {"label": "With the shift", "sub": "%s moved to %s" % (pct_txt, to)}, "rows": rows,
                 "caption": "Ranges run from the saturating case (low) to today's yield holding (high)."})

    # ---- 02 next steps
    weeks = max(1.0, days / 7.0)
    recs = []
    if verdict == "gain":
        recs.append({"label": "This month", "title": "Run the shift as a *two-week test*",
                     "body": "The model gains %s leads. Move %s for two weeks and keep %s's cost per lead under %s." % (
                         _rng(ch_lo, ch_hi), pct_txt, to, money(cpl_f)) if use_spend else
                     "The model gains %s leads. Move %s for two weeks and compare weekly leads." % (_rng(ch_lo, ch_hi), pct_txt),
                     "impact": "High", "effort": "Low"})
    elif verdict == "loss":
        recs.append({"label": "This week", "title": "Keep the budget in *%s*" % fr,
                     "body": "Even at best the shift loses %s. %s" % (
                         _plural(int(round(-ch_hi)), "lead"),
                         "%s brings leads at %s vs %s in %s." % (fr, money(cpl_f), money(cpl_t), to) if use_spend and cpl_t
                         else "%s turns budget into leads more cheaply today." % fr),
                     "impact": "High", "effort": "Low"})
    elif verdict == "flat":
        recs.append({"label": "This week", "title": "Connect *ad spend* before moving budget",
                     "body": "Without spend, the best case for this shift is flat and the worst is %s. Spend for %s and "
                             "%s shows whether %s buys leads more cheaply." % (
                                 _plural(int(round(-ch_lo)), "lead") + " lost", fr, to, to),
                     "impact": "High", "effort": "Low"})
    else:
        half = pct(p_raw / 2.0) if (p_raw / 2.0).is_integer() else pct(p_raw / 2.0, 1)
        recs.append({"label": "This month", "title": "Test a smaller shift into *%s*" % to,
                     "body": "The result runs from %s leads. Move %s for two weeks before committing the full %s." % (
                         _rng(ch_lo, ch_hi, signed=True), half, pct_txt),
                     "impact": "Medium", "effort": "Low"})
    if verdict == "loss" and use_spend and Lf and Lt:
        # the same model run the other way: is the opposite move worth a test?
        D2 = p * St
        r_lo = Lf * (math.sqrt(1.0 + D2 / Sf) - 1.0) - p * Lt
        r_hi = D2 * Lf / Sf - p * Lt
        if round(r_hi) > 0:
            recs.append({"label": "This month", "title": "Test the reverse: %s into *%s*" % (pct_txt, fr),
                         "body": "The same model says moving %s of the %s budget (%s) into %s changes leads by %s, "
                                 "because %s brings leads at %s vs %s." % (
                                     pct_txt, to, money(D2), fr, _rng(r_lo, r_hi, signed=True), fr, money(cpl_f),
                                     money(cpl_t) if cpl_t else "more"),
                         "impact": "Medium", "effort": "Low"})
    recs.append({"label": "Weekly", "title": "Track *%s* leads every week" % to,
                 "body": "Today it brings %s leads a week. To break even it must reach %s a week." % (
                     n(round(Lt / weeks, 1)), n(round((Lt + loss) / weeks, 1))),
                 "impact": "Medium", "effort": "Low"})
    if not use_spend and verdict != "flat":
        recs.append({"label": "Next run", "title": "Connect *ad spend* for a sharper model",
                     "body": "With spend for %s and %s, the simulator uses real cost per lead instead of the effort "
                             "assumption." % (fr, to), "impact": "Medium", "effort": "Low"})
    no_src = sum(1 for e in current if not lead_source_medium(e)[0])
    if share(no_src, T) >= 20:
        recs.append({"label": "This month", "title": "Tag the %s of leads with no *source*" % pct(share(no_src, T)),
                     "body": "They can't be credited to either channel, so both baselines are undercounted.",
                     "impact": "Medium", "effort": "Low"})
    secs.append({"type": "section-header", "number": "02", "kicker": "Next steps", "title": "How to *test* it."})
    secs.append({"type": "recommendations", "items": recs[:4]})

    kind_txt = {"platform": "ad platform (paid leads with that platform's click ID or paid tags)",
                "campaign": "campaign (utm_campaign, case and punctuation ignored)",
                "source": "utm_source (every medium)"}
    notes = ["Baseline: %s from %s." % (_plural(T, "lead"), period or "the data provided"),
             "\"%s\" was read as the %s %s: %s. \"%s\" was read as the %s %s: %s." % (
                 _safe(scenario.get("shift_from"), 30), kind_txt[src_u["kind"]].split(" (")[0], fr, _plural(Lf, "lead"),
                 _safe(scenario.get("shift_to"), 30), kind_txt[dst_u["kind"]].split(" (")[0], to, _plural(Lt, "lead"))]
    if use_spend:
        notes.append("Spend from %s: %s on %s, %s on %s. %s loses leads in proportion to the dollars moved." % (
            _ad_dates(ads), money(Sf), fr, money(St), to, fr))
        notes.append("Low end: %s gains leads as the square root of its spend. High end: it keeps today's cost per lead." % to)
    else:
        notes.append("No spend: leads are assumed proportional to effort, and effort is assumed to buy the same leads "
                     "in both channels. %s loses %s of its leads." % (fr, pct_txt))
        notes.append("Low end: %s responds as the square root of its effort. High end: it matches %s's yield." % (to, fr))
    notes.append("Projections are a range, not a promise. Test, then rerun this with the new data.")
    secs.append({"type": "notes", "items": notes})

    if verdict == "gain":
        close = "Next: test %s in *%s* for two weeks. Break-even is %s." % (pct_txt, to, _plural(loss_r, "extra lead"))
    elif verdict == "loss":
        close = "Next: keep budget in *%s*. The shift loses up to %s." % (fr, _plural(int(round(-ch_lo)), "lead"))
    elif verdict == "flat":
        close = "Next: connect *ad spend*. Without it the best case for this shift is flat."
    else:
        close = "Next: test a smaller shift into *%s*. It needs %s to break even." % (to, _plural(loss_r, "extra lead"))
    secs.append({"type": "closing", "kicker": "The scenario in one line", "title": close,
                 "summary_stats": [{"value": n(T), "label": "Leads today"},
                                   {"value": _rng(proj_lo, proj_hi), "label": "With the shift"},
                                   {"value": _rng(ch_lo, ch_hi, signed=True), "label": "Change"},
                                   {"value": pct_txt, "label": "Budget moved"}],
                 "bullets": ["%s: %s today, about %s after the shift." % (fr, n(Lf), n(int(round(Lf - loss)))),
                             "%s: %s today, %s after the shift." % (to, n(Lt), _rng(Lt + gain_lo, Lt + gain_hi)),
                             "Model: %s." % ("real cost per lead with saturation" if use_spend else
                                             "leads follow effort, no spend data")]})
    return {"meta": m, "sections": secs}


REGISTRY = {
    "ad-creative": build_ad_creative, "ad-creative-performance": build_ad_creative, "creative": build_ad_creative,
    "utm-content": build_ad_creative,
    "keyword": build_keyword, "keywords": build_keyword, "keyword-performance": build_keyword,
    "utm-term": build_keyword, "search-terms": build_keyword,
    "landing-page": build_landing_page, "landing-pages": build_landing_page, "pages": build_landing_page,
    "landing-page-performance": build_landing_page,
    "budget-simulator": build_budget_simulator, "budget": build_budget_simulator, "what-if": build_budget_simulator,
    "simulator": build_budget_simulator,
}
