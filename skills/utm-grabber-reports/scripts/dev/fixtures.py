"""
Dev fixtures: a "kitchen sink" summary that uses every section type and chart
type, plus edge-case summaries (long labels, tiny data, light brand colors).
Used by scripts/dev/test_matrix.py to render every component in every theme.
"""
import copy

BRAND = {
    "company_name": "Northwind Dental",
    "logo": {"type": "text", "value": "Northwind Dental"},
    "colors": {"primary": "#0E7C66", "accent": "#F2A541", "ink": "#0B1F1A", "muted": "#5A6B64",
               "surface": "#EEF7F4"},
}

DAYS = ["Sep %d" % d for d in range(1, 31)]
LEADS = [31, 38, 44, 40, 29, 22, 35, 41, 47, 43, 39, 24, 21, 37, 45, 52, 48, 44, 27, 23, 39,
         46, 55, 51, 47, 30, 26, 44, 58, 61]


def kitchen_sink(brand=None):
    b = brand or BRAND
    return {
        "meta": {
            "customer_name": b["company_name"], "customer_domain": "northwinddental.com",
            "brand_profile": b, "skill_version": "2.0.0", "generated_at": "2026-10-05T09:00:00Z",
            "compare_label": "August", "prepared_by": "Brightline Agency",
            "prepared_for": "Northwind Dental",
            "sources": [
                {"name": "UTM Grabber", "detail": "1,186 leads"},
                {"name": "Google Ads", "detail": "$18,420 spend"},
                {"name": "Meta Ads", "detail": "$9,180 spend"},
                {"name": "Google Analytics 4", "detail": "48,210 sessions"},
                {"name": "HubSpot", "detail": "214 deals"},
            ],
        },
        "sections": [
            {"type": "title-block", "kicker": "Full-funnel performance · September 2026",
             "title": "September turned *ad spend* into $86K of booked revenue.",
             "subtitle": "Every lead matched to the ad, the visit and the deal it became. Google search did the heavy lifting; Meta retargeting found the cheapest patients.",
             "meta_bits": ["northwinddental.com", "Gravity Forms + WooCommerce", "30 days"]},
            {"type": "stat-strip", "stats": [
                {"label": "Leads", "value": "1,186", "delta_label": "+14%", "delta_direction": "up",
                 "spark": LEADS, "source": "UTM Grabber"},
                {"label": "Cost per lead", "value": "$23.27", "delta_label": "−9%", "delta_direction": "down",
                 "good": "down", "spark": [29, 28, 27, 27, 26, 25, 25, 24, 24, 23], "source": "Ads + UTMG"},
                {"label": "New patients", "value": "214", "delta_label": "+21%", "delta_direction": "up",
                 "spark": [5, 6, 7, 6, 8, 7, 9, 8, 9, 10], "source": "HubSpot"},
                {"label": "Return on ad spend", "value": "3.1x", "delta_label": "+0.4x", "delta_direction": "up",
                 "spark": [2.4, 2.5, 2.6, 2.7, 2.7, 2.9, 3.0, 3.1], "source": "All platforms"},
            ]},
            {"type": "insight-card", "kicker": "The headline",
             "title": "*Google search* brought 41% of new patients at half the cost of Meta.",
             "body": ["Brand and emergency-dentist keywords converted at 9.8%. Meta prospecting filled the top of the funnel but closed at 2.1%.",
                      "Shift $2,000 from Meta prospecting to Google emergency terms and October should add about 18 patients."]},
            {"type": "section-header", "number": "01", "kicker": "The funnel",
             "title": "From *visit* to booked patient.",
             "dek": "Sessions from Google Analytics, leads from UTM Grabber, patients and revenue from HubSpot."},
            {"type": "funnel", "stages": [
                {"label": "Website sessions", "value": 48210, "source": "Google Analytics 4"},
                {"label": "Form leads", "value": 1186, "source": "UTM Grabber", "conv_label": "of sessions became leads"},
                {"label": "Booked consults", "value": 512, "source": "HubSpot", "conv_label": "of leads booked"},
                {"label": "New patients", "value": 214, "source": "HubSpot", "conv_label": "of consults started treatment"}],
             "insight_kicker": "Where it leaks", "insight_title": "Only *43%* of leads book a consult.",
             "insight_body": ["The biggest drop is between form and booking. Leads that get a call within 5 minutes book at 61%."]},
            {"type": "section-header", "number": "02", "kicker": "Channels",
             "title": "Which *channels* paid for themselves."},
            {"type": "chart-insight",
             "chart": {"type": "doughnut", "labels": ["Paid search", "Paid social", "Organic", "Referral", "Direct", "Email", "AI assistants"],
                       "values": [41, 22, 17, 8, 6, 4, 2], "unit": "%"},
             "caption": "Share of new patients by first-touch channel",
             "insight_kicker": "The mix", "insight_title": "Paid search starts *41%* of journeys.",
             "insight_body": ["Organic search is the quiet second engine: 17% of patients, zero ad cost."]},
            {"type": "ranked-list", "title": "Spend, leads and revenue by *platform*",
             "columns": [
                 {"key": "platform", "label": "Platform", "type": "platform"},
                 {"key": "spend", "label": "Spend", "type": "money", "align": "right"},
                 {"key": "leads", "label": "Leads", "type": "bar"},
                 {"key": "cpl", "label": "Cost per lead", "type": "money", "align": "right"},
                 {"key": "patients", "label": "Patients", "type": "number", "align": "right"},
                 {"key": "roas", "label": "ROAS", "type": "number", "align": "right"},
                 {"key": "trend", "label": "vs August", "type": "delta", "align": "right"}],
             "rows": [
                 {"platform": "Google Ads", "spend": "$18,420", "leads": {"value": 642, "label": "642"}, "cpl": "$28.69", "patients": "118", "roas": "3.6x", "trend": {"label": "+18%", "direction": "up"}},
                 {"platform": "Meta Ads", "spend": "$9,180", "leads": {"value": 398, "label": "398"}, "cpl": "$23.07", "patients": "52", "roas": "2.2x", "trend": {"label": "−6%", "direction": "down"}},
                 {"platform": "Organic search", "spend": "$0", "leads": {"value": 104, "label": "104"}, "cpl": "–", "patients": "33", "roas": "n/a", "trend": {"label": "+4%", "direction": "up"}},
                 {"platform": "Email", "spend": "$0", "leads": {"value": 42, "label": "42"}, "cpl": "–", "patients": "11", "roas": "n/a", "trend": {"label": "0%", "direction": "flat"}}],
             "totals": {"platform": "Total", "spend": "$27,600", "leads": "1,186", "cpl": "$23.27", "patients": "214", "roas": "3.1x", "trend": "+14%"},
             "caption": "Spend from Google Ads and Meta Ads. Leads matched by utm_campaign and click ID."},
            {"type": "chart",
             "chart": {"type": "line-multi", "labels": DAYS,
                       "series": [{"label": "Google Ads", "values": [18, 21, 25, 22, 16, 12, 19, 23, 27, 24, 22, 13, 12, 21, 25, 29, 27, 25, 15, 13, 22, 26, 31, 29, 27, 17, 14, 25, 33, 35]},
                                  {"label": "Meta Ads", "values": [9, 12, 13, 12, 9, 7, 11, 12, 14, 13, 12, 7, 6, 11, 14, 16, 14, 13, 8, 7, 12, 13, 16, 15, 13, 9, 8, 13, 17, 18]},
                                  {"label": "Organic", "values": [4, 5, 6, 6, 4, 3, 5, 6, 6, 6, 5, 4, 3, 5, 6, 7, 7, 6, 4, 3, 5, 7, 8, 7, 7, 4, 4, 6, 8, 8]}]},
             "chart_title": "Daily leads by *platform*", "caption": "Weekend dips are normal for dental. Tuesdays peak."},
            {"type": "section-header", "number": "03", "kicker": "Money", "title": "Where the *revenue* came from."},
            {"type": "chart-insight",
             "chart": {"type": "waterfall", "unit": "$", "steps": [
                 {"label": "Ad spend", "value": 27600, "kind": "start"},
                 {"label": "Google search revenue", "value": 39800},
                 {"label": "Meta revenue", "value": 20200},
                 {"label": "Organic revenue", "value": 26400},
                 {"label": "Refunds", "value": -4100},
                 {"label": "Net revenue", "value": 82300, "kind": "total"}]},
             "caption": "Revenue from WooCommerce orders matched to each lead's first touch",
             "insight_kicker": "Return", "insight_title": "Every *$1* in ads returned $3.10.",
             "insight_body": ["Organic revenue is pure margin and grew 9% on the back of the new implant guide."]},
            {"type": "matrix", "chart_title": "Campaigns: cost per lead vs *volume*",
             "points": [
                 {"label": "Emergency dentist", "x": 212, "y": 19.4, "size": 212, "group": "Google Ads"},
                 {"label": "Brand search", "x": 188, "y": 8.2, "size": 188, "group": "Google Ads"},
                 {"label": "Implants", "x": 96, "y": 61.0, "size": 96, "group": "Google Ads"},
                 {"label": "Invisalign", "x": 146, "y": 33.5, "size": 146, "group": "Google Ads"},
                 {"label": "Retargeting", "x": 174, "y": 14.1, "size": 174, "group": "Meta Ads"},
                 {"label": "Lookalike", "x": 132, "y": 38.9, "size": 132, "group": "Meta Ads"},
                 {"label": "Whitening offer", "x": 92, "y": 27.3, "size": 92, "group": "Meta Ads"}],
             "x_label": "Leads", "y_label": "Cost per lead", "y_unit": "$", "x_ref": 140, "y_ref": 28,
             "quadrants": {"tl": "Fix or cut", "tr": "Scale with care", "bl": "Hidden gems", "br": "Scale now"},
             "insight_kicker": "Read the map", "insight_title": "*Retargeting* is cheap and big. Feed it.",
             "insight_body": ["Implants cost $61 per lead. Pause the broad match terms first."]},
            {"type": "section-header", "number": "04", "kicker": "Journeys", "title": "How patients *found* you."},
            {"type": "flow", "left_title": "First touch", "right_title": "Last touch before booking",
             "chart_title": "From discovery to *decision*",
             "links": [
                 {"from": "Paid search", "to": "Paid search", "value": 61}, {"from": "Paid search", "to": "Direct", "value": 18},
                 {"from": "Paid search", "to": "Email", "value": 9}, {"from": "Paid social", "to": "Paid search", "value": 21},
                 {"from": "Paid social", "to": "Paid social", "value": 17}, {"from": "Paid social", "to": "Direct", "value": 9},
                 {"from": "Organic", "to": "Organic", "value": 22}, {"from": "Organic", "to": "Direct", "value": 14},
                 {"from": "AI assistants", "to": "Direct", "value": 4}, {"from": "Referral", "to": "Referral", "value": 12},
                 {"from": "Referral", "to": "Direct", "value": 6}],
             "caption": "Meta starts journeys that Google search finishes. Judge Meta on first touch."},
            {"type": "heatmap", "chart_title": "When *leads* arrive",
             "rows": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
             "cols": ["%d%s" % ((h % 12) or 12, "a" if h < 12 else "p") for h in range(7, 23)],
             "values": [[2, 5, 9, 12, 14, 11, 10, 12, 11, 9, 8, 7, 9, 8, 5, 2],
                        [3, 7, 12, 15, 17, 13, 12, 14, 13, 11, 9, 9, 10, 9, 6, 3],
                        [2, 6, 10, 13, 15, 12, 11, 13, 12, 10, 9, 8, 9, 7, 5, 2],
                        [2, 6, 10, 12, 14, 12, 10, 12, 11, 10, 8, 8, 8, 7, 4, 2],
                        [2, 5, 8, 10, 12, 10, 8, 9, 8, 6, 5, 4, 4, 3, 2, 1],
                        [0, 1, 3, 5, 6, 6, 5, 4, 3, 3, 2, 2, 2, 2, 1, 1],
                        [0, 1, 2, 3, 4, 4, 4, 3, 3, 3, 3, 4, 5, 5, 3, 1]],
             "caption": "Tuesday 10am is the busiest hour. Staff the phones then."},
            {"type": "comparison", "a": {"label": "Google Ads", "sub": "$18,420 spend"},
             "b": {"label": "Meta Ads", "sub": "$9,180 spend"},
             "rows": [{"label": "Leads", "a": 642, "b": 398, "better": "a"},
                      {"label": "Cost per lead", "a": 28.69, "b": 23.07, "a_display": "$28.69", "b_display": "$23.07", "better": "b"},
                      {"label": "Booking rate", "a": 48, "b": 31, "a_display": "48%", "b_display": "31%", "better": "a"},
                      {"label": "Cost per patient", "a": 156, "b": 177, "a_display": "$156", "b_display": "$177", "better": "a"},
                      {"label": "Revenue", "a": 39800, "b": 20200, "a_display": "$39.8K", "b_display": "$20.2K", "better": "a"}],
             "caption": "Meta wins on cheap leads, Google wins on patients."},
            {"type": "callouts", "items": [
                {"kicker": "Platform said", "value": "1,412", "title": "conversions reported by Google + Meta", "tone": "neutral"},
                {"kicker": "Your forms saw", "value": "1,040", "title": "real paid leads in UTM Grabber", "tone": "neutral"},
                {"kicker": "Over-reported", "value": "26%", "title": "counted twice or never happened", "tone": "bad"}]},
            {"type": "scorecard", "title": "Tracking *health*", "items": [
                {"label": "UTM coverage on paid clicks", "value": "97%", "status": "pass", "detail": "Every Google and Meta ad carries source, medium and campaign."},
                {"label": "Google click ID captured", "value": "88%", "status": "warn", "detail": "12% of Google leads lost gclid. Check the booking widget redirect."},
                {"label": "Meta click ID captured", "value": "41%", "status": "fail", "detail": "Conversions API cannot match most Meta leads. Turn on fbclid capture."},
                {"label": "Lead to CRM match rate", "value": "94%", "status": "pass"}]},
            {"type": "timeline", "title": "One patient's *journey*", "events": [
                {"date": "Aug 28, 9:14pm", "title": "Asked ChatGPT for a dentist near Riverside", "detail": "First visit from chatgpt.com to /emergency-dentist", "tags": ["organic", "AI assistant"], "kind": "touch"},
                {"date": "Sep 2, 7:41am", "title": "Clicked a Meta retargeting ad", "detail": "Whitening offer, carousel 2", "tags": ["utm_source=facebook", "utm_campaign=retargeting"], "kind": "touch"},
                {"date": "Sep 3, 12:06pm", "title": "Searched \"emergency dentist open now\"", "detail": "Google Ads, exact match", "tags": ["gclid", "utm_term=emergency dentist"], "kind": "touch"},
                {"date": "Sep 3, 12:09pm", "title": "Booked a consult", "detail": "Booking form on /emergency-dentist", "kind": "conversion"},
                {"date": "Sep 19", "title": "Started treatment: $2,400", "detail": "Won in HubSpot", "kind": "purchase"}]},
            {"type": "hero-number", "kicker": "Revenue per $1 of ad spend", "value": "$3.10",
             "label": "Up from $2.70 in August. The best month this year.", "delta_label": "+$0.40", "delta_direction": "up",
             "spark": [2.1, 2.3, 2.2, 2.5, 2.6, 2.7, 3.1]},
            {"type": "section-header", "number": "05", "kicker": "Next steps", "title": "What to do in *October*."},
            {"type": "recommendations", "items": [
                {"label": "This week", "title": "Move $2,000 to *emergency* search terms", "body": "They convert at 9.8% and cost $19 per lead. Expect about 18 extra patients.", "impact": "High", "effort": "Low"},
                {"label": "This week", "title": "Call every lead within *5 minutes*", "body": "Fast follow-up books 61% of leads vs 38% after an hour.", "impact": "High", "effort": "Medium"},
                {"label": "This month", "title": "Turn on Meta *click ID* capture", "body": "Only 41% of Meta leads carry fbclid, so Meta optimizes on guesses.", "impact": "Medium", "effort": "Low"},
                {"label": "Next month", "title": "Pause broad match *implant* terms", "body": "$61 per lead with a 9% booking rate. Rebuild with exact match.", "impact": "Medium", "effort": "Low"}]},
            {"type": "notes", "items": [
                "Spend pulled from Google Ads and Meta Ads for Sep 1 to Sep 30, 2026.",
                "Leads matched to campaigns by utm_campaign, then by click ID when the campaign tag was missing.",
                "Revenue is the WooCommerce order total, credited to the lead's first touch."]},
            {"type": "closing", "kicker": "The month in one line",
             "title": "Next: move $2,000 into *emergency search*. It books patients at $156 each.",
             "summary_stats": [{"value": "1,186", "label": "Leads"}, {"value": "214", "label": "New patients"},
                               {"value": "$86K", "label": "Revenue"}, {"value": "3.1x", "label": "ROAS"}],
             "bullets": ["Google search drove 41% of new patients.", "Meta retargeting found the cheapest leads at $14.",
                         "Fix Meta click ID capture before October's budget review."]},
        ],
    }


def edge_cases():
    """Summaries that stress layout: long labels, tiny numbers, light brand."""
    long_brand = {"company_name": "The Extraordinarily Long Named Family Law Practice of Westchester County",
                  "logo": {"type": "text", "value": "The Extraordinarily Long Named Family Law Practice"},
                  "colors": {"primary": "#F5C400", "accent": "#111111", "ink": "#111111", "muted": "#555555", "surface": "#FFF9E0"}}
    s = kitchen_sink(long_brand)
    s["sections"][0]["title"] = "A remarkably long report title that keeps going to test how the *cover* wraps across several lines without breaking"
    s["sections"][1]["stats"][0]["value"] = "1,234,567"
    s["sections"][1]["stats"][1]["value"] = "$12,345.67"
    rl = next(x for x in s["sections"] if x["type"] == "ranked-list")
    rl["rows"][0]["platform"] = "Google Ads Performance Max with a very long campaign name"
    tiny = {"meta": copy.deepcopy(s["meta"]), "sections": [
        {"type": "title-block", "kicker": "Weekly summary · Oct 1 to Oct 7", "title": "A quiet *week*.", "meta_bits": ["3 leads"]},
        {"type": "stat-strip", "stats": [{"label": "Leads", "value": "3", "delta_label": "−50%", "delta_direction": "down"},
                                         {"label": "Top source", "value": "google"}]},
        {"type": "chart", "chart": {"type": "bar-vertical", "labels": ["Mon", "Tue", "Wed"], "values": [1, 0, 2]}},
        {"type": "chart", "chart": {"type": "doughnut", "labels": ["Direct"], "values": [3]}},
        {"type": "closing", "title": "Check *tracking* and try again.", "body": "Low volume weeks happen."}]}
    tiny["meta"]["brand_profile"] = {"company_name": "Tiny", "logo": {"type": "text", "value": "Tiny"},
                                     "colors": {"primary": "#111111", "accent": "#888888"}}
    return {"long": s, "tiny": tiny}
