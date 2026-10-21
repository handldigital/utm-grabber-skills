/* UTM Grabber live dashboard.
   The page renders from the snapshot embedded at publish time, then pulls fresh
   leads through the viewer's own UTM Grabber connection (the claude.ai Artifact
   `mcp` capability) and recomputes every number in the page. Only dates and
   attribution fields are kept: no names, emails, phones or IP addresses.
   Markup and classes match the report engine, so the theme CSS styles it. */
(function () {
  "use strict";
  var CFG = JSON.parse(document.getElementById("live-config").textContent);
  var TH = CFG.theme, TK = TH.tokens, KEY = TH.key, SERVER = CFG.server;
  var SNAP = CFG.snapshot || {entries: []};
  var MINUS = "−";
  var WINDOWS = [{k: "today", days: 1, label: "Today"}, {k: "7", days: 7, label: "7 days"},
                 {k: "30", days: 30, label: "30 days"}, {k: "90", days: 90, label: "90 days"}];
  var MAX_PAGES = 30, PER_PAGE = 100, REFRESH_MS = 15 * 60 * 1000;
  var CACHE = {staleTime: 300000, gcTime: 86400000};

  // ------------------------------------------------------------- text + numbers
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c];
    });
  }
  function trim(x, d) { var s = x.toFixed(d); return s.indexOf(".") >= 0 ? s.replace(/0+$/, "").replace(/\.$/, "") : s; }
  function commas(n) { return Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ","); }
  function compact(n) {
    var a = Math.abs(n), s;
    if (a >= 1e9) s = trim(a / 1e9, 1) + "B";
    else if (a >= 1e6) s = trim(a / 1e6, 1) + "M";
    else if (a >= 1e4) s = trim(a / 1e3, 1) + "K";
    else if (a === Math.round(a)) s = commas(a);
    else s = commas(Math.floor(a)) + "." + a.toFixed(1).split(".")[1];
    return (n < 0 ? MINUS : "") + s;
  }
  function pct(n, d) { return (n < 0 ? MINUS : "") + trim(Math.abs(n), d || 0) + "%"; }
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function ymd(d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
  function dayAdd(d, n) { return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n); }
  function parseDay(s) { var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s || ""); return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null; }
  function parseTime(s) {
    var m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?/.exec(s || "");
    if (m) return new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0));
    return parseDay(s);
  }
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function shortDay(d) { return MONTHS[d.getMonth()] + " " + d.getDate(); }
  function longDay(d) { return MONTHS[d.getMonth()] + " " + d.getDate() + ", " + d.getFullYear(); }
  function clock(d) { var h = d.getHours(), m = d.getMinutes(); return (h % 12 || 12) + ":" + pad(m) + (h < 12 ? "am" : "pm"); }
  function hourLabel(h) { return h === 0 ? "12am" : h < 12 ? h + "am" : h === 12 ? "12pm" : (h - 12) + "pm"; }
  function plural(n, w) { return compact(n) + " " + w + (n === 1 ? "" : "s"); }

  // Titles carry one accent, styled per theme (ledger keeps them plain).
  function title(text) {
    return String(text).split(/(\*[^*]+\*)/).map(function (p) {
      if (p.length > 2 && p.charAt(0) === "*" && p.charAt(p.length - 1) === "*") {
        return TH.accent === "plain" ? esc(p.slice(1, -1)) : '<em class="acc">' + esc(p.slice(1, -1)) + "</em>";
      }
      return esc(p);
    }).join("");
  }

  var canvas = document.createElement("canvas").getContext("2d");
  function tw(s, size, font, weight, italic) {
    canvas.font = (italic ? "italic " : "") + (weight || 400) + " " + size + "px " + font;
    return canvas.measureText(String(s)).width;
  }
  function vw(value) {   // measured width in em, for the KPI auto-fit CSS
    var f = TH.fonts.numeral;
    return Math.max(0.6, tw(value, 100, f.css, f.weight, f.italic) / 100).toFixed(3);
  }

  // ------------------------------------------------------------- reading the connector
  function jsonAt(text, start) {   // the JSON value that begins exactly at text[start]
    var open = text.charAt(start), close = open === "[" ? "]" : "}", depth = 0, inStr = false;
    for (var i = start; i < text.length; i++) {
      var c = text.charAt(i);
      if (inStr) { if (c === "\\") i++; else if (c === '"') inStr = false; continue; }
      if (c === '"') inStr = true;
      else if (c === "[" || c === "{") depth++;
      else if (c === "]" || c === "}") { depth--; if (depth === 0) { try { return JSON.parse(text.slice(start, i + 1)); } catch (e) { return null; } } }
    }
    return null;
  }
  function pageText(result) {
    if (result && typeof result.payload === "string") return result.payload;
    var blocks = (result && result.content) || [];
    return blocks.filter(function (b) { return b && b.type === "text"; }).map(function (b) { return b.text; }).join("\n");
  }
  function readPage(result) {   // -> {entries, labels, total, totalPages}
    var p = result && result.payload;
    if (p && typeof p === "object" && !Array.isArray(p) && Array.isArray(p.entries)) {
      return {entries: p.entries, labels: p.field_labels || {}, total: +(p.total || p.entries.length),
              totalPages: +(p.total_pages || 1)};
    }
    var text = pageText(result), entries = [], labels = {};
    var at = text.lastIndexOf("Entries:"), from = at >= 0 ? at + 8 : 0, b = text.indexOf("[", from);
    if (b >= 0) entries = jsonAt(text, b) || [];
    var fl = /[Ff]ield labels/.exec(text);
    if (fl) { var c = text.indexOf("{", fl.index + fl[0].length); if (c >= 0) labels = jsonAt(text, c) || {}; }
    var m = /Page\s+(\d+)\s+of\s+(\d+)\s*\(\s*(\d+)\s+per page,\s*([\d,]+)\s+total/i.exec(text);
    var total = m ? +m[4].replace(/,/g, "") : entries.length;
    if (!m) { var t = /([\d,]+)\s+total matching/i.exec(text); if (t) total = +t[1].replace(/,/g, ""); }
    return {entries: Array.isArray(entries) ? entries : [], labels: labels, total: total, totalPages: m ? +m[2] : 1};
  }
  function field(e, keys) {
    for (var i = 0; i < keys.length; i++) {
      var v = e[keys[i]];
      if (v !== undefined && v !== null && String(v).trim() !== "") return String(v).trim();
    }
    return "";
  }
  function slim(raw, labels) {   // named keys (field_labels applied), then attribution fields only
    var fid = String(raw.form_id || raw["Form ID"] || "");
    var map = (labels && labels[fid]) || {}, e = {};
    Object.keys(raw).forEach(function (k) { e[map[k] || k] = raw[k]; });
    var url = field(e, ["Source URL", "source_url"]), path = url;
    try { if (url) path = new URL(url, "https://x.invalid").pathname || "/"; } catch (err) { path = url; }
    return {d: field(e, ["Date Created", "date_created"]), s: field(e, ["utm_source (HandL)", "utm_source"]).toLowerCase(),
            m: field(e, ["utm_medium (HandL)", "utm_medium"]).toLowerCase(),
            c: field(e, ["utm_campaign (HandL)", "utm_campaign"]),
            ts: field(e, ["traffic_source (HandL)", "traffic_source"]).toLowerCase(),
            g: field(e, ["gclid (HandL)", "gclid"]) ? 1 : 0, f: field(e, ["fbclid (HandL)", "fbclid"]) ? 1 : 0,
            k: field(e, ["msclkid (HandL)", "msclkid"]) ? 1 : 0,
            rf: field(e, ["referrer (first touch, HandL)", "referrer"]) ? 1 : 0, u: path, fm: fid};
  }

  // Channel rules match helpers.classify_traffic_source in the report engine.
  var PAID = toSet("cpc ppc paid paid_search paid_social paidsocial display cpm cpv paid_video paidvideo paid-social paid-search banner retargeting");
  var SOCIAL = toSet("social organic_social"), EMAIL = toSet("email newsletter e-mail"), REFERRAL = toSet("referral partner");
  var SEARCH = toSet("google bing duckduckgo yahoo ecosia brave");
  function toSet(s) { var o = {}; s.split(" ").forEach(function (w) { o[w] = 1; }); return o; }
  function channel(e) {
    if (["paid", "organic", "social", "referral", "direct"].indexOf(e.ts) >= 0) return e.ts.charAt(0).toUpperCase() + e.ts.slice(1);
    if (e.g || e.k) return "Paid";
    if (e.f) return PAID[e.m] ? "Paid" : "Social";
    if (PAID[e.m]) return "Paid";
    if (SOCIAL[e.m]) return "Social";
    if (EMAIL[e.m] || REFERRAL[e.m]) return "Referral";
    if (SEARCH[e.s]) return "Organic";
    return e.rf ? "Referral" : "Direct";
  }
  var KNOWN = {google: "Google", facebook: "Facebook", instagram: "Instagram", linkedin: "LinkedIn", bing: "Bing",
               youtube: "YouTube", tiktok: "TikTok", newsletter: "Newsletter", chatgpt: "ChatGPT", "chatgpt.com": "ChatGPT",
               perplexity: "Perplexity", x: "X", twitter: "X (Twitter)", email: "Email", hubspot: "HubSpot", meta: "Meta"};
  function pretty(s, fallback) {
    s = String(s || "").trim();
    if (!s) return fallback || "(not set)";
    return s.replace(/[_-]/g, " ").split(/\s+/).map(function (w, i) {
      if (w === w.toUpperCase() && /[A-Z]/.test(w) && w.length <= 4) return w;
      if (/\d/.test(w) && w.length <= 4) return w.toUpperCase();
      return i === 0 ? w.charAt(0).toUpperCase() + w.slice(1).toLowerCase() : w.toLowerCase();
    }).join(" ");
  }
  function sourceName(s) { return s ? (KNOWN[s] || pretty(s)) : "No source tag"; }

  // ------------------------------------------------------------- windows + numbers
  function winOf(k) { for (var i = 0; i < WINDOWS.length; i++) if (WINDOWS[i].k === k) return WINDOWS[i]; return WINDOWS[1]; }
  function span(win, today) {
    var start = dayAdd(today, -(win.days - 1)), pend = dayAdd(start, -1);
    return {start: start, end: today, pstart: dayAdd(pend, -(win.days - 1)), pend: pend};
  }
  function inDays(e, a, b) { var d = parseDay(e.d); return d && d >= a && d <= b; }
  function periodName(win) { return win.k === "today" ? "today" : "the last " + win.days + " days"; }
  function priorName(win) { return win.k === "today" ? "yesterday" : "the " + win.days + " days before"; }

  function compute(entries, win, sp, total, prior) {
    var n = entries.length, per = [], labels = [], byDay = {}, hourly = win.k === "today";
    var chans = {Paid: 0, Organic: 0, Social: 0, Referral: 0, Direct: 0}, srcs = {}, camps = {}, pages = {}, tagged = 0;
    if (hourly) { for (var h = 0; h < 24; h++) { per.push(0); labels.push(hourLabel(h)); } }
    else { for (var d = new Date(sp.start); d <= sp.end; d = dayAdd(d, 1)) { byDay[ymd(d)] = per.length; per.push(0); labels.push(shortDay(d)); } }
    entries.forEach(function (e) {
      var t = parseTime(e.d);
      if (t) { if (hourly) per[t.getHours()]++; else if (byDay[ymd(t)] !== undefined) per[byDay[ymd(t)]]++; }
      chans[channel(e)]++;
      srcs[e.s] = (srcs[e.s] || 0) + 1;
      if (e.c) camps[e.c] = (camps[e.c] || 0) + 1;
      pages[e.u || "/"] = (pages[e.u || "/"] || 0) + 1;
      if (e.s && e.m && e.c) tagged++;
    });
    if (hourly) {   // today: stop the line at the current hour
      var lastH = 23;
      if (ymd(sp.end) === ymd(new Date())) lastH = new Date().getHours();
      per = per.slice(0, lastH + 1); labels = labels.slice(0, lastH + 1);
    }
    function top(o, k) { return Object.keys(o).map(function (x) { return [x, o[x]]; }).sort(function (a, b) { return b[1] - a[1]; }).slice(0, k); }
    var latest = entries.slice().sort(function (a, b) { return (parseTime(b.d) || 0) - (parseTime(a.d) || 0); }).slice(0, 8);
    var todayCount = 0, todayKey = ymd(sp.end);
    entries.forEach(function (e) { var t = parseDay(e.d); if (t && ymd(t) === todayKey) todayCount++; });
    return {win: win, sp: sp, n: n, total: Math.max(total || 0, n), prior: prior, per: per, labels: labels, chans: chans,
            sources: top(srcs, 6), campaigns: top(camps, 8), pages: top(pages, 6), tagged: tagged, latest: latest,
            today: todayCount, capped: (total || 0) > n};
  }

  // ------------------------------------------------------------- charts (same geometry as the engine)
  function f1(x) { return (Math.round(x * 10) / 10).toString(); }
  function ticksFor(vmax) {
    if (!(vmax > 0)) vmax = 1;
    var raw = vmax / 5, mag = Math.pow(10, Math.floor(Math.log10(raw))), step = mag;
    var ms = [1, 2, 2.5, 5, 10];
    for (var i = 0; i < ms.length; i++) { step = ms[i] * mag; if (vmax / step <= 5) break; }
    var out = [], hi = Math.ceil(vmax / step) * step;
    for (var t = 0; t <= hi + step * 0.001; t += step) out.push(Math.round(t * 1e6) / 1e6);
    return out;
  }
  function spark(values, color) {
    if (!values || values.length < 2) return "";
    var w = 160, h = 36, p = 3.5, lo = Math.min.apply(null, values), hi = Math.max.apply(null, values), sp = (hi - lo) || 1, n = values.length;
    var X = function (i) { return p + (w - 2 * p) * i / (n - 1); }, Y = function (v) { return p + (h - 2 * p) * (1 - (v - lo) / sp); };
    var d = "M" + values.map(function (v, i) { return f1(X(i)) + " " + f1(Y(v)); }).join(" L");
    return '<svg class="spark" viewBox="0 0 ' + w + " " + h + '" width="' + w + '" height="' + h + '" aria-hidden="true" preserveAspectRatio="none">' +
      '<path d="' + d + " L" + f1(X(n - 1)) + " " + h + " L" + f1(X(0)) + " " + h + 'Z" fill="' + color + '" fill-opacity="0.12"/>' +
      '<path d="' + d + '" fill="none" stroke="' + color + '" stroke-width="1.75" stroke-linejoin="round" stroke-linecap="round"/>' +
      '<circle cx="' + f1(X(n - 1)) + '" cy="' + f1(Y(values[n - 1])) + '" r="3" fill="' + color + '" stroke="' + TK.panel + '" stroke-width="1.5"/></svg>';
  }
  function lineChart(labels, values, ref, width, height) {
    var size = TH.chartSize, font = TH.fonts.chart.css, wt = TH.fonts.chart.weight || 400, n = values.length;
    var col = TK.series[0], txt = function (x, y, s, cls, anchor, fill, sz) {
      return '<text x="' + f1(x) + '" y="' + f1(y) + '" class="' + cls + '"' + (anchor !== "start" ? ' text-anchor="' + anchor + '"' : "") +
        ' fill="' + fill + '" font-size="' + f1(sz || size) + '">' + esc(s) + "</text>";
    };
    if (!n) return "";
    var vmax = Math.max.apply(null, values.concat(ref ? [ref.value] : [0]));
    var ticks = ticksFor(vmax > 0 ? vmax * 1.1 : 1), top = size * 2.2, bottom = size * 2.6;
    var left = Math.max.apply(null, ticks.map(function (t) { return tw(compact(t), size, font, wt); })) + 12;
    var right = ref ? Math.max(12, tw(ref.label, size, font, wt) + 22) : 12;
    var pw = width - left - right, ph = height - top - bottom, t1 = ticks[ticks.length - 1];
    var Y = function (v) { return top + ph * (1 - v / (t1 || 1)); }, X = function (i) { return left + (n > 1 ? pw * i / (n - 1) : pw / 2); };
    var body = [];
    ticks.forEach(function (t) {
      body.push('<line x1="' + f1(left) + '" x2="' + f1(left + pw) + '" y1="' + f1(Y(t)) + '" y2="' + f1(Y(t)) + '" stroke="' + (t === 0 ? TK.axis : TK.grid) + '" stroke-width="1"/>');
      body.push(txt(left - 8, Y(t) + size * 0.35, compact(t), "ct ct-tick", "end", TK.chart_text));
    });
    var pts = values.map(function (v, i) { return [X(i), Y(v), v, i]; });
    var d = "M" + pts.map(function (p) { return f1(p[0]) + " " + f1(p[1]); }).join(" L");
    if (!ref) body.push('<path d="M' + f1(pts[0][0]) + " " + f1(Y(0)) + " L" + pts.map(function (p) { return f1(p[0]) + " " + f1(p[1]); }).join(" L") +
      " L" + f1(pts[n - 1][0]) + " " + f1(Y(0)) + 'Z" fill="' + col + '" fill-opacity="0.10"/>');
    if (ref) {
      body.push('<line x1="' + f1(left) + '" x2="' + f1(left + pw) + '" y1="' + f1(Y(ref.value)) + '" y2="' + f1(Y(ref.value)) +
        '" stroke="' + TK.neutral + '" stroke-width="2" stroke-dasharray="5 5"/>');
      body.push(txt(left + pw + 10, Y(ref.value) + size * 0.35, ref.label, "ct ct-end", "start", TK.ink2));
    }
    if (n > 1) body.push('<path d="' + d + '" fill="none" stroke="' + col + '" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>');
    pts.forEach(function (p) { body.push('<circle cx="' + f1(p[0]) + '" cy="' + f1(p[1]) + '" r="9" fill="transparent" data-tip="' + esc(labels[p[3]] + ": " + compact(p[2])) + '"/>'); });
    var last = pts[n - 1];
    body.push('<circle cx="' + f1(last[0]) + '" cy="' + f1(last[1]) + '" r="4.5" fill="' + col + '" stroke="' + TK.panel + '" stroke-width="2"/>');
    body.push(txt(last[0] - 2, last[1] - 12, compact(last[2]), "ct ct-val ct-strong", "end", TK.ink));
    if (n > 4) {
      var pk = pts.reduce(function (a, b) { return b[2] > a[2] ? b : a; });
      if (pk[3] !== n - 1 && pk[3] !== 0 && pk[2] > 0) {
        var lab = "Peak " + compact(pk[2]) + " on " + labels[pk[3]], w = tw(lab, size * 0.95, font, wt);
        body.push('<circle cx="' + f1(pk[0]) + '" cy="' + f1(pk[1]) + '" r="4.5" fill="' + col + '" stroke="' + TK.panel + '" stroke-width="2"/>');
        body.push(txt(Math.min(Math.max(pk[0], left + w / 2), left + pw - w / 2), pk[1] - 12, lab, "ct ct-note", "middle", TK.ink2, size * 0.95));
      }
    }
    // x labels at an even stride; first and last always shown
    var widest = Math.max.apply(null, labels.map(function (l) { return tw(l, size, font, wt); })), gap = size * 1.1;
    var step = n > 1 ? (X(n - 1) - X(0)) / (n - 1) : widest, stride = 1;
    while (stride < n && step * stride < widest + gap) stride++;
    var idx = [];
    for (var i = 0; i < n; i += stride) idx.push(i);
    if (idx[idx.length - 1] !== n - 1) {
      while (idx.length && X(n - 1) - tw(labels[n - 1], size, font, wt) - gap < X(idx[idx.length - 1]) + tw(labels[idx[idx.length - 1]], size, font, wt) / 2) idx.pop();
      idx.push(n - 1);
    }
    idx.forEach(function (j) {
      body.push(txt(X(j), height - bottom + size * 1.55, labels[j], "ct ct-x", j === 0 ? "start" : j === n - 1 ? "end" : "middle", TK.chart_text));
    });
    return '<svg class="chart-svg" viewBox="0 0 ' + width + " " + height + '" width="' + width + '" height="' + height +
      '" role="img" aria-label="Leads over time" preserveAspectRatio="xMidYMid meet">' + body.join("") + "</svg>";
  }

  // ------------------------------------------------------------- page sections (engine markup)
  function delta(lab, dir, good, vs) {
    if (!lab && dir === "flat") return "";
    var tone = dir === "flat" ? "flat" : (good === "neutral" ? "neutral" : (dir === good ? "good" : "bad"));
    if (KEY === "studio") {
      var plain = lab === "New" ? "New: none in " + vs : (dir === "up" ? "Up " : dir === "down" ? "Down " : "Flat ") +
        (dir === "flat" ? "vs " + vs : lab.replace(/^[+−-]/, "") + " from " + vs);
      var m = /^(.*?)\s+((?:from|vs|none in)\s.*)$/.exec(plain);
      return '<p class="delta ' + dir + " " + tone + '"><span class="arw">' + ({up: "↑", down: "↓"}[dir] || "→") +
        '</span><span class="dtx">' + (m ? '<span class="dm">' + esc(m[1]) + '</span> <span class="dvs">' + esc(m[2]) + "</span>" : esc(plain)) + "</span></p>";
    }
    if (KEY === "classic") return dir === "flat" ? '<span class="delta flat ' + tone + '"></span>' : '<span class="delta ' + dir + " " + tone + '">' + esc(lab) + "</span>";
    return '<p class="delta ' + dir + " " + tone + '"><span class="arw">' + ({up: "▲", down: "▼"}[dir] || "●") +
      '</span><span class="dv">' + esc(dir === "flat" ? "Flat" : lab) + '</span><span class="vs">vs ' + esc(vs) + "</span></p>";
  }
  function kpis(stats) {
    var out = ['<section class="s s-kpis d-kpis n' + stats.length + '">'];
    stats.forEach(function (st, i) {
      var dl = st.delta ? delta(st.delta[0], st.delta[1], st.delta[2], st.delta[3]) : "";
      if (KEY === "classic") {
        out.push('<div class="kpi"><div class="kpi-value" style="--vw:' + vw(st.value) + '">' + esc(st.value) + '</div><div class="kpi-foot"><span class="kpi-label">' +
          esc(st.label) + "</span>" + dl + "</div></div>");
        return;
      }
      var lead = KEY === "boardroom" && i === 0 && stats.length >= 4 ? " kpi-lead" : "";
      var sp = st.spark ? '<div class="kpi-spark">' + spark(st.spark, TK.dark ? TK.brand_ink : TK.series[0]) + "</div>" : "";
      out.push('<div class="kpi' + lead + '"><div class="kpi-head"><p class="kpi-label">' + esc(st.label) + '</p></div><p class="kpi-value" style="--vw:' +
        vw(st.value) + '">' + esc(st.value) + "</p>" + dl + sp + (st.note ? '<p class="kpi-note">' + esc(st.note) + "</p>" : "") + "</div>");
    });
    out.push("</section>");
    return out.join("");
  }
  function barList(rows, total) {
    var max = Math.max.apply(null, rows.map(function (r) { return r[1]; }).concat([1]));
    return '<div class="viz viz-barlist"><ol class="barlist">' + rows.map(function (r) {
      return '<li class="bl-row" data-tip="' + esc(r[0] + ": " + compact(r[1])) + '"><span class="bl-label">' + esc(r[0]) +
        '</span><span class="bl-track"><span class="bl-fill" style="width:' + (100 * r[1] / max).toFixed(2) + '%"></span></span><span class="bl-val">' +
        esc(compact(r[1])) + '<span class="bl-share">' + esc(pct(total ? 100 * r[1] / total : 0)) + "</span></span></li>";
    }).join("") + "</ol></div>";
  }
  function table(cols, rows) {
    return '<section class="s s-table"><div class="tbl-wrap"><table class="tbl"><thead><tr>' + cols.map(function (c) {
      return '<th class="c-' + c[1] + (c[2] ? " a-" + c[2] : "") + '">' + esc(c[0]) + "</th>";
    }).join("") + "</tr></thead><tbody>" + rows.map(function (r) {
      return "<tr>" + r.map(function (v, i) { return '<td class="c-' + cols[i][1] + (cols[i][2] ? " a-" + cols[i][2] : "") + '">' + v + "</td>"; }).join("") + "</tr>";
    }).join("") + "</tbody></table></div></section>";
  }
  function panel(span, kicker, head, inner, extra) {
    return '<article class="panel span-' + span + " " + (span < 8 ? "p-narrow" : "p-wide") + (extra ? " " + extra : "") + '"><header class="p-head">' +
      (kicker ? '<p class="p-kicker">' + esc(kicker) + "</p>" : "") + '<h2 class="p-title">' + title(head) + "</h2></header>" + inner + "</article>";
  }
  var DASH_W = 1312, GAP = 16, PAD = 20;
  function innerW(span) { var col = (DASH_W - 11 * GAP) / 12; return Math.round(span * col + (span - 1) * GAP - 2 * PAD); }

  function dashboard(R, source) {
    var win = R.win, pName = periodName(win), vs = priorName(win), total = R.total;
    var dir = "flat", dlab = "", good = "up";
    if (R.prior != null && win.k !== "today") {
      if (R.prior === 0) { dir = total > 0 ? "up" : "flat"; dlab = total > 0 ? "New" : ""; }
      else { var ch = 100 * (total - R.prior) / R.prior; dir = Math.abs(ch) < 0.5 ? "flat" : ch > 0 ? "up" : "down"; dlab = dir === "flat" ? "Flat" : (ch > 0 ? "+" : MINUS) + trim(Math.abs(ch), 0) + "%"; }
    }
    var paid = R.n ? 100 * R.chans.Paid / R.n : 0, tag = R.n ? 100 * R.tagged / R.n : 0, topSrc = R.sources[0];
    var perDay = win.k === "today" ? null : total / win.days;
    var head;
    if (!total) head = "No leads " + pName + " *yet*.";
    else if (win.k === "today") head = "*" + plural(total, "lead") + "* so far today.";
    else if (dir === "flat" || R.prior == null || dlab === "New") head = "*" + plural(total, "lead") + "* in " + pName + ".";
    else head = "*" + plural(total, "lead") + "* in " + pName + ", " + trim(Math.abs(100 * (total - R.prior) / R.prior), 0) + "% " + (dir === "up" ? "more" : "fewer") + " than " + vs + ".";
    var dek = [];
    if (topSrc && R.n) dek.push(sourceName(topSrc[0]) + " sent the most (" + compact(topSrc[1]) + ", " + pct(100 * topSrc[1] / R.n) + ").");
    if (R.n) dek.push(pct(tag) + " arrived fully tagged.");
    if (R.capped) dek.push("Charts use the latest " + compact(R.n) + " of " + compact(total) + " leads; pick a shorter window to see them all.");
    var stats = [
      {label: win.k === "today" ? "Leads today" : "Leads", value: compact(total), delta: dlab ? [dlab, dir, good, vs] : null,
       spark: win.k === "today" ? null : R.per, note: win.k === "today" && R.prior != null ? "Yesterday: " + compact(R.prior) : null},
      win.k === "today" ? {label: "Busiest hour", value: R.n ? hourLabel(R.per.indexOf(Math.max.apply(null, R.per))) : "–"}
                        : {label: "Leads per day", value: trim(perDay, perDay < 10 ? 1 : 0), note: R.prior != null ? "Before: " + trim(R.prior / win.days, R.prior / win.days < 10 ? 1 : 0) + " a day" : null},
      {label: "Paid share", value: pct(paid), note: compact(R.chans.Paid) + " paid leads"},
      {label: "Fully tagged", value: pct(tag), note: "source, medium and campaign"},
      {label: "Top source", value: topSrc ? sourceName(topSrc[0]) : "–", note: topSrc && R.n ? pct(100 * topSrc[1] / R.n) + " of leads" : null}
    ];
    var w8 = innerW(8), chartH = 250;
    var ref = R.prior != null && win.k !== "today" ? {value: R.prior / win.days, label: "Before: " + trim(R.prior / win.days, R.prior / win.days < 10 ? 1 : 0) + "/day"} : null;
    var chart = R.n ? '<div class="viz viz-line"><div class="v-wide">' + lineChart(R.labels, R.per, ref, w8, chartH) + '</div><div class="v-narrow">' +
      lineChart(R.labels, R.per, ref, 340, 230) + "</div></div>" : '<p class="lv-empty">No leads in this window yet.</p>';
    var chOrder = ["Paid", "Organic", "Social", "Referral", "Direct"].map(function (c) { return [c, R.chans[c]]; }).filter(function (r) { return r[1] > 0; })
      .sort(function (a, b) { return b[1] - a[1]; });
    var srcRows = R.sources.map(function (r) { return [sourceName(r[0]), r[1]]; });
    var campRows = R.campaigns.map(function (r, i) {
      return ['<span class="lv-rank">' + (i + 1) + "</span>", esc(pretty(r[0])), '<span class="lv-mono">' + esc(r[0]) + "</span>", esc(compact(r[1])), esc(pct(R.n ? 100 * r[1] / R.n : 0))];
    });
    var latestRows = R.latest.map(function (e) {
      var t = parseTime(e.d);
      return [esc(t ? (ymd(t) === ymd(R.sp.end) ? "Today " + clock(t) : shortDay(t) + ", " + clock(t)) : ""),
              '<span class="pill badge neutral">' + esc(channel(e)) + "</span>",
              esc(e.s || e.m ? (sourceName(e.s) + (e.m ? " / " + e.m : "")) : "No tags"), esc(e.c ? pretty(e.c) : "–"), '<span class="lv-mono">' + esc(e.u || "/") + "</span>"];
    });
    var panels = [
      panel(8, win.k === "today" ? "Today, by hour" : "Leads per day", "When leads *arrived*.", chart),
      panel(4, "Channel mix", "Where they *came from*.", R.n ? barList(chOrder, R.n) : '<p class="lv-empty">No leads yet.</p>'),
      panel(4, "Sources", "Top *sources*.", srcRows.length ? barList(srcRows, R.n) : '<p class="lv-empty">No leads yet.</p>'),
      panel(8, "Campaigns", "Top *campaigns*.", campRows.length ? table([["#", "rank"], ["Campaign", "name"], ["utm_campaign", "source"], ["Leads", "number", "right"], ["Share", "pct", "right"]], campRows)
        : '<p class="lv-empty">No campaign tags in this window.</p>'),
      panel(8, "Latest", "The newest *leads*.", latestRows.length ? table([["When", "text"], ["Channel", "badge"], ["Source / medium", "name"], ["Campaign", "text"], ["Landing page", "source"]], latestRows)
        : '<p class="lv-empty">No leads yet.</p>'),
      panel(4, "Landing pages", "Pages that *convert*.", R.pages.length ? barList(R.pages, R.n) : '<p class="lv-empty">No leads yet.</p>')
    ];
    return {head: head, dek: dek.join(" "), kpis: kpis(stats), grid: panels.join("")};
  }

  // ------------------------------------------------------------- the page
  var root = document.getElementById("live-root");
  var els = {
    h1: root.querySelector(".d-h1"), dek: root.querySelector(".d-dek"), body: root.querySelector(".lv-body"),
    period: root.querySelector(".d-period"), status: root.querySelector(".lv-status"), msg: root.querySelector(".lv-msg"),
    refresh: root.querySelector(".lv-refresh"), tabs: root.querySelectorAll(".lv-tab")
  };
  var state = {win: CFG.window || "7", mode: "snapshot", live: {}, at: {}, busy: false, mcp: null, lastAttempt: 0};

  function snapToday() { return parseDay(SNAP.to) || new Date(); }
  function snapCovers(win) {
    var sp = span(win, snapToday()), from = parseDay(SNAP.from);
    return {ok: !!from && from <= sp.start, prior: !!from && from <= sp.pstart, sp: sp};
  }
  function snapshotView(win) {
    var cov = snapCovers(win), sp = cov.sp;
    var cur = SNAP.entries.filter(function (e) { return inDays(e, sp.start, sp.end); });
    var prior = cov.prior ? SNAP.entries.filter(function (e) { return inDays(e, sp.pstart, sp.pend); }).length : null;
    return compute(cur, win, sp, cur.length, prior);
  }
  function paint(R) {
    var v = dashboard(R);
    els.h1.innerHTML = title(v.head);
    els.dek.textContent = v.dek;
    els.period.textContent = R.win.k === "today" ? longDay(R.sp.end) : shortDay(R.sp.start) + " to " + shortDay(R.sp.end);
    els.body.innerHTML = v.kpis + '<div class="d-grid">' + v.grid + "</div>";
    Array.prototype.forEach.call(els.tabs, function (b) { b.setAttribute("aria-pressed", b.dataset.win === R.win.k ? "true" : "false"); });
  }
  function ago(ms) {
    var s = Math.max(0, Math.round((Date.now() - ms) / 1000));
    if (s < 60) return "just now";
    var m = Math.round(s / 60);
    if (m < 60) return m + " min ago";
    var h = Math.round(m / 60);
    return h < 24 ? h + (h === 1 ? " hour ago" : " hours ago") : longDay(new Date(ms));
  }
  function setStatus() {
    var s = els.status, at = state.at[state.win];
    s.classList.remove("is-live", "is-snap", "is-busy");
    if (state.busy) { s.classList.add("is-busy"); s.textContent = "Getting live numbers"; return; }
    if (state.mode === "live" && at) { s.classList.add("is-live"); s.textContent = (CFG.demo ? "Live demo, updated " : "Live, updated ") + ago(at); return; }
    s.classList.add("is-snap");
    s.textContent = "Numbers from " + longDay(new Date(SNAP.at || SNAP.to));
  }
  function setMsg(text, tone) {
    if (!text) { els.msg.hidden = true; els.msg.textContent = ""; return; }
    els.msg.hidden = false;
    els.msg.className = "lv-msg tone-" + (tone || "info");
    els.msg.textContent = text;
  }
  var COPY = {
    needs_reauth: "Reconnect " + SERVER + " in claude.ai Settings > Connectors, then press Refresh to see live numbers.",
    server_not_connected: "Add " + SERVER + " in claude.ai Settings > Connectors to see live numbers. Until then this page shows saved numbers.",
    selection_required: "You have more than one " + SERVER + " connection. Pick one when claude.ai asks, then press Refresh.",
    not_in_manifest: "This page isn't allowed to use " + SERVER + " for you, so it shows saved numbers. Reload the page to be asked again.",
    consent_required: "Allow " + SERVER + " for this page to see live numbers, then press Refresh.",
    blocked_by_policy: "Your organization's settings don't let this page use " + SERVER + ". It shows saved numbers.",
    approval_required: "Your organization needs to approve " + SERVER + " for pages like this one. It shows saved numbers.",
    server_unavailable: "Your site didn't answer just now. Press Refresh in a minute.",
    no_mcp: "Live numbers load when this page is opened on claude.ai while you're signed in. It shows saved numbers.",
    no_config: "This page wasn't set up with your forms, so it shows saved numbers. Ask Claude to rebuild it from a chat where " + SERVER + " is connected.",
    other: "Live numbers didn't load just now. Press Refresh to try again."
  };
  var DENIALS = {needs_reauth: 1, server_not_connected: 1, blocked_by_policy: 1, approval_required: 1, not_in_manifest: 1, selection_required: 1, consent_required: 1};

  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function call(input, refresh) {
    var opts = {cache: refresh ? {staleTime: CACHE.staleTime, gcTime: CACHE.gcTime, refresh: true} : CACHE};
    return state.mcp.callTool(SERVER, "get_entries", input, opts).catch(function (e) {
      if (e && e.retryable) return sleep(e.retryAfterMs || 700 + Math.random() * 900).then(function () { return state.mcp.callTool(SERVER, "get_entries", input, opts); });
      throw e;
    });
  }
  function fetchWindow(win, refresh) {
    var sp = span(win, new Date());
    var base = {selected_form_plugin: CFG.form_plugin, selected_form_ids: CFG.form_ids, selected_start_date: ymd(sp.start), selected_end_date: ymd(sp.end)};
    var stamp = Date.now();
    function note(res) { if (res && res.cache && res.cache.storedAt) stamp = Math.min(stamp, res.cache.storedAt); return res; }
    var priorP = call(Object.assign({}, base, {selected_start_date: ymd(sp.pstart), selected_end_date: ymd(sp.pend), page: 1, per_page: 1}), refresh)
      .then(note).then(function (r) { return readPage(r).total; }).catch(function (e) { if (DENIALS[e && e.code]) throw e; return null; });
    return call(Object.assign({}, base, {page: 1, per_page: PER_PAGE}), refresh).then(note).then(function (r) {
      var first = readPage(r), pages = Math.min(first.totalPages || 1, MAX_PAGES), rest = [];
      for (var p = 2; p <= pages; p++) rest.push(p);
      var labels = {}, raw = first.entries.slice();
      function merge(pg) { Object.keys(pg.labels || {}).forEach(function (f) { labels[f] = Object.assign(labels[f] || {}, pg.labels[f]); }); }
      merge(first);
      var queue = rest.slice(), results = [];
      function worker() {
        if (!queue.length) return Promise.resolve();
        var p = queue.shift();
        return call(Object.assign({}, base, {page: p, per_page: PER_PAGE}), refresh).then(note).then(function (res) { results.push(readPage(res)); return worker(); });
      }
      return Promise.all([worker(), worker(), worker(), worker()]).then(function () {
        results.forEach(function (pg) { merge(pg); raw = raw.concat(pg.entries); });
        var entries = raw.map(function (e) { return slim(e, labels); }).filter(function (e) { return inDays(e, sp.start, sp.end); });
        return priorP.then(function (prior) { return {R: compute(entries, win, sp, first.total, prior), at: stamp}; });
      });
    });
  }
  function load(refresh) {
    if (!state.mcp || state.busy) return;
    var win = winOf(state.win);
    state.busy = true; state.lastAttempt = Date.now(); setStatus();
    fetchWindow(win, refresh).then(function (out) {
      state.live[win.k] = out.R; state.at[win.k] = out.at; state.mode = "live"; state.denied = false;
      if (state.win === win.k) { paint(out.R); setMsg(""); }
    }).catch(function (e) {
      var code = (e && e.code) || "other";
      if (code === "user_changed" || code === "cancelled") return;
      if (DENIALS[code]) { delete state.live[win.k]; state.mode = "snapshot"; state.denied = true; showSnapshot(); }
      if (code === "tool_error") setMsg((e.message || COPY.other).replace(/\s+/g, " ").trim(), "warn");
      else if (code === "not_granted" || code === "capability_disabled" || code === "capability_removed") { state.mcp = null; state.mode = "snapshot"; showSnapshot(); setMsg(COPY.no_mcp); }
      else setMsg(COPY[code] || COPY.other, DENIALS[code] ? "warn" : "info");
    }).then(function () { state.busy = false; setStatus(); });
  }
  function showSnapshot() {
    var win = winOf(state.win), cov = snapCovers(win);
    if (cov.ok || !SNAP.entries.length) paint(snapshotView(win));
  }
  function select(k) {
    var win = winOf(k);
    if (!state.mcp && !snapCovers(win).ok) { setMsg("The " + win.label + " view needs live numbers from " + SERVER + "."); return; }
    state.win = k;
    if (state.live[k]) { paint(state.live[k]); state.mode = "live"; }
    else if (snapCovers(win).ok) { paint(snapshotView(win)); state.mode = "snapshot"; }
    setStatus();
    if (state.mcp) load(false);
  }
  Array.prototype.forEach.call(els.tabs, function (b) {
    var win = winOf(b.dataset.win);
    b.addEventListener("click", function () { select(b.dataset.win); });
    b.disabled = false;
    if (!snapCovers(win).ok) b.dataset.needsLive = "1";
  });
  els.refresh.addEventListener("click", function () { if (state.mcp) load(true); else setMsg(CFG.live ? COPY.no_mcp : COPY.no_config); });

  // first paint: the snapshot
  if (!snapCovers(winOf(state.win)).ok) state.win = "7";
  paint(snapshotView(winOf(state.win)));
  setStatus();
  setInterval(setStatus, 60000);

  // demo connector: serves the sample entries in the connector's own page format
  function demoMcp() {
    var shift = Math.round((dayAdd(new Date(), 0) - parseDay(SNAP.to)) / 864e5);
    var all = SNAP.entries.map(function (e) {
      var t = parseTime(e.d); if (!t) return null;
      var n = new Date(t.getTime() + shift * 864e5);
      if (n > new Date()) return null;   // never show leads from the future
      return {"form_id": "1", date_created: ymd(n) + " " + pad(n.getHours()) + ":" + pad(n.getMinutes()) + ":00",
              "3": e.s, "4": e.m, "5": e.c, "6": e.ts, "7": e.g ? "x" : "", "8": e.f ? "x" : "", "9": e.k ? "x" : "",
              "10": e.rf ? "https://referrer.example/" : "", source_url: "https://example.com" + (e.u || "/")};
    }).filter(Boolean);
    var labels = {"1": {"3": "utm_source (HandL)", "4": "utm_medium (HandL)", "5": "utm_campaign (HandL)", "6": "traffic_source (HandL)",
                        "7": "gclid (HandL)", "8": "fbclid (HandL)", "9": "msclkid (HandL)", "10": "referrer (first touch, HandL)"}};
    return {callTool: function (server, tool, input) {
      var a = parseDay(input.selected_start_date), b = parseDay(input.selected_end_date);
      var rows = all.filter(function (e) { var d = parseDay(e.date_created); return d >= a && d <= b; })
        .sort(function (x, y) { return x.date_created < y.date_created ? 1 : -1; });
      var per = input.per_page || 50, pages = Math.max(1, Math.ceil(rows.length / per)), page = input.page || 1;
      var text = "Found " + rows.length + " entries.\nPage " + page + " of " + pages + " (" + per + " per page, " + rows.length + " total matching entries).\n" +
        "Field labels: " + JSON.stringify(labels) + "\nEntries: " + JSON.stringify(rows.slice((page - 1) * per, page * per));
      return sleep(250 + Math.random() * 350).then(function () { return {content: [{type: "text", text: text}], payload: text}; });
    }};
  }

  // live data
  if (CFG.demo) { state.mcp = demoMcp(); load(false); }
  else if (CFG.live && window.claude && typeof window.claude.use === "function") {
    if (!CFG.form_plugin || !(CFG.form_ids && CFG.form_ids.length)) setMsg(COPY.no_config);
    else {
      state.busy = true; setStatus();
      window.claude.use("mcp").then(function (mcp) {
        state.busy = false;
        if (!mcp) { setMsg(COPY.no_mcp); setStatus(); return; }
        state.mcp = mcp; load(false);
      }, function () { state.busy = false; setMsg(COPY.no_mcp); setStatus(); });
    }
  } else if (CFG.live) setMsg(COPY.no_mcp);
  setInterval(function () { if (!document.hidden && state.mcp && !state.denied) load(true); }, REFRESH_MS);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden && state.mcp && !state.denied && Date.now() - state.lastAttempt > REFRESH_MS) load(true);
  });
  // repaint once the embedded fonts are ready, so measured text (KPI fit, chart labels) is exact
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () {
    var w = winOf(state.win);
    paint(state.mode === "live" && state.live[w.k] ? state.live[w.k] : snapshotView(w));
  });

  // hover details
  var tip = document.createElement("div"); tip.className = "tip"; document.body.appendChild(tip);
  document.addEventListener("mousemove", function (e) {
    var t = e.target.closest && e.target.closest("[data-tip]");
    if (!t) { tip.style.opacity = 0; return; }
    tip.textContent = t.getAttribute("data-tip"); tip.style.opacity = 1;
    var x = e.clientX + 14, y = e.clientY + 14, w = tip.offsetWidth, h = tip.offsetHeight;
    if (x + w > innerWidth - 8) x = e.clientX - w - 14;
    if (y + h > innerHeight - 8) y = e.clientY - h - 14;
    tip.style.transform = "translate(" + x + "px," + y + "px)";
  });
})();
