"""
Matplotlib-based chart renderer for PDF generation.

The main HTML template uses Chart.js (JavaScript) which WeasyPrint can't execute.
This module renders the same chart specs to SVG strings that can be embedded
directly in the HTML before WeasyPrint converts it to PDF.

Supports all 7 chart types from the v0.8 template schema:
  doughnut, bar-horizontal, bar-vertical, bar-stacked, bar-grouped, line, area.

Output: SVG string (UTF-8) ready to drop into an <img src="data:image/svg+xml;utf8,...">
        or inline into an HTML document.
"""
import io
import os
import matplotlib
matplotlib.use('Agg')  # headless
import matplotlib.pyplot as plt
from matplotlib import font_manager
import matplotlib.patches as mpatches
from matplotlib.ticker import MaxNLocator


# Register bundled fonts if available. Looks in assets/fonts relative to this file.
_FONT_DIR_CANDIDATES = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'fonts'),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'fonts'),
    '/home/claude/fonts',
]
for _d in _FONT_DIR_CANDIDATES:
    if os.path.isdir(_d):
        for _f in os.listdir(_d):
            if _f.endswith('.ttf') or _f.endswith('.otf'):
                try:
                    font_manager.fontManager.addfont(os.path.join(_d, _f))
                except Exception:
                    pass
        break


# Font families with short fallback chains to keep matplotlib quiet.
# If the primary is bundled (default path), that's what gets used.
DISPLAY_FONT = ['Instrument Serif', 'DejaVu Serif']
BODY_FONT = ['Geist', 'DejaVu Sans']
MONO_FONT = ['Geist Mono', 'DejaVu Sans Mono']


def _brand_palette(colors):
    """Return a 7-color palette matching the Chart.js palette in the template."""
    return [
        colors.get('primary', '#0160BF'),
        colors.get('accent', '#2E90FA'),
        '#FFC857',
        '#30B47A',
        '#6FB1E8',
        '#F59E0B',
        colors.get('ink', '#0B1B34'),
    ]


def _style_axes(ax, show_x_grid=False):
    """Apply consistent axis styling across all charts."""
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#C3C9D1')
    ax.spines['bottom'].set_color('#C3C9D1')
    ax.tick_params(axis='both', which='both', length=0, colors='#64748B', labelsize=10)
    ax.grid(axis='y' if show_x_grid else 'x', color='#EDEEF2', linestyle='-', linewidth=0.5, zorder=0)
    ax.set_axisbelow(True)


def _make_fig(width_in=10, height_in=4.2, dpi=120):
    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=dpi)
    fig.patch.set_facecolor('white')
    return fig, ax


def _render_to_svg(fig):
    buf = io.StringIO()
    fig.savefig(buf, format='svg', bbox_inches='tight', pad_inches=0.2,
                facecolor='white', transparent=False)
    plt.close(fig)
    return buf.getvalue()


def render_doughnut(labels, values, colors, unit='%', **kwargs):
    palette = _brand_palette(colors)
    fig, ax = plt.subplots(figsize=(8, 4.8), dpi=120)
    fig.patch.set_facecolor('white')

    wedges, _ = ax.pie(
        values, labels=None,
        colors=[palette[i % len(palette)] for i in range(len(values))],
        wedgeprops=dict(width=0.42, edgecolor='white', linewidth=3),
        startangle=90, counterclock=False,
    )

    # Center total
    total = sum(values)
    ax.text(0, 0.08, f'{total}', ha='center', va='center',
            fontfamily=DISPLAY_FONT, fontsize=36, color=colors.get('ink', '#0B1B34'),
            fontstyle='italic')
    ax.text(0, -0.18, 'total', ha='center', va='center',
            fontfamily=MONO_FONT, fontsize=10, color=colors.get('muted', '#64748B'))

    # Right-side legend
    legend_items = [mpatches.Patch(color=palette[i % len(palette)], label=f'{l}: {v}{unit}')
                    for i, (l, v) in enumerate(zip(labels, values))]
    ax.legend(handles=legend_items, loc='center left', bbox_to_anchor=(1.02, 0.5),
              frameon=False, fontsize=11)
    ax.set_aspect('equal')
    return _render_to_svg(fig)


def render_bar_horizontal(labels, values, colors, x_title=None, **kwargs):
    palette = _brand_palette(colors)
    fig, ax = _make_fig(width_in=10, height_in=max(3.5, 0.6 * len(labels) + 1.2))

    # Reverse so largest is at top
    labels_rev = list(reversed(labels))
    values_rev = list(reversed(values))
    bar_colors = [palette[(len(values_rev) - 1 - i) % len(palette)] for i in range(len(values_rev))]

    bars = ax.barh(range(len(labels_rev)), values_rev, color=bar_colors, height=0.65, zorder=3)

    ax.set_yticks(range(len(labels_rev)))
    ax.set_yticklabels(labels_rev, fontsize=11, color=colors.get('ink', '#0B1B34'))
    if x_title:
        ax.set_xlabel(x_title, fontsize=10, color=colors.get('muted', '#64748B'))
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    _style_axes(ax, show_x_grid=True)
    ax.spines['left'].set_visible(False)

    # Value labels
    for bar, val in zip(bars, values_rev):
        ax.text(bar.get_width() + max(values) * 0.01, bar.get_y() + bar.get_height() / 2,
                str(val), va='center', fontsize=10, color=colors.get('ink', '#0B1B34'))

    return _render_to_svg(fig)


def render_bar_vertical(labels, values, colors, **kwargs):
    palette = _brand_palette(colors)
    fig, ax = _make_fig()
    ax.bar(range(len(labels)), values, color=palette[0], width=0.65, zorder=3)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=10, color=colors.get('ink', '#0B1B34'), rotation=0)
    _style_axes(ax, show_x_grid=True)
    return _render_to_svg(fig)


def render_bar_stacked(labels, stacks, colors, **kwargs):
    palette = _brand_palette(colors)
    fig, ax = _make_fig()
    bottom = [0] * len(labels)
    for i, stack in enumerate(stacks):
        ax.bar(range(len(labels)), stack['values'], bottom=bottom,
               color=palette[i % len(palette)], label=stack.get('label', ''),
               width=0.65, zorder=3)
        bottom = [b + v for b, v in zip(bottom, stack['values'])]
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=10, color=colors.get('ink', '#0B1B34'))
    ax.legend(loc='upper right', frameon=False, fontsize=10, ncol=min(len(stacks), 3))
    _style_axes(ax, show_x_grid=True)
    return _render_to_svg(fig)


def render_bar_grouped(labels, groups, colors, **kwargs):
    palette = _brand_palette(colors)
    fig, ax = _make_fig()
    n_groups = len(groups)
    bar_width = 0.8 / max(n_groups, 1)
    for i, group in enumerate(groups):
        offsets = [x + (i - (n_groups - 1) / 2) * bar_width for x in range(len(labels))]
        ax.bar(offsets, group['values'], bar_width,
               color=palette[i % len(palette)], label=group.get('label', ''), zorder=3)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=10, color=colors.get('ink', '#0B1B34'))
    ax.legend(loc='upper right', frameon=False, fontsize=10, ncol=min(n_groups, 3))
    _style_axes(ax, show_x_grid=True)
    return _render_to_svg(fig)


def render_line(labels, values, colors, filled=False, **kwargs):
    palette = _brand_palette(colors)
    fig, ax = _make_fig()
    line_color = palette[0]
    ax.plot(range(len(labels)), values, color=line_color, linewidth=2,
            marker='o', markersize=3, markerfacecolor=line_color, zorder=3)
    if filled:
        ax.fill_between(range(len(labels)), 0, values, color=line_color, alpha=0.13, zorder=2)

    # Sparse x-ticks if there are many labels
    step = max(1, len(labels) // 8)
    ax.set_xticks(range(0, len(labels), step))
    ax.set_xticklabels([labels[i] for i in range(0, len(labels), step)],
                       fontsize=9, color=colors.get('muted', '#64748B'), rotation=0)
    _style_axes(ax, show_x_grid=True)
    return _render_to_svg(fig)


def render_chart(chart_spec, colors):
    """
    Router — picks the right renderer based on `chart_spec['type']`.
    Returns SVG string or None if type is unknown.
    """
    t = chart_spec.get('type')
    try:
        if t == 'doughnut':
            return render_doughnut(chart_spec['labels'], chart_spec['values'],
                                    colors, unit=chart_spec.get('unit', '%'))
        if t == 'bar-horizontal':
            return render_bar_horizontal(chart_spec['labels'], chart_spec['values'],
                                          colors, x_title=chart_spec.get('x_title'))
        if t == 'bar-vertical':
            return render_bar_vertical(chart_spec['labels'], chart_spec['values'], colors)
        if t == 'bar-stacked':
            return render_bar_stacked(chart_spec['labels'], chart_spec['stacks'], colors)
        if t == 'bar-grouped':
            return render_bar_grouped(chart_spec['labels'], chart_spec['groups'], colors)
        if t in ('line', 'area'):
            return render_line(chart_spec['labels'], chart_spec['values'], colors,
                               filled=(t == 'area'))
        return None
    except Exception as e:
        # Return a tiny placeholder SVG with an error message rather than crashing the PDF
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 100">'
                f'<rect width="400" height="100" fill="#F5F7FB"/>'
                f'<text x="200" y="55" text-anchor="middle" fill="#64748B" '
                f'font-family="monospace" font-size="11">Chart unavailable: {t}</text></svg>')
