"""Turn a results.json into one HTML page: the comparison, the charts, the diagnosis and health.

    python bench/report.py <work>/<tier>/results.json
"""

import datetime as dt
import html
import json
import os
import sys

W, H, PAD = 760, 300, 48
ROWS = [
    ("Hidden tests passed", lambda f: f"{f['passed']}/{f['of']}", None),
    ("Tokens", lambda f: f"{f['tokens'] / 1e6:.1f}M", "tokens"),
    ("Cost-weighted tokens", lambda f: f"{f['cost'] / 1e6:.1f}M", "cost"),
    ("API-equivalent cost", lambda f: f"${f['usd']:.2f}" if f["usd"] is not None else "-", "usd"),
    ("Tokens per passing task", lambda f: f"{f['tokens_per_pass'] / 1e6:.1f}M" if f["tokens_per_pass"] else "-",
     "tokens_per_pass"),
    ("Wall clock", lambda f: f"{f['wall_min']:.0f} min", "wall_min"),
    ("Time per task", lambda f: f"{f['min_per_task']:.0f} min", "min_per_task"),
    ("Tokens on calls above 100k", lambda f: f"{f['above_100k']:.0%}", "above_100k"),
    ("Largest agent context", lambda f: f"{f['peak'] / 1e3:.0f}k" if f["peak"] else "-", "peak"),
    ("Lead peak context", lambda f: f"{f['lead_peak'] / 1e3:.0f}k", "lead_peak"),
    ("Agent start-up (median)", lambda f: f"{f['startup'] / 1e3:.1f}k" if f["startup"] else "-", "startup"),
    ("Cache rebought after waits", lambda f: f"{f['rebuys'] / 1e6:.1f}M", "rebuys"),
    ("New suite failures", lambda f: "-" if f["new_failures"] is None else str(len(f["new_failures"])), None),
    ("Stopped by", lambda f: f["stopped"] or "finished", None),
]
CSS = """
:root{--bg:#fbfaf7;--fg:#1d1d1b;--muted:#6b6a65;--line:#dedcd5;--c0:#b8572f;--c1:#2f6fb8;--c2:#3c8f5a;--c3:#8a4fb0}
@media (prefers-color-scheme:dark){:root{--bg:#18181a;--fg:#ecebe6;--muted:#a3a29c;--line:#3a3a3d;
--c0:#e58a5f;--c1:#6fa6e8;--c2:#6cc58c;--c3:#bd8ae0}}
body{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;max-width:820px;margin:0 auto;padding:24px 16px}
table{border-collapse:collapse;width:100%}td,th{padding:4px 8px;border-bottom:1px solid var(--line);text-align:right}
td:first-child,th:first-child{text-align:left}.muted{color:var(--muted)}svg{width:100%;height:auto}
.swatch{display:inline-block;width:10px;height:10px;border-radius:2px;margin:0 4px 0 12px}
"""


def esc(s):
    return html.escape(str(s))


def _minutes(series):
    series = [p for p in series if p["ts"]]
    if not series:
        return []
    t0 = min(dt.datetime.fromisoformat(p["ts"].replace("Z", "+00:00")) for p in series)
    return [((dt.datetime.fromisoformat(p["ts"].replace("Z", "+00:00")) - t0).total_seconds() / 60, p)
            for p in series if p["ts"]]


def chart(title, arms, points_of, dots):
    """An SVG chart, one colour per arm. points_of(series) gives [(minutes, value)]."""
    data = [(i, points_of(_minutes(a["measure"]["series"]))) for i, a in enumerate(arms)]
    xs = [x for _, pts in data for x, _ in pts] or [0]
    ys = [y for _, pts in data for _, y in pts] or [0]
    xmax, ymax = max(xs) or 1, max(ys) or 1

    def sx(x):
        return PAD + x / xmax * (W - 2 * PAD)

    def sy(y):
        return H - PAD + 8 - y / ymax * (H - 2 * PAD)

    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(title)}">',
             f'<line x1="{PAD}" y1="{sy(0)}" x2="{W - PAD}" y2="{sy(0)}" stroke="var(--line)"/>',
             f'<text x="{PAD}" y="16" fill="var(--muted)" font-size="12">{esc(title)}; '
             f'top {ymax / 1e3:,.0f}k, {xmax:.0f} min</text>']
    for i, pts in data:
        colour = f"var(--c{i % 4})"
        if dots:
            parts += [f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="1.8" fill="{colour}" opacity=".6"/>' for x, y in pts]
        else:
            path = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in pts)
            parts.append(f'<polyline points="{path}" fill="none" stroke="{colour}" stroke-width="2"/>')
    parts.append("</svg>")
    return "".join(parts)


def _context(points):
    return [(x, p["ctx"]) for x, p in points]


def _cumulative(points):
    total, out = 0, []
    for x, p in sorted(points, key=lambda xp: xp[0]):
        total += p["ctx"] + p["out"]
        out.append((x, total))
    return out


def _change(base, value):
    if base in (None, 0) or value is None:
        return ""
    return f"{(value - base) / base:+.0%}".replace("-", "−")


def render(results):
    arms = [a for a in results["arms"] if a.get("figures") and a.get("measure")]
    head = ["<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>",
            f"<title>Benchmark {esc(results['tier'])}</title><style>{CSS}</style></head><body>",
            f"<h1>lean-agents benchmark: {esc(results['tier'])} tier</h1>",
            f"<p class='muted'>{esc(results['date'])}. Tasks: {esc(', '.join(results['tasks']))}. "
            f"Token cap per arm: {results['cap'] / 1e6:.0f}M.</p>"]
    if results.get("runs_per_arm", 1) == 1:
        head.append("<p><strong>Single run per arm.</strong> Agent runs vary, so differences under about 10% "
                    "are within run-to-run noise.</p>")
    for a in results["arms"]:
        if a.get("error"):
            head.append(f"<p><strong>{esc(a['arm'])}:</strong> {esc(a['error'])}</p>")
    if not arms:
        return "".join(head) + "</body></html>"
    base = arms[0]["figures"]
    table = ["<table><tr><th></th>" + "".join(f"<th>{esc(a['arm'])}</th>" for a in arms) + "</tr>"]
    for name, fmt, key in ROWS:
        cells = []
        for a in arms:
            f = a["figures"]
            change = _change(base.get(key), f.get(key)) if key and a is not arms[0] else ""
            cells.append(f"<td>{esc(fmt(f))} <span class='muted'>{change}</span></td>")
        table.append(f"<tr><td>{esc(name)}</td>{''.join(cells)}</tr>")
    table.append("</table>")
    legend = "<p>" + "".join(f"<span class='swatch' style='background:var(--c{i % 4})'></span>{esc(a['arm'])}"
                             for i, a in enumerate(arms)) + "</p>"
    charts = [legend, chart("Context size of every model call over time", arms, _context, dots=True),
              chart("Cumulative tokens over time", arms, _cumulative, dots=False)]
    diag = ["<h2>Where the tokens went</h2>"]
    for a in arms:
        d, health = a["measure"]["diagnosis"], a["measure"]["health"]
        diag.append(f"<h3>{esc(a['arm'])}</h3><ul>")
        diag += [f"<li>{esc(c['cause'])}: {c['tokens'] / 1e6:.1f}M ({c['share']:.0%}). {esc(c['fix'])}</li>"
                 for c in d["causes"][:3]]
        diag += [f"<li>{esc(h['kind'])}: {esc(h['agent'])}: {esc(h['detail'])}</li>" for h in health]
        diag.append("</ul>")
    return "".join(head + ["<h2>Comparison</h2>"] + table + ["<h2>Over time</h2>"] + charts + diag) + "</body></html>"


def main():
    path = sys.argv[1]
    with open(path, encoding="utf-8") as f:
        results = json.load(f)
    out = os.path.join(os.path.dirname(os.path.abspath(path)), "report.html")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(render(results))
    print(out)


if __name__ == "__main__":
    main()
