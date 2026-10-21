"""
Dev tool: screenshot rendered reports and run layout checks.

    python scripts/dev/snap.py OUT_DIR file1.html [file2.html ...] [--mobile] [--split 2400]

For each HTML file it waits for fonts, then reports:
  * console errors
  * horizontal page overflow (the page is wider than the viewport)
  * clipped text (an element whose content is wider than its box) in KPI values,
    labels, table cells and legends
  * literal "undefined", "NaN", "None" or "null" in visible text
and saves a full-page PNG (split into chunks of --split px for easy viewing).
"""
import asyncio
import json
import os
import sys

from playwright.async_api import async_playwright

CHECK_JS = r"""
() => {
  const out = {overflowX: document.documentElement.scrollWidth - window.innerWidth, clipped: [], bad: []};
  const sel = '.kpi-value,.kpi-label,.bl-label,.bl-val,.dl-label,.dl-val,.cl-stats dd,.fn-val,.co-value,.sc-value,.h1,.h2,.h3,.tbl td,.cmp-cell b,.src,.fact dd';
  document.querySelectorAll(sel).forEach(el => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || el.offsetParent === null) return;
    if (el.scrollWidth > el.clientWidth + 2 && cs.overflow !== 'visible') {
      out.clipped.push((el.className || el.tagName) + ': ' + el.textContent.trim().slice(0, 60));
    }
  });
  const txt = document.body.innerText;
  ['undefined', 'NaN', 'None', 'null', '[object Object]'].forEach(w => {
    const re = new RegExp('\\b' + w.replace(/[\[\]]/g, '\\$&') + '\\b');
    if (re.test(txt)) out.bad.push(w);
  });
  out.height = document.body.scrollHeight;
  return out;
}
"""


async def run(out_dir, files, mobile=False, split=2400):
    os.makedirs(out_dir, exist_ok=True)
    results = {}
    async with async_playwright() as p:
        b = await p.chromium.launch()
        vp = {"width": 390, "height": 844} if mobile else {"width": 1280, "height": 900}
        ctx = await b.new_context(viewport=vp, device_scale_factor=1)
        for f in files:
            pg = await ctx.new_page()
            errors = []
            pg.on("console", lambda m, errors=errors: errors.append(m.text) if m.type == "error" else None)
            pg.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
            await pg.goto("file://" + os.path.abspath(f))
            await pg.evaluate("document.fonts.ready")
            await pg.wait_for_timeout(250)
            chk = await pg.evaluate(CHECK_JS)
            chk["errors"] = errors
            name = os.path.splitext(os.path.basename(f))[0] + ("-m" if mobile else "")
            png = os.path.join(out_dir, name + ".png")
            await pg.screenshot(path=png, full_page=True)
            results[name] = chk
            await pg.close()
            try:
                from PIL import Image
                im = Image.open(png)
                w, h = im.size
                n = (h + split - 1) // split
                for i in range(n):
                    im.crop((0, i * split, w, min(h, (i + 1) * split))).save(
                        os.path.join(out_dir, "%s_%d.png" % (name, i)))
            except Exception:
                pass
        await b.close()
    return results


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    mobile = "--mobile" in sys.argv
    split = 2400
    for a in sys.argv:
        if a.startswith("--split="):
            split = int(a.split("=")[1])
    out_dir, files = args[0], args[1:]
    res = asyncio.run(run(out_dir, files, mobile, split))
    for k, v in res.items():
        flag = "OK " if not (v["errors"] or v["clipped"] or v["bad"] or v["overflowX"] > 0) else "!! "
        print(flag + k, json.dumps({kk: vv for kk, vv in v.items() if vv}))


if __name__ == "__main__":
    main()
