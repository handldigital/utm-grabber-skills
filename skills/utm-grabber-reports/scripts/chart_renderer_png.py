"""
PNG chart renderer for PowerPoint.

PowerPoint prefers PNG over SVG for reliable cross-version rendering.
This module mirrors chart_renderer.py (SVG for PDF) but outputs PNG bytes.

Returns: bytes object (PNG) that can be embedded via python-pptx's
add_picture(BytesIO(png_bytes), ...).
"""
import io
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import matplotlib.patches as mpatches
from matplotlib.ticker import MaxNLocator


# Register bundled fonts
_FONT_DIR_CANDIDATES = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'fonts'),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'fonts'),
    '/home/claude/fonts',
]
for _d in _FONT_DIR_CANDIDATES:
    if os.path.isdir(_d):
        for _f in os.listdir(_d):
            if _f.endswith(('.ttf', '.otf')):
                try:
                    font_manager.fontManager.addfont(os.path.join(_d, _f))
                except Exception:
                    pass
        break


DISPLAY_FONT = ['Instrument Serif', 'DejaVu Serif']
BODY_FONT = ['Geist', 'DejaVu Sans']
MONO_FONT = ['Geist Mono', 'DejaVu Sans Mono']

PNG_DPI = 200  # High DPI so slides look sharp at any zoom


def _brand_palette(colors):
    return [
        colors.get('primary', '#0160BF'),
        colors.get('accent', '#2E90FA'),
        '#FFC857',
        '#30B47A',
        '#6FB1E8',
        '#F59E0B',
        colors.get('ink', '#0B1B34'),
    ]


def _style_axes(ax):
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#C3C9D1')
    ax.spines['bottom'].set_color('#C3C9D1')
    ax.tick_params(axis='both', which='both', length=0, colors='#64748B', labelsize=12)
    ax.grid(axis='y', color='#EDEEF2', linestyle='-', linewidth=0.5, zorder=0)
    ax.set_axisbelow(True)


def _to_png_bytes(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=PNG_DPI, bbox_inches='tight',
                facecolor='white', transparent=False)
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def render_doughnut_png(labels, values, colors, unit='%', width_in=7, height_in=4.5):
    palette = _brand_palette(colors)
    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=PNG_DPI / 2)
    fig.patch.set_facecolor('white')
    wedges, _ = ax.pie(
        values, labels=None,
        colors=[palette[i % len(palette)] for i in range(len(values))],
        wedgeprops=dict(width=0.42, edgecolor='white', linewidth=3),
        startangle=90, counterclock=False,
    )
    total = sum(values)
    ax.text(0, 0.08, f'{total}', ha='center', va='center',
            fontfamily=DISPLAY_FONT, fontsize=40, color=colors.get('ink', '#0B1B34'),
            fontstyle='italic')
    ax.text(0, -0.22, 'total', ha='center', va='center',
            fontfamily=MONO_FONT, fontsize=11, color=colors.get('muted', '#64748B'))
    legend_items = [mpatches.Patch(color=palette[i % len(palette)], label=f'{l}: {v}{unit}')
                    for i, (l, v) in enumerate(zip(labels, values))]
    ax.legend(handles=legend_items, loc='center left', bbox_to_anchor=(1.02, 0.5),
              frameon=False, fontsize=12)
    ax.set_aspect('equal')
    return _to_png_bytes(fig)


def render_bar_horizontal_png(labels, values, colors, width_in=10, height_in=5):
    palette = _brand_palette(colors)
    fig, ax = plt.subplots(figsize=(width_in, max(height_in, 0.55 * len(labels) + 1.2)), dpi=PNG_DPI / 2)
    fig.patch.set_facecolor('white')

    labels_rev = list(reversed(labels))
    values_rev = list(reversed(values))
    bar_colors = [palette[(len(values_rev) - 1 - i) % len(palette)] for i in range(len(values_rev))]
    bars = ax.barh(range(len(labels_rev)), values_rev, color=bar_colors, height=0.65, zorder=3)
    ax.set_yticks(range(len(labels_rev)))
    ax.set_yticklabels(labels_rev, fontsize=12, color=colors.get('ink', '#0B1B34'))
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    _style_axes(ax)
    ax.spines['left'].set_visible(False)
    for bar, val in zip(bars, values_rev):
        ax.text(bar.get_width() + max(values) * 0.01, bar.get_y() + bar.get_height() / 2,
                str(val), va='center', fontsize=11, color=colors.get('ink', '#0B1B34'))
    return _to_png_bytes(fig)


def render_bar_vertical_png(labels, values, colors, width_in=10, height_in=4.5):
    palette = _brand_palette(colors)
    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=PNG_DPI / 2)
    fig.patch.set_facecolor('white')
    ax.bar(range(len(labels)), values, color=palette[0], width=0.65, zorder=3)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=11, color=colors.get('ink', '#0B1B34'))
    _style_axes(ax)
    return _to_png_bytes(fig)


def render_bar_stacked_png(labels, stacks, colors, width_in=10, height_in=4.5):
    palette = _brand_palette(colors)
    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=PNG_DPI / 2)
    fig.patch.set_facecolor('white')
    bottom = [0] * len(labels)
    for i, stack in enumerate(stacks):
        ax.bar(range(len(labels)), stack['values'], bottom=bottom,
               color=palette[i % len(palette)], label=stack.get('label', ''),
               width=0.65, zorder=3)
        bottom = [b + v for b, v in zip(bottom, stack['values'])]
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=11, color=colors.get('ink', '#0B1B34'))
    ax.legend(loc='upper right', frameon=False, fontsize=11, ncol=min(len(stacks), 3))
    _style_axes(ax)
    return _to_png_bytes(fig)


def render_bar_grouped_png(labels, groups, colors, width_in=10, height_in=4.5):
    palette = _brand_palette(colors)
    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=PNG_DPI / 2)
    fig.patch.set_facecolor('white')
    n_groups = len(groups)
    bar_width = 0.8 / max(n_groups, 1)
    for i, group in enumerate(groups):
        offsets = [x + (i - (n_groups - 1) / 2) * bar_width for x in range(len(labels))]
        ax.bar(offsets, group['values'], bar_width,
               color=palette[i % len(palette)], label=group.get('label', ''), zorder=3)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=11, color=colors.get('ink', '#0B1B34'))
    ax.legend(loc='upper right', frameon=False, fontsize=11, ncol=min(n_groups, 3))
    _style_axes(ax)
    return _to_png_bytes(fig)


def render_line_png(labels, values, colors, filled=False, width_in=10, height_in=4.5):
    palette = _brand_palette(colors)
    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=PNG_DPI / 2)
    fig.patch.set_facecolor('white')
    line_color = palette[0]
    ax.plot(range(len(labels)), values, color=line_color, linewidth=2.5,
            marker='o', markersize=4, markerfacecolor=line_color, zorder=3)
    if filled:
        ax.fill_between(range(len(labels)), 0, values, color=line_color, alpha=0.13, zorder=2)
    step = max(1, len(labels) // 8)
    ax.set_xticks(range(0, len(labels), step))
    ax.set_xticklabels([labels[i] for i in range(0, len(labels), step)],
                       fontsize=11, color=colors.get('muted', '#64748B'))
    _style_axes(ax)
    return _to_png_bytes(fig)


def render_chart_png(chart_spec, colors, width_in=10, height_in=4.5):
    """Router — returns PNG bytes for the given chart spec, or None."""
    t = chart_spec.get('type')
    try:
        if t == 'doughnut':
            return render_doughnut_png(chart_spec['labels'], chart_spec['values'],
                                        colors, unit=chart_spec.get('unit', '%'),
                                        width_in=width_in, height_in=height_in)
        if t == 'bar-horizontal':
            return render_bar_horizontal_png(chart_spec['labels'], chart_spec['values'], colors,
                                              width_in=width_in, height_in=height_in)
        if t == 'bar-vertical':
            return render_bar_vertical_png(chart_spec['labels'], chart_spec['values'], colors,
                                            width_in=width_in, height_in=height_in)
        if t == 'bar-stacked':
            return render_bar_stacked_png(chart_spec['labels'], chart_spec['stacks'], colors,
                                           width_in=width_in, height_in=height_in)
        if t == 'bar-grouped':
            return render_bar_grouped_png(chart_spec['labels'], chart_spec['groups'], colors,
                                           width_in=width_in, height_in=height_in)
        if t in ('line', 'area'):
            return render_line_png(chart_spec['labels'], chart_spec['values'], colors,
                                   filled=(t == 'area'),
                                   width_in=width_in, height_in=height_in)
        return None
    except Exception:
        return None
