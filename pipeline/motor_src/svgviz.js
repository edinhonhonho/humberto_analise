// Porte de eleicao/svgviz.py (modo "blocos": mapas e tabelas viram dados). Sem DOM.
import { esc, fnum, fdyn, fmtF, pyJson, PF, PN, I, Fl, pAdd, pSub, roundPar, num } from "./format.js";

export const SEQ_STEPS = ["s1", "s2", "s3", "s4", "s5", "s6"];

// ---------------------------------------------------------------- np.quantile (linear), np.unique, np.digitize
function linspace(a, b, n) {
  if (n === 1) return [a];
  const step = (b - a) / (n - 1);
  const y = [];
  for (let i = 0; i < n; i++) y.push(i * step + a);
  y[n - 1] = b;
  return y;
}

function quantileLinear(sorted, q) {
  const n = sorted.length;
  const virt = (n - 1) * q;
  if (virt >= n - 1) return sorted[n - 1];
  const prev = Math.floor(virt);
  const t = virt - prev;
  const a = sorted[prev], b = sorted[prev + 1];
  const diff = b - a;
  let lerp = a + diff * t;
  if (t >= 0.5) lerp = b - diff * (1 - t);
  return lerp;
}

/** Classes por quantil entre os valores > 0. Devolve [classes, legenda [[classe, rótulo]]]. */
export function classesQuantil(values, k = 6, unit = "", inteiro = false) {
  const v = Array.from(values, (x) => (x === null || x === undefined ? NaN : Number(x)));
  const pos = v.filter((x) => Number.isFinite(x) && x > 0).sort((a, b) => a - b);
  const f = inteiro ? (x) => fnum(x, 0) : fdyn;
  if (pos.length === 0) {
    return [v.map((x) => (!Number.isFinite(x) ? "nd" : "z")), [["z", "sem votos"]]];
  }
  let edges = linspace(0, 1, k + 1).map((q) => quantileLinear(pos, q));
  edges = edges.filter((x, i) => i === 0 || x !== edges[i - 1]); // já ordenado: unique
  if (edges.length < 2) edges = [edges[0], edges[0] + 1e-9];
  const n = edges.length - 1;
  const steps = n > 1 ? linspace(0, SEQ_STEPS.length - 1, n).map((x) => SEQ_STEPS[roundPar(x)]) : [SEQ_STEPS[3]];
  const inner = edges.slice(1, -1);
  const cls = v.map((x) => {
    if (!Number.isFinite(x)) return "nd";
    if (x <= 0) return "z";
    let i = 0;
    while (i < inner.length && inner[i] < x) i++; // digitize(right=True)
    return steps[Math.min(i, n - 1)];
  });
  const legend = v.some((x) => x === 0) ? [["z", "sem votos"]] : [];
  for (let i = 0; i < n; i++) legend.push([steps[i], `${f(edges[i])} – ${f(edges[i + 1])}${unit}`]);
  if (v.some((x) => !Number.isFinite(x))) legend.push(["nd", "sem dado"]);
  return [cls, legend];
}

/** Quociente locacional ancorado em 1. */
export function classesQl(values) {
  const cortes = [[1, "s1", "abaixo da média (< 1)"], [2, "s3", "1 a 2 vezes a média"], [5, "s4", "2 a 5 vezes"],
    [10, "s5", "5 a 10 vezes"], [Infinity, "s6", "mais de 10 vezes"]];
  const cls = Array.from(values, (x) => {
    x = x === null || x === undefined ? NaN : Number(x);
    if (!Number.isFinite(x)) return "nd";
    if (x <= 0) return "z";
    return cortes.find(([lim]) => x < lim)[1];
  });
  return [cls, [["z", "sem votos"]].concat(cortes.map(([, c, r]) => [c, r]))];
}

/** Classes categóricas: mapa {valor: classe}; legenda na ordem dada, com contagem. */
export function classesCategoria(values, mapa, ordem) {
  const cls = values.map((v) => (typeof v === "string" && Object.hasOwn(mapa, v) ? mapa[v] : "nd"));
  const cont = new Map();
  for (const v of values) cont.set(v, (cont.get(v) || 0) + 1);
  const legend = ordem.filter((o) => Object.hasOwn(mapa, o)).map((o) => [mapa[o], `${o} (${cont.get(o) || 0})`]);
  return [cls, legend];
}

// ---------------------------------------------------------------- geometria compartilhada
/** <svg> com os traçados dos municípios (polys: [{id, d}]). */
export function geoDefs(polys) {
  const ps = polys.filter((p) => p.id !== null && p.id !== undefined && p.d)
    .map((p) => `<path id="g${p.id}" d="${p.d}" vector-effect="non-scaling-stroke"/>`).join("");
  return `<svg class="defs" width="0" height="0" aria-hidden="true" focusable="false"><defs>${ps}</defs></svg>`;
}

// ---------------------------------------------------------------- bloco de mapa (modo blocos)
export function mapBloco(uid, polys, metrics, vb, aria = "Mapa") {
  const tp = {};
  for (const p of polys) tp[String(Math.trunc(Number(p.id)))] = p.tip;
  return {
    t: "map", id: uid, vb, aria,
    m: metrics.map((m) => ({ key: m.key, label: m.label, note: m.note ?? "", legend: m.legend.map((x) => [x[0], x[1]]) })),
    i: polys.map((p) => Math.trunc(Number(p.id))), k: polys.map((p) => p.cls.join(" ")), tp,
  };
}

// ---------------------------------------------------------------- barras horizontais
const gcode = (s) => Array.from(String(s)).length;

function barSvg(rows, aria, unit = "", width = 760) {
  if (!rows.length) return "";
  const f = 7.2 * Math.max(...rows.map((r) => gcode(r.label))) + 18;
  let labW = f > 80 ? Fl(f) : I(80);
  labW = labW.v < 230 ? labW : I(230);
  const right = I(70), bh = I(22), gap = I(10), top = I(4);
  const H = top.v + rows.length * (bh.v + gap.v);
  let vmax = Math.max(...rows.map((r) => r.value));
  vmax = vmax || 1;
  const plotW = pSub(pSub(I(width), labW), right);
  const out = [`<svg class="bars" viewBox="0 0 ${width} ${H}" role="img" aria-label="${esc(aria)}">`];
  rows.forEach((r, i) => {
    const y = I(top.v + i * (bh.v + gap.v));
    const wv = plotW.v * r.value / vmax;
    const w = Fl(wv > 2 ? wv : 2);
    const x0 = labW;
    const rr = w.v / 2 < 4 ? Fl(w.v / 2) : I(4);
    const xw = pAdd(x0, w);
    const d = `M${x0}`.concat(` ${y}H${pSub(xw, rr)}Q${xw} ${y} ${xw} ${pAdd(y, rr)}V${pSub(pAdd(y, bh), rr)}`,
      `Q${xw} ${pAdd(y, bh)} ${pSub(xw, rr)} ${pAdd(y, bh)}H${x0}Z`);
    const ty = pAdd(pAdd(y, Fl(bh.v / 2)), I(4));
    out.push(`<g class="row${r.hl ? " hl" : ""}" data-tip="${esc(pyJson(r.tip))}">`
      + `<rect class="hit" x="0" y="${pSub(y, Fl(gap.v / 2))}" width="${width}" height="${bh.v + gap.v}"/>`
      + `<text class="lab" x="${pSub(labW, I(8))}" y="${ty}" text-anchor="end">${esc(r.label)}</text>`
      + `<path class="bar" d="${d}"/>`
      + `<text class="val" x="${pAdd(pAdd(x0, w), I(6))}" y="${ty}">${esc(r.fmt)}${esc(unit)}</text></g>`);
  });
  out.push("</svg>");
  return out.join("");
}

/** Barras horizontais: SVG no computador e lista com barras em HTML no celular. */
export function barChart(rows, aria, unit = "", width = 760) {
  const svg = barSvg(rows, aria, unit, width);
  if (!svg) return "";
  const vmax = Math.max(...rows.map((r) => r.value)) || 1;
  const itens = rows.map((r) =>
    `<li class="${r.hl ? "hl" : ""}" data-tip="${esc(pyJson(r.tip))}">`
    + `<span class="hn">${esc(r.label)}</span><b class="hv">${esc(r.fmt)}${esc(unit)}</b>`
    + `<i class="hb"><u style="width:${fmtF(Math.max(1.5, 100 * r.value / vmax), 1)}%"></u></i></li>`).join("");
  return `<div class="barwrap">${svg}<ul class="hbars" aria-label="${esc(aria)}">${itens}</ul></div>`;
}

// ---------------------------------------------------------------- Pareto
export function paretoChart(series, marcos, xmax) {
  return pareto(series, marcos, xmax, 760, 300, "vd") + pareto(series, marcos, xmax, 420, 330, "vm");
}

function pareto(series, marcos, xmax, width, height, cls) {
  const [ml, mr, mt, mb] = [44, 22, 12, 34];
  const pw = width - ml - mr, ph = height - mt - mb;
  const sx = (x) => ml + (pw * (x - 1)) / Math.max(xmax - 1, 1);
  const sy = (y) => mt + ph * (1 - y / 100);
  const f1 = (x) => fmtF(x, 1);
  const ser = series.filter((r) => r[0] <= xmax);
  const pts = ser.map((r) => [sx(r[0]), sy(r[3].v)]);
  const line = "M" + pts.map(([x, y]) => `${f1(x)} ${f1(y)}`).join("L");
  const area = line + `L${f1(pts[pts.length - 1][0])} ${f1(sy(0))}L${f1(pts[0][0])} ${f1(sy(0))}Z`;
  const g = [];
  for (const v of [0, 25, 50, 75, 100]) {
    g.push(`<line class="grid" x1="${ml}" x2="${width - mr}" y1="${f1(sy(v))}" y2="${f1(sy(v))}"/>`
      + `<text class="tick" x="${ml - 8}" y="${f1(sy(v) + 4)}" text-anchor="end">${v}%</text>`);
  }
  let step = xmax <= 12 ? 1 : xmax <= 60 ? 5 : xmax <= 150 ? 10 : 50;
  if (width < 500 && step > 1) step *= 2;
  const xt = [1];
  for (let x = step; x <= xmax; x += step) if (x !== 1) xt.push(x);
  for (const x of xt) g.push(`<text class="tick" x="${f1(sx(x))}" y="${height - 12}" text-anchor="middle">${x}</text>`);
  const mk = [];
  for (const m of marcos) {
    if (m.x > xmax) continue;
    const cx = sx(m.x), cy = sy(m.y);
    const anchor = cx < width * (width < 500 ? 0.5 : 0.65) ? "start" : "end";
    const dx = anchor === "start" ? 12 : -12;
    mk.push(`<circle class="dot" cx="${f1(cx)}" cy="${f1(cy)}" r="5"/>`
      + `<text class="dl" x="${f1(cx + dx)}" y="${f1(cy + 18)}" text-anchor="${anchor}">${esc(m.rotulo)}</text>`);
  }
  const data = pyJson({ s: ser, ml, pw, mt, ph, xmax, w: width, h: height });
  return `<div class="pareto ${cls}"><svg viewBox="0 0 ${width} ${height}" role="img" `
    + `aria-label="Curva de concentração: percentual acumulado dos votos por município">`
    + `${g.join("")}<path class="area" d="${area}"/><path class="ln" d="${line}"/>${mk.join("")}`
    + `<g class="xh" hidden><line class="xl" y1="${mt}" y2="${mt + ph}"/><circle class="dot" r="5"/></g>`
    + `<rect class="cap" x="${ml}" y="${mt}" width="${pw}" height="${ph}" fill="transparent"/></svg>`
    + `<div class="axcap">Municípios, do mais votado ao menos votado</div>`
    + `<script type="application/json" class="pdat">${data}</script></div>`;
}

export { PF, num };
