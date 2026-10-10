"""Turn a results.json into a page for sharing: a side-by-side card and a replay of the run.

    python bench/post.py <work>/<tier>/results.json [--repo URL]

Writes post.html next to results.json. Open it in a browser; add #record to
the address to show only the replay, laid out for capture.
bench/post_capture.py turns it into post-card.png and post-replay.mp4.
"""

import argparse
import datetime as dt
import html
import json
import os

ARM_COLOURS = ["--arm0", "--arm1", "--arm2", "--arm3"]


def _seconds(ts, t0):
    return (dt.datetime.fromisoformat(ts.replace("Z", "+00:00")) - t0).total_seconds()


def arm_data(arm):
    """The figures and the per-call series of one arm, with times in seconds from its first call."""
    f, m = arm["figures"], arm["measure"]
    series = [p for p in m["series"] if p["ts"]]
    t0 = min(dt.datetime.fromisoformat(p["ts"].replace("Z", "+00:00")) for p in series)
    calls = sorted([round(_seconds(p["ts"], t0), 1), p["ctx"], p["out"], p["agent"]] for p in series)
    return dict(name=arm["arm"], tokens=f["tokens"], cost=f["cost"], usd=f["usd"], passed=f["passed"], of=f["of"],
                wall_min=f["wall_min"], peak=max(f["peak"] or 0, f["lead_peak"] or 0), agents=len({p["agent"] for p in series}) - 1,
                stopped=f["stopped"], calls=calls,
                alone=sum(1 for t in (arm.get("grade") or {}).get("tasks", [])
                          if t.get("hidden") != "pass" and t.get("hidden_alone") == "pass"))


def render(results, repo, arms=None):
    """arms: names to show, in order (default: all). The first is the reference; the headline is the second."""
    have = {a["arm"]: a for a in results["arms"] if a.get("figures") and a.get("measure")}
    shown = [arm_data(have[n]) for n in (arms or have) if n in have]
    if not shown:
        raise SystemExit("no arm has figures to show")
    data = json.dumps(dict(tier=results["tier"], date=results["date"], tasks=results["tasks"],
                           runs=results.get("runs_per_arm", 1), repo=repo, arms=shown,
                           headline=shown[1]["name"] if len(shown) > 1 else None), separators=(",", ":"))
    return PAGE.replace("__DATA__", data.replace("</", "<\\/")).replace("__TITLE__", html.escape(
        f"lean-agents run {results['date']}"))


PAGE = r"""<title>__TITLE__</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700&family=IBM+Plex+Sans:wght@400;500&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* Layout: one 16:9 card (the shareable image), then the replay lanes side by side. */
:root {
  --bg: #eef1f4; --card: #ffffff; --ink: #14202b; --muted: #5d6b78; --line: #d5dce3;
  --arm0: #c8553d; --arm1: #2b8a7e; --arm2: #3f5f9e; --arm3: #8a5aa8; --good: #2b8a5a; --bad: #b8433a;
  --display: "Bricolage Grotesque", "Segoe UI", system-ui, sans-serif;
  --body: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, Consolas, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #0e1419; --card: #151d24; --ink: #e8eef3; --muted: #93a3b1; --line: #2a3640;
  --arm0: #e47a62; --arm1: #4fb8aa; --arm2: #7d9ce0; --arm3: #b98ad6; --good: #5cc28b; --bad: #e0776d; color-scheme: dark } }
:root[data-theme="dark"] {
  --bg: #0e1419; --card: #151d24; --ink: #e8eef3; --muted: #93a3b1; --line: #2a3640;
  --arm0: #e47a62; --arm1: #4fb8aa; --arm2: #7d9ce0; --arm3: #b98ad6; --good: #5cc28b; --bad: #e0776d; color-scheme: dark }
body { background: var(--bg); color: var(--ink); font: 15px/1.5 var(--body); padding-inline: 16px; padding-block: 24px; }
main { max-width: 1200px; margin: 0 auto; display: grid; gap: 28px; }
h1, h2 { font-family: var(--display); font-weight: 700; text-wrap: balance; margin: 0; letter-spacing: -0.01em; }
.label { font: 500 11px/1.2 var(--mono); letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); }
.num { font-variant-numeric: tabular-nums; }
#card { background: var(--card); border: 1px solid var(--line); border-radius: 14px; aspect-ratio: 16 / 9; width: 100%;
  max-width: 100%; padding: clamp(16px, 3.2vw, 40px); display: grid; grid-template-rows: auto auto 1fr auto; gap: clamp(10px, 2vw, 22px); }
#card h1 { font-size: clamp(22px, 3.6vw, 44px); line-height: 1.05; }
.sub { color: var(--muted); font-size: clamp(12px, 1.3vw, 16px); margin-top: 6px; }
.arms { display: grid; grid-template-columns: repeat(var(--n), minmax(0, 1fr)); gap: clamp(10px, 2vw, 24px); align-items: start; }
.arm { display: grid; gap: clamp(4px, 0.8vw, 10px); min-width: 0; }
.arm .name { font: 700 clamp(14px, 1.6vw, 20px)/1.1 var(--display); display: flex; align-items: center; gap: 8px; }
.dot { width: 10px; height: 10px; border-radius: 50%; background: var(--c); flex: none; }
.big { font: 700 clamp(26px, 4.6vw, 58px)/1 var(--display); font-variant-numeric: tabular-nums; }
.delta { font: 500 clamp(12px, 1.4vw, 17px)/1.2 var(--mono); color: var(--c); min-height: 1.2em; }
.bar { height: 8px; border-radius: 4px; background: var(--line); overflow: hidden; }
.bar i { display: block; height: 100%; background: var(--c); border-radius: 4px; }
.facts { display: grid; grid-template-columns: auto 1fr; gap: 2px 10px; font: 400 clamp(11px, 1.15vw, 14px)/1.4 var(--mono); }
.facts dt { color: var(--muted); }
.facts dd { margin: 0; font-variant-numeric: tabular-nums; }
.pass { color: var(--good); } .fail { color: var(--bad); }
.foot { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 6px 16px; color: var(--muted); font: 400 clamp(10px, 1.05vw, 13px)/1.3 var(--mono); }
#replay { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: clamp(16px, 3vw, 32px); display: grid; gap: 18px; }
.rhead { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 8px 16px; }
.rhead h2 { font-size: clamp(20px, 2.6vw, 30px); }
.clock { font: 500 clamp(18px, 2.2vw, 26px)/1 var(--mono); font-variant-numeric: tabular-nums; }
.lanes { display: grid; grid-template-columns: repeat(var(--n), minmax(0, 1fr)); gap: clamp(10px, 2vw, 22px); }
.lane { display: grid; gap: 10px; min-width: 0; border-top: 3px solid var(--c); padding-top: 12px; }
.lane .tok { font: 700 clamp(24px, 3.4vw, 44px)/1 var(--display); font-variant-numeric: tabular-nums; }
.strip { display: block; width: 100%; height: 120px; border-bottom: 1px solid var(--line); }
.progress { height: 3px; background: var(--line); border-radius: 2px; overflow: hidden; }
.progress i { display: block; height: 100%; width: 0; background: var(--muted); }
.agents { display: flex; flex-wrap: wrap; gap: 5px; min-height: 14px; }
.agents b { width: 12px; height: 12px; border-radius: 3px; background: var(--c); opacity: 0.25; }
.state { font: 500 13px/1.3 var(--mono); color: var(--muted); min-height: 1.3em; }
.controls { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
button { font: 500 14px/1 var(--body); color: var(--ink); background: transparent; border: 1px solid var(--line); border-radius: 8px; padding: 9px 14px; cursor: pointer; }
button:focus-visible { outline: 2px solid var(--arm2); outline-offset: 2px; }
svg text { fill: var(--muted); font: 400 11px var(--mono); }
.chartwrap { min-width: 0; }
body.record { padding: 0; background: var(--card); }
body.record main { max-width: none; gap: 0; }
body.record #card, body.record .controls, body.record .note { display: none; }
body.record #replay { border: 0; border-radius: 0; min-height: 100vh; align-content: center; }
@media (max-width: 640px) { .arms, .lanes { grid-template-columns: 1fr; } #card { aspect-ratio: auto; } .strip { height: 70px; } }
</style>
<main>
  <section id="card" aria-label="Side-by-side result"></section>
  <section id="replay" aria-label="Replay of the run"></section>
</main>
<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById("data").textContent);
const N = D.arms.length;
document.documentElement.style.setProperty("--n", N);
const M = v => v >= 1e6 ? (v / 1e6).toFixed(1) + "M" : Math.round(v / 1e3) + "k";
const pct = (v, b) => (v - b) / b;
const sign = p => (p > 0 ? "+" : "−") + Math.abs(Math.round(p * 100)) + "%";
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const base = D.arms[0];
const maxTok = Math.max(...D.arms.map(a => a.tokens));

function card() {
  const best = D.arms.find(a => a.name === D.headline);
  const head = best ? `${sign(pct(best.tokens, base.tokens))} tokens, ${best.passed === best.of ? "hidden tests passed" : best.passed + "/" + best.of + " hidden tests"}`
                    : "One run";
  const arms = D.arms.map((a, i) => {
    const c = `var(--arm${i % 4})`;
    const d = i ? sign(pct(a.tokens, base.tokens)) + " vs " + esc(base.name) : "reference";
    const tests = a.passed === a.of ? `<span class="pass">✓ ${a.passed}/${a.of} passed</span>`
      : a.passed + a.alone === a.of ? `<span class="pass">✓ ${a.of}/${a.of} passed*</span>`
      : `<span class="fail">✗ ${a.passed}/${a.of} passed</span>`;
    return `<div class="arm" style="--c:${c}">
      <div class="name"><span class="dot"></span>${esc(a.name)}</div>
      <div class="big num">${M(a.tokens)}</div><div class="delta">${d}</div>
      <div class="bar" aria-hidden="true"><i style="width:${(a.tokens / maxTok * 100).toFixed(1)}%"></i></div>
      <dl class="facts">
        <dt>hidden tests</dt><dd>${tests}</dd>
        <dt>API cost</dt><dd>${a.usd != null ? "$" + a.usd.toFixed(2) : "-"}${i && a.usd != null && base.usd ? " (" + sign(pct(a.usd, base.usd)) + ")" : ""}</dd>
        <dt>wall clock</dt><dd>${Math.round(a.wall_min)} min${a.stopped ? " (stopped: " + esc(a.stopped) + ")" : ""}</dd>
        <dt>peak context</dt><dd>${M(a.peak)}</dd>
        <dt>subagents</dt><dd>${a.agents}</dd>
      </dl></div>`;
  }).join("");
  document.getElementById("card").innerHTML = `
    <div><div class="label">lean-agents · same task, same prompt, run side by side</div>
      <h1>${esc(head)}</h1>
      <div class="sub">${esc(D.tasks.join(", "))} in ${esc(D.tier)} tier · graded by the hidden tests from the real merged fix</div></div>
    <div class="arms">${arms}</div>
    <div class="chartwrap">${chart()}</div>
    <div class="foot"><span>${D.arms.some(a => a.alone) ? "* passed once its own clashing test files were set aside · " : ""}${D.runs === 1 ? "Single run per arm" : D.runs + " runs per arm"} · ${esc(D.date)} · tokens = context sent + output, summed over every model call</span><span>${esc(D.repo)}</span></div>`;
}

function cumulative(a) {
  let t = 0;
  return a.calls.map(c => (t += c[1] + c[2], [c[0], t]));
}

function chart() {
  const W = 1100, H = 210, L = 46, B = 20;
  const series = D.arms.map(cumulative);
  const xmax = Math.max(...series.map(s => s.length ? s[s.length - 1][0] : 0)) || 1;
  const ymax = Math.max(...series.map(s => s.length ? s[s.length - 1][1] : 0)) || 1;
  const x = v => L + v / xmax * (W - L - 8), y = v => H - B - v / ymax * (H - B - 8);
  const lines = series.map((s, i) => `<polyline fill="none" stroke="var(--arm${i % 4})" stroke-width="2.5" stroke-linejoin="round" points="${s.map(p => x(p[0]).toFixed(1) + "," + y(p[1]).toFixed(1)).join(" ")}"/>`).join("");
  const mins = Math.round(xmax / 60);
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Cumulative tokens over time per arm" style="width:100%;height:auto;display:block">
    <line x1="${L}" y1="${H - B}" x2="${W - 8}" y2="${H - B}" stroke="var(--line)"/>
    <line x1="${L}" y1="8" x2="${L}" y2="${H - B}" stroke="var(--line)"/>
    <text x="${L - 6}" y="14" text-anchor="end">${M(ymax)}</text><text x="${L - 6}" y="${H - B}" text-anchor="end">0</text>
    <text x="${L}" y="${H - 4}">0 min</text><text x="${W - 8}" y="${H - 4}" text-anchor="end">${mins} min</text>
    <text x="${L + 8}" y="20">tokens used so far</text>${lines}</svg>`;
}

// Replay: every model call lands at its real time, sped up so the longest run takes DURATION seconds.
// renderAt(seconds) draws any moment exactly, so a capture can step through it frame by frame.
const T = Math.max(...D.arms.map(a => a.calls.length ? a.calls[a.calls.length - 1][0] : 0)) || 1;
const DURATION = 20;
const WINDOW = T / 4;  // the context strip shows the last quarter of the run
const PEAK = Math.max(...D.arms.map(a => a.peak)) || 1;
const lanes = [];
let started = null, raf = null;

function replayShell() {
  document.getElementById("replay").innerHTML = `
    <div class="rhead"><div><div class="label">Replay · every model call at its real time, ${Math.round(T / DURATION)}× speed</div>
      <h2>Tokens and context as the run happened</h2></div>
      <div class="clock num" id="clock"></div></div>
    <div class="progress" aria-hidden="true"><i id="prog"></i></div>
    <div class="lanes">${D.arms.map((a, i) => `<div class="lane" style="--c:var(--arm${i % 4})">
      <div class="name" style="font:700 17px var(--display)">${esc(a.name)}</div>
      <div class="label">tokens used</div><div class="tok num" id="tok${i}">0</div>
      <div class="label">context size of each call, last ${Math.max(1, Math.round(WINDOW / 60))} min</div>
      <canvas class="strip" id="cv${i}" aria-hidden="true"></canvas>
      <div class="label">agents (lit while working)</div>
      <div class="agents" id="ag${i}"></div>
      <div class="state" id="st${i}"></div></div>`).join("")}</div>
    <div class="controls">
      <button id="play" type="button">Play replay</button>
      <span class="note label">The still frame shows the end of the run.</span></div>`;
  document.getElementById("play").addEventListener("click", play);
  D.arms.forEach((a, i) => {
    let t = 0;
    const cum = a.calls.map(c => (t += c[1] + c[2]));
    const ids = [...new Set(a.calls.map(c => c[3]))].filter(id => id !== 0);
    const first = new Map(), stamps = new Map();
    for (const c of a.calls) {
      if (!first.has(c[3])) first.set(c[3], c[0]);
      if (!stamps.has(c[3])) stamps.set(c[3], []);
      stamps.get(c[3]).push(c[0]);
    }
    const ag = document.getElementById("ag" + i);
    ag.innerHTML = ids.map(() => "<b></b>").join("");
    lanes.push({a, cum, ids, first, stamps, squares: [...ag.children], cv: document.getElementById("cv" + i),
                colour: getComputedStyle(ag.parentElement).getPropertyValue("--c").trim(),
                end: a.calls.length ? a.calls[a.calls.length - 1][0] : 0});
  });
}

function tokensAt(l, now) {
  // Linear between calls, so the counter climbs instead of jumping.
  const c = l.a.calls;
  let lo = 0, hi = c.length - 1;
  if (!c.length || now < c[0][0]) return 0;
  if (now >= c[hi][0]) return l.cum[hi];
  while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (c[mid][0] <= now) lo = mid; else hi = mid; }
  const f = (now - c[lo][0]) / (c[hi][0] - c[lo][0] || 1);
  return l.cum[lo] + f * (l.cum[hi] - l.cum[lo]);
}

function lastBefore(list, now) {
  let best = -Infinity;
  for (const t of list) { if (t <= now) best = t; else break; }
  return best;
}

function drawStrip(l, now) {
  const cv = l.cv, dpr = window.devicePixelRatio || 1;
  const w = Math.round(cv.clientWidth * dpr), h = Math.round(cv.clientHeight * dpr);
  if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; }
  const g = cv.getContext("2d");
  g.clearRect(0, 0, w, h);
  const from = now - WINDOW, bw = Math.max(2 * dpr, w / 160);
  g.fillStyle = l.colour;
  for (const c of l.a.calls) {
    if (c[0] > now) break;
    if (c[0] < from) continue;
    const x = (c[0] - from) / WINDOW * (w - bw);
    const bh = Math.max(1, c[1] / PEAK * (h - 2 * dpr));
    g.globalAlpha = 0.85;
    g.fillRect(x, h - bh, bw, bh);
  }
  g.globalAlpha = 1;
}

function renderAt(seconds) {
  const now = Math.max(0, Math.min(T, seconds / DURATION * T));
  document.getElementById("clock").textContent =
    `${String(Math.floor(now / 60)).padStart(2, "0")}:${String(Math.floor(now % 60)).padStart(2, "0")} into the run`;
  document.getElementById("prog").style.width = (now / T * 100).toFixed(2) + "%";
  const fade = Math.max(20, T / 40);
  for (const [i, l] of lanes.entries()) {
    document.getElementById("tok" + i).textContent = M(tokensAt(l, now));
    drawStrip(l, now);
    l.ids.forEach((id, k) => {
      const sq = l.squares[k];
      if (l.first.get(id) > now) { sq.style.opacity = 0; return; }
      const since = now - lastBefore(l.stamps.get(id), now);
      sq.style.opacity = now >= l.end ? 0.25 : (0.25 + 0.75 * Math.max(0, 1 - since / fade)).toFixed(3);
    });
    const done = now >= l.end;
    const st = document.getElementById("st" + i);
    const text = done
      ? (l.a.passed + l.a.alone === l.a.of ? `<span class="pass">✓ finished in ${Math.round(l.end / 60)} min, hidden tests passed${l.a.passed < l.a.of ? "*" : ""}</span>`
                               : `<span class="fail">✗ finished in ${Math.round(l.end / 60)} min, ${l.a.passed}/${l.a.of} hidden tests</span>`)
      : "working…";
    if (st.innerHTML !== text) st.innerHTML = text;
  }
  return now >= T;
}
window.renderAt = renderAt;
window.REPLAY_SECONDS = DURATION;

function tick(ts) {
  if (started === null) started = ts;
  if (!renderAt((ts - started) / 1000)) raf = requestAnimationFrame(tick);
  else started = null;
}

function play() {
  cancelAnimationFrame(raf);
  started = null;
  raf = requestAnimationFrame(tick);
}

card();
replayShell();
renderAt(DURATION);
addEventListener("resize", () => renderAt(DURATION));
if (location.hash === "#record") document.body.classList.add("record");
</script>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results")
    ap.add_argument("--repo", default="github.com/Ben87812/lean-agents")
    ap.add_argument("--arms", help="comma-separated arms to show, reference first (default: all)")
    args = ap.parse_args()
    with open(args.results, encoding="utf-8") as f:
        results = json.load(f)
    out = os.path.join(os.path.dirname(os.path.abspath(args.results)), "post.html")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(render(results, args.repo, args.arms.split(",") if args.arms else None))
    print(out)


if __name__ == "__main__":
    main()
