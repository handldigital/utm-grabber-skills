"""
One-shot demo report builder.

When the user picks "See a sample report (no setup needed)" in the welcome
flow, Claude runs this script instead of the full MCP → recipe → template
pipeline. Handles data generation, summary building, and output in one call.

Usage (from bash tool in Claude's conversation):

    python scripts/demo_report.py \\
      --out /mnt/user-data/outputs/demo-report.html \\
      --report monthly \\
      --theme gradient

    # Or for a different report type:
    python scripts/demo_report.py --out /tmp/demo.html --report weekly

Supported report types (any RECIPES key from report_recipes.py):
    monthly, weekly, audit, leaderboard, forecast, anomaly,
    lead-scorer, landing-page, form-performance, ad-creative,
    keyword, source-to-crm, paid-vs-organic, agency-rollup

Supported output formats (inferred from --out extension):
    .html → HTML template
    .pptx → PowerPoint deck
    .pdf  → WeasyPrint PDF (always light — per v0.9.8 rule)

Brand profile is a stock "Sample Brand" unless --brand-json points to a
serialized profile. Theme defaults to light unless --theme=gradient.
"""
import argparse
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


DEFAULT_BRAND = {
    "company_name": "Sample Co",
    "logo": {"type": "text", "value": "Sample Co"},
    "colors": {
        "primary": "#0160BF",   # UTM Grabber blue
        "accent":  "#2E90FA",   # UTM Grabber bright blue (accent)
        "ink":     "#0B1B34",
        "muted":   "#64748B",
        "surface": "#F3F1FA",
    },
}


def _load_brand(brand_json_path, theme):
    if brand_json_path and os.path.exists(brand_json_path):
        with open(brand_json_path) as f:
            brand = json.load(f)
    else:
        brand = dict(DEFAULT_BRAND)
    if theme and theme.lower() == 'gradient':
        brand['theme'] = 'gradient'
    return brand


def _build_summary(report_type, brand):
    """Dispatch to the right recipe with demo data."""
    from demo_data import get_demo_current, get_demo_prior
    from report_recipes import (
        RECIPES,
        build_monthly_summary, build_weekly_summary,
        build_forecast_summary, build_anomaly_summary,
        build_campaign_deep_dive_summary, build_lead_profile_summary,
        build_side_by_side_summary, build_budget_simulator_summary,
        build_agency_rollup_summary,
    )

    if report_type not in RECIPES:
        raise ValueError(
            f"Unknown report type: {report_type!r}. "
            f"Available: {', '.join(sorted(set(RECIPES.keys())))}"
        )

    current = get_demo_current()
    prior = get_demo_prior()
    fn = RECIPES[report_type]

    common_kwargs = dict(
        brand_profile=brand,
        customer_name=brand.get('company_name', 'Sample Co'),
        customer_domain='demo.sample.com',
    )

    # Dispatch by function identity so aliases route correctly
    if fn in (build_monthly_summary, build_weekly_summary):
        return fn(current, prior, **common_kwargs)
    elif fn is build_forecast_summary:
        # Single-history arg: concatenate current + prior for longer history window
        history = (prior or []) + (current or [])
        return fn(history, **common_kwargs)
    elif fn is build_anomaly_summary:
        # Takes (current, baseline) — baseline is the older period
        return fn(current, prior, **common_kwargs)
    elif fn is build_campaign_deep_dive_summary:
        camps = {}
        for e in current:
            c = e.get('utm_campaign (HandL)')
            if c:
                camps[c] = camps.get(c, 0) + 1
        top = max(camps, key=camps.get) if camps else 'demo_campaign'
        return fn(current, top, **common_kwargs)
    elif fn is build_lead_profile_summary:
        sample_email = next(
            (e.get('Work Email') for e in current if e.get('Work Email')),
            'demo@example.com'
        )
        return fn(current, sample_email, **common_kwargs)
    elif fn is build_side_by_side_summary:
        half = len(current) // 2
        return fn(current[:half], 'First half', current[half:], 'Second half',
                  **common_kwargs)
    elif fn is build_budget_simulator_summary:
        return fn(current,
                  {'shift_from': 'google', 'shift_to': 'linkedin', 'pct': 20},
                  **common_kwargs)
    elif fn is build_agency_rollup_summary:
        q = len(current) // 4
        brand_data = [
            {'brand_name': 'Sample Agency — Client A', 'entries': current[:q]},
            {'brand_name': 'Sample Agency — Client B', 'entries': current[q:2*q]},
            {'brand_name': 'Sample Agency — Client C', 'entries': current[2*q:3*q]},
            {'brand_name': 'Sample Agency — Client D', 'entries': current[3*q:]},
        ]
        return fn(brand_data, **common_kwargs)
    else:
        # Single-arg recipes: audit, leaderboard, lead-scorer, landing-page,
        # form-performance, ad-creative, keyword, source-to-crm, paid-vs-organic
        return fn(current, **common_kwargs)


def _write_html(summary, out_path):
    template_path = os.path.join(
        os.path.dirname(_HERE), 'templates', 'report-shell.html'
    )
    with open(template_path) as f:
        tpl = f.read()
    new_json = json.dumps(summary, ensure_ascii=False)
    tpl = re.sub(
        r'<script id="report-data" type="application/json">.*?</script>',
        (
            '<script id="report-data" type="application/json">\n'
            + new_json
            + '\n</script>'
        ),
        tpl, count=1, flags=re.DOTALL
    )
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    with open(out_path, 'w') as f:
        f.write(tpl)


def _write_pptx(summary, out_path):
    from build_pptx import build_pptx_from_summary
    build_pptx_from_summary(summary, out_path)


def _write_pdf(summary, out_path):
    from build_pdf import build_pdf_from_summary
    # Note: PDF always renders light per v0.9.8 rule, even if summary brand
    # specifies theme=gradient. build_pdf.py force-empties the body class.
    build_pdf_from_summary(summary, out_path, validate=False)


def main():
    p = argparse.ArgumentParser(
        description="Generate a sample attribution report using synthetic demo data."
    )
    p.add_argument('--out', required=True,
                   help='Output path (.html, .pptx, or .pdf)')
    p.add_argument('--report', default='monthly',
                   help='Report type key from RECIPES (default: monthly)')
    p.add_argument('--theme', default='light',
                   help="'light' (default) or 'gradient' — affects HTML/PPTX only")
    p.add_argument('--brand-json',
                   help='Optional path to a brand profile JSON file')
    args = p.parse_args()

    brand = _load_brand(args.brand_json, args.theme)
    summary = _build_summary(args.report, brand)

    ext = os.path.splitext(args.out)[1].lower()
    if ext == '.html':
        _write_html(summary, args.out)
    elif ext == '.pptx':
        _write_pptx(summary, args.out)
    elif ext == '.pdf':
        _write_pdf(summary, args.out)
    else:
        raise ValueError(f"Unsupported output extension: {ext}. Use .html, .pptx, or .pdf")

    print(f"✓ Demo report written: {args.out}")


if __name__ == '__main__':
    main()
