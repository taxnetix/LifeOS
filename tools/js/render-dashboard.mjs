#!/usr/bin/env node
/**
 * Render a self-contained financial dashboard.
 *
 * Hard constraint (brief §7): the output must open correctly with NO network
 * access — inline CSS, inline SVG, no CDN, no build step, no charting library.
 * A dashboard that needs the internet to render is useless in the situation
 * this system exists for.
 *
 * Node owns rendering; Python owns the numbers. This file computes nothing it
 * was not handed — every figure arrives from lifeos.analyse via stdin, already
 * traced to its source records.
 *
 *   .venv/bin/python -m lifeos.analyse | node tools/js/render-dashboard.mjs > out.html
 */

import { readFileSync } from "node:fs";

const input = JSON.parse(readFileSync(process.argv[2] ?? 0, "utf8"));
const flow = input.cashflow;
const nw = input.net_worth;
const variance = input.budget_variance ?? [];

/**
 * Format cents as rands. Deliberately NOT toLocaleString: en-ZA uses a comma as
 * the DECIMAL separator and a space for thousands, so normalising commas to
 * spaces silently destroys the decimal point — R426 760,00 becomes R426 760 00.
 * Formatting is done explicitly here, and matches Python's money.fmt exactly so
 * the same number reads the same in a report and on a dashboard.
 */
const R = (cents) => {
  const neg = cents < 0;
  const abs = Math.abs(cents);
  const whole = String(Math.floor(abs / 100)).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  const frac = String(abs % 100).padStart(2, "0");
  return (neg ? "-R" : "R") + whole + "." + frac;
};
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const monthLabel = (m) => {
  const [y, mo] = m.split("-");
  return ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][+mo - 1] + " " + y.slice(2);
};

/* ── Inline SVG: grouped bars for in/out plus a net line ──────────────────── */
function cashflowChart(series) {
  if (!series.length) return `<p class="empty">No transactions yet.</p>`;
  const W = 720, H = 260, PAD = { t: 16, r: 16, b: 34, l: 68 };
  const iw = W - PAD.l - PAD.r, ih = H - PAD.t - PAD.b;
  const max = Math.max(...series.flatMap((s) => [s.in_cents, Math.abs(s.out_cents)]), 1);
  const scale = (v) => (v / max) * ih;
  const bw = Math.min(46, (iw / series.length) * 0.34);

  let bars = "", labels = "", line = [];
  series.forEach((s, i) => {
    const cx = PAD.l + (iw / series.length) * (i + 0.5);
    const hIn = scale(s.in_cents), hOut = scale(Math.abs(s.out_cents));
    bars += `<rect x="${(cx - bw - 3).toFixed(1)}" y="${(PAD.t + ih - hIn).toFixed(1)}" width="${bw}" height="${hIn.toFixed(1)}" class="bar-in"><title>${monthLabel(s.month)} in: ${R(s.in_cents)}</title></rect>`;
    bars += `<rect x="${(cx + 3).toFixed(1)}" y="${(PAD.t + ih - hOut).toFixed(1)}" width="${bw}" height="${hOut.toFixed(1)}" class="bar-out"><title>${monthLabel(s.month)} out: ${R(s.out_cents)}</title></rect>`;
    labels += `<text x="${cx.toFixed(1)}" y="${H - 12}" class="axis" text-anchor="middle">${monthLabel(s.month)}</text>`;
    line.push(`${cx.toFixed(1)},${(PAD.t + ih - scale(s.net_cents)).toFixed(1)}`);
  });

  let grid = "";
  for (let g = 0; g <= 4; g++) {
    const y = PAD.t + ih - (ih / 4) * g;
    grid += `<line x1="${PAD.l}" y1="${y.toFixed(1)}" x2="${W - PAD.r}" y2="${y.toFixed(1)}" class="grid"/>`;
    grid += `<text x="${PAD.l - 8}" y="${(y + 4).toFixed(1)}" class="axis" text-anchor="end">${R((max / 4) * g).replace(".00", "")}</text>`;
  }

  return `<svg viewBox="0 0 ${W} ${H}" class="chart" role="img" aria-label="Monthly money in, money out and net">
    ${grid}${bars}
    <polyline points="${line.join(" ")}" class="net-line"/>
    ${line.map((p) => { const [x, y] = p.split(","); return `<circle cx="${x}" cy="${y}" r="3.5" class="net-dot"/>`; }).join("")}
    ${labels}
  </svg>`;
}

/* ── Horizontal bars, personal and business kept visually distinct ────────── */
function categoryChart(byCategory) {
  const rows = Object.entries(byCategory)
    .map(([k, v]) => { const [scope, cat] = k.split(":"); return { scope, cat, cents: Math.abs(v.cents), n: v.n }; })
    .filter((r) => r.cents > 0)
    .sort((a, b) => b.cents - a.cents)
    .slice(0, 12);
  if (!rows.length) return `<p class="empty">No categorised spending yet.</p>`;
  const max = Math.max(...rows.map((r) => r.cents));
  return `<table class="bars">${rows.map((r) => `
    <tr>
      <td class="cat">${esc(r.cat)} <span class="scope ${r.scope}">${r.scope === "business" ? "biz" : "personal"}</span></td>
      <td class="track"><div class="fill ${r.scope}" style="width:${((r.cents / max) * 100).toFixed(1)}%"></div></td>
      <td class="amt">${R(-r.cents)}</td>
      <td class="n">${r.n}</td>
    </tr>`).join("")}</table>`;
}

const t = flow.totals;
const savings = t.savings_rate_pct;
const savingsBand = savings === null ? "mid" : savings >= 20 ? "good" : savings >= 10 ? "mid" : "poor";

const html = `<!doctype html><html lang="en-ZA"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>LifeOS — financial dashboard</title>
<style>
:root { color-scheme: light dark; --fg:#16181d; --muted:#6b7280; --bg:#fff; --card:#f7f8fa;
        --line:#e3e6ea; --in:#1a7f37; --out:#a40e26; --biz:#5b4bc4; --accent:#16181d; }
@media (prefers-color-scheme: dark) {
  :root { --fg:#e8eaed; --muted:#9aa3ad; --bg:#14161a; --card:#1c1f25; --line:#2b3038;
          --in:#4ec97a; --out:#f4707f; --biz:#a898ff; --accent:#e8eaed; } }
* { box-sizing:border-box; }
body { margin:0; padding:28px 20px 56px; background:var(--bg); color:var(--fg);
       font:15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }
.wrap { max-width:860px; margin:0 auto; }
h1 { font-size:26px; margin:0 0 2px; letter-spacing:-0.4px; }
h2 { font-size:15px; text-transform:uppercase; letter-spacing:1.2px; color:var(--muted);
     margin:34px 0 12px; font-weight:600; }
.sub { color:var(--muted); margin:0 0 22px; font-size:14px; }
.tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; }
.tile { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px; }
.tile .k { font-size:11px; text-transform:uppercase; letter-spacing:1px; color:var(--muted); }
.tile .v { font-size:23px; font-weight:600; margin-top:4px; letter-spacing:-0.5px; }
.tile .m { font-size:12px; color:var(--muted); margin-top:2px; }
.v.pos { color:var(--in); } .v.neg { color:var(--out); }
.v.good { color:var(--in); } .v.mid { color:#9a6700; } .v.poor { color:var(--out); }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:16px; }
.chart { width:100%; height:auto; display:block; }
.grid { stroke:var(--line); stroke-width:1; }
.axis { fill:var(--muted); font-size:10px; }
.bar-in { fill:var(--in); opacity:.85; } .bar-out { fill:var(--out); opacity:.85; }
.net-line { fill:none; stroke:var(--accent); stroke-width:2; stroke-dasharray:4 3; }
.net-dot { fill:var(--accent); }
table.bars { width:100%; border-collapse:collapse; }
table.bars td { padding:5px 8px 5px 0; vertical-align:middle; font-size:13.5px; }
td.cat { width:34%; white-space:nowrap; }
td.track { width:40%; }
td.amt { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
td.n { text-align:right; color:var(--muted); font-size:12px; width:36px; }
.fill { height:9px; border-radius:5px; background:var(--out); min-width:2px; }
.fill.business { background:var(--biz); }
.scope { font-size:10px; padding:1px 5px; border-radius:3px; background:var(--line); color:var(--muted); }
.scope.business { background:var(--biz); color:#fff; }
.legend { display:flex; gap:16px; font-size:12px; color:var(--muted); margin-top:10px; }
.swatch { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:5px; }
.note { background:var(--card); border-left:3px solid #9a6700; padding:11px 14px;
        border-radius:0 6px 6px 0; font-size:13.5px; margin-top:12px; }
.empty { color:var(--muted); font-style:italic; }
footer { margin-top:40px; padding-top:16px; border-top:1px solid var(--line);
         color:var(--muted); font-size:12px; }
</style></head><body><div class="wrap">

<h1>Financial dashboard</h1>
<p class="sub">${flow.months.length ? esc(monthLabel(flow.months[0])) + " – " + esc(monthLabel(flow.months.at(-1))) : "no data"}
 · generated ${esc((input.at ?? "").slice(0, 10))}</p>

<div class="tiles">
  <div class="tile"><div class="k">Money in</div><div class="v pos">${R(t.in_cents)}</div><div class="m">all accounts</div></div>
  <div class="tile"><div class="k">Money out</div><div class="v neg">${R(t.out_cents)}</div><div class="m">excl. transfers</div></div>
  <div class="tile"><div class="k">Net</div><div class="v ${t.net_cents >= 0 ? "pos" : "neg"}">${R(t.net_cents)}</div><div class="m">over ${flow.months.length} month${flow.months.length === 1 ? "" : "s"}</div></div>
  <div class="tile"><div class="k">Savings rate</div><div class="v ${savingsBand}">${savings === null ? "—" : savings + "%"}</div><div class="m">personal only</div></div>
</div>

<h2>Monthly cashflow</h2>
<div class="card">
  ${cashflowChart(flow.series)}
  <div class="legend">
    <span><i class="swatch" style="background:var(--in)"></i>money in</span>
    <span><i class="swatch" style="background:var(--out)"></i>money out</span>
    <span><i class="swatch" style="background:var(--accent)"></i>net (dashed)</span>
  </div>
</div>

<h2>Where it goes</h2>
<div class="card">${categoryChart(flow.by_category)}</div>

<h2>Personal and business</h2>
<div class="tiles">
${Object.entries(flow.by_entity).map(([ref, v]) => `
  <div class="tile"><div class="k">${esc(ref)}</div>
    <div class="v ${v.in + v.out >= 0 ? "pos" : "neg"}">${R(v.in + v.out)}</div>
    <div class="m">${R(v.in)} in · ${R(v.out)} out · ${v.n} txns</div></div>`).join("")}
</div>

${variance.length ? `<h2>Budget variance</h2><div class="card"><table class="bars">
${variance.map((v) => `<tr><td class="cat">${esc(v.category)}</td>
  <td class="track"><div class="fill ${v.breached ? "" : "business"}" style="width:${Math.min(100, Math.abs(v.delta_pct)).toFixed(0)}%"></div></td>
  <td class="amt">${v.delta_pct > 0 ? "+" : ""}${v.delta_pct}%</td>
  <td class="n">${v.breached ? "!" : ""}</td></tr>`).join("")}
</table></div>` : ""}

<h2>Position</h2>
<div class="tiles">
  <div class="tile"><div class="k">Cash at bank</div><div class="v ${nw.net_cents >= 0 ? "pos" : "neg"}">${R(nw.net_cents)}</div>
    <div class="m">${nw.components.length} account${nw.components.length === 1 ? "" : "s"}, as at ${esc(nw.as_at)}</div></div>
</div>
${nw.partial ? `<div class="note"><strong>This is a cash position, not a net worth.</strong> ${esc(nw.note)}</div>` : ""}

<footer>
  Every figure traces to a filed source document — run <code>/audit</code> to walk any of them back to a page.
  Transfers between own accounts are excluded so the same rand is never counted twice.
  This file is self-contained: no network access is needed to read it, now or in ten years.
</footer>
</div></body></html>`;

process.stdout.write(html);
