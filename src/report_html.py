"""
Small helpers for writing the plain HTML report pages (tables and a static SVG line
chart), so every number on a page is generated from the CSV outputs rather than
typed in by hand.
"""
import html

import numpy as np
import pandas as pd


def pct(x, digits=1, sign=False):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    s = f"{x * 100:+.{digits}f}%" if sign else f"{x * 100:.{digits}f}%"
    return s.replace("-", "&minus;")


def num(x, digits=2):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    return f"{x:.{digits}f}".replace("-", "&minus;")


def pval(p):
    if p is None or np.isnan(p):
        return "n/a"
    return "&lt;0.0001" if p < 1e-4 else f"{p:.4f}"


def table(header: list, rows: list, highlight: set = frozenset()) -> str:
    """rows: list of lists of already-formatted cell strings."""
    th = "".join(f"<th>{h}</th>" for h in header)
    body = []
    for i, r in enumerate(rows):
        cls = ' class="hl"' if i in highlight else ""
        tds = "".join(f'<td class="neg">{c}</td>' if str(c).startswith("&minus;") and i not in highlight
                      else f"<td>{c}</td>" for c in r)
        body.append(f"<tr{cls}>{tds}</tr>")
    return f'<div class="table-wrap"><table><thead><tr>{th}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


def line_chart(dates, series: dict, ylabel_fmt=lambda v: f"${v:.0f}", width=760, height=320) -> str:
    """Static SVG line chart. series: {label: (values, color, dash)}; dates: sequence of Timestamps."""
    ml, mr, mt, mb = 44, 118, 12, 28
    pw, ph = width - ml - mr, height - mt - mb
    dates = pd.DatetimeIndex(dates)
    all_vals = np.concatenate([np.asarray(v, float) for v, _, _ in series.values()])
    lo, hi = np.nanmin(all_vals), np.nanmax(all_vals)
    step = max(0.5, np.ceil((hi - lo) / 5 * 2) / 2)
    ylo, yhi = np.floor(lo / step) * step, np.ceil(hi / step) * step
    t0, t1 = dates[0].value, dates[-1].value

    def x(d):
        return ml + (pd.Timestamp(d).value - t0) / (t1 - t0) * pw

    def y(v):
        return mt + ph - (v - ylo) / (yhi - ylo) * ph

    out = [f'<svg viewBox="0 0 {width} {height}" role="img" font-family="Helvetica, Arial, sans-serif" font-size="11">']
    for v in np.arange(ylo, yhi + step / 2, step):
        out.append(f'<line x1="{ml}" x2="{width - mr}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="#e5e5e5"/>')
        out.append(f'<text x="{ml - 6}" y="{y(v) + 4:.1f}" text-anchor="end" fill="#666">{ylabel_fmt(v)}</text>')
    for yr in range(dates[0].year + 1, dates[-1].year + 1):
        d = pd.Timestamp(year=yr, month=1, day=1)
        out.append(f'<line x1="{x(d):.1f}" x2="{x(d):.1f}" y1="{mt}" y2="{mt + ph}" stroke="#f0f0f0"/>')
        out.append(f'<text x="{x(d):.1f}" y="{height - 8}" text-anchor="middle" fill="#666">{yr}</text>')
    for label, (vals, color, dash) in series.items():
        vals = np.asarray(vals, float)
        pts = " ".join(f"{x(d):.1f},{y(v):.1f}" for d, v in zip(dates, vals) if not np.isnan(v))
        da = f' stroke-dasharray="{dash}"' if dash else ""
        out.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.8"{da}/>')
        last = vals[~np.isnan(vals)][-1]
        out.append(f'<text x="{x(dates[-1]) + 5:.1f}" y="{y(last) + 4:.1f}" fill="{color}">{html.escape(label)} '
                   f'{ylabel_fmt(last) if ylabel_fmt else ""}</text>')
    out.append("</svg>")
    return "".join(out)


PAGE_HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<main>
"""
PAGE_FOOT = """
<footer>Code and data: <a href="https://github.com/jmp1909/sec-inside-trading">github.com/jmp1909/sec-inside-trading</a>.
Not investment advice.</footer>
</main>
</body>
</html>
"""
