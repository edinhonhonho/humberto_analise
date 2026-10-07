// Formatação compatível com o Python (pt-BR, repr de float, round-half-even, json.dumps).
// Sem dependências, sem DOM.

export const nn = (v) => v !== null && v !== undefined && !(typeof v === "number" && Number.isNaN(v));
/** null/undefined -> NaN (como o pandas faz em colunas numéricas). */
export const num = (v) => (v === null || v === undefined || v === "" ? NaN : Number(v));
export const finito = (v) => typeof v === "number" && Number.isFinite(v);

// ---------------------------------------------------------------- f"{x:.{nd}f}" exato
function fixoAbs(a, nd) {
  if (a >= 1e21) {
    const s = BigInt(a).toString();
    return nd > 0 ? s + "." + "0".repeat(nd) : s;
  }
  const t = a.toFixed(Math.min(100, nd + 30));
  const p = t.indexOf(".");
  const resto = t.slice(p + 1 + nd);
  if (/^50*$/.test(resto)) {
    // empate exato: o Python arredonda para o par
    const cortado = t.slice(0, p) + t.slice(p + 1, p + 1 + nd);
    let n = BigInt(cortado);
    if (n % 2n === 1n) n += 1n;
    let s = n.toString();
    if (nd === 0) return s;
    s = s.padStart(nd + 1, "0");
    return s.slice(0, s.length - nd) + "." + s.slice(s.length - nd);
  }
  return a.toFixed(nd);
}

/** f"{x:.{nd}f}" (x finito). */
export function fmtF(x, nd) {
  const neg = x < 0 || Object.is(x, -0);
  return (neg ? "-" : "") + fixoAbs(Math.abs(x), nd);
}

/** round(x, nd) do Python para float (correto, half-even sobre o valor binário exato). */
export function pyRound(x, nd) {
  if (!Number.isFinite(x)) return x;
  return Number(fmtF(x, nd));
}

/** round(x) do Python (half-even). */
export function roundPar(x) {
  const f = Math.floor(x), d = x - f;
  if (d < 0.5) return f;
  if (d > 0.5) return f + 1;
  return f % 2 === 0 ? f : f + 1;
}

export function fnum(x, dec = 0) {
  if (x === null || x === undefined || typeof x !== "number" || !Number.isFinite(x)) return "–";
  const s = fmtF(x, dec);
  const neg = s[0] === "-";
  const b = neg ? s.slice(1) : s;
  const p = b.indexOf(".");
  const ip = p < 0 ? b : b.slice(0, p);
  const fp = p < 0 ? "" : b.slice(p + 1);
  const g = ip.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return (neg ? "-" : "") + g + (fp ? "," + fp : "");
}

export function fdyn(x) {
  if (x === null || x === undefined || (typeof x === "number" && Number.isNaN(x))) return "–";
  const a = Math.abs(x);
  return fnum(x, a >= 100 ? 0 : a >= 10 ? 1 : a >= 0.1 ? 2 : 3);
}

export function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#x27;");
}

// ---------------------------------------------------------------- repr(float) do Python
export function pyFloatRepr(x) {
  if (Number.isNaN(x)) return "nan";
  if (!Number.isFinite(x)) return x > 0 ? "inf" : "-inf";
  if (x === 0) return Object.is(x, -0) ? "-0.0" : "0.0";
  const neg = x < 0;
  const e = Math.abs(x).toExponential(); // dígitos mais curtos que identificam o valor
  const [m, ex] = e.split("e");
  const digs = m.replace(".", "");
  const exp = parseInt(ex, 10);
  const decpt = exp + 1;
  let s;
  if (decpt > 16 || decpt < -3) {
    s = digs[0] + (digs.length > 1 ? "." + digs.slice(1) : "") + "e" + (exp < 0 ? "-" : "+") + String(Math.abs(exp)).padStart(2, "0");
  } else if (decpt <= 0) {
    s = "0." + "0".repeat(-decpt) + digs;
  } else if (digs.length <= decpt) {
    s = digs + "0".repeat(decpt - digs.length) + ".0";
  } else {
    s = digs.slice(0, decpt) + "." + digs.slice(decpt);
  }
  return (neg ? "-" : "") + s;
}

/** Número com tipo Python explícito (int ou float), para reproduzir f-strings. */
export class PN {
  constructor(v, fl) { this.v = v; this.fl = fl; }
  toString() { return this.fl ? pyFloatRepr(this.v) : String(this.v); }
}
export const I = (v) => new PN(v, false);
export const Fl = (v) => new PN(v, true);
export const pAdd = (a, b) => new PN(a.v + b.v, a.fl || b.fl);
export const pSub = (a, b) => new PN(a.v - b.v, a.fl || b.fl);

/** Marca um valor que o json.dumps escreveria como float (ex.: 43.0). */
export class PF { constructor(v) { this.v = v; } }

// ---------------------------------------------------------------- json.dumps(ensure_ascii=False), separadores padrão
export function pyJson(o) {
  if (o === null || o === undefined) return "null";
  if (o instanceof PF) return pyFloatRepr(o.v);
  if (typeof o === "string") return JSON.stringify(o);
  if (typeof o === "boolean") return o ? "true" : "false";
  if (typeof o === "number") {
    if (Number.isNaN(o)) return "NaN";
    if (!Number.isFinite(o)) return o > 0 ? "Infinity" : "-Infinity";
    return Number.isInteger(o) ? String(o) : pyFloatRepr(o);
  }
  if (Array.isArray(o)) return "[" + o.map(pyJson).join(", ") + "]";
  return "{" + Object.entries(o).map(([k, v]) => JSON.stringify(k) + ": " + pyJson(v)).join(", ") + "}";
}

/** svgviz._num: None se vazio; int se inteiro; senão round(f, nd). */
export function numJ(v, nd = 4) {
  if (v === null || v === undefined) return null;
  const f = typeof v === "boolean" ? Number(v) : typeof v === "string" ? (v.trim() === "" ? NaN : Number(v)) : Number(v);
  if (!Number.isFinite(f)) return null;
  return Number.isInteger(f) && Math.abs(f) < 1e15 ? f : pyRound(f, nd);
}

const PEQUENAS = new Set(["de", "da", "do", "das", "dos", "e"]);
const cap = (p) => { const a = Array.from(p); return a.length ? a[0].toUpperCase() + a.slice(1).join("").toLowerCase() : ""; };
export function nomePt(s) {
  if (s === null || s === undefined || (typeof s === "number" && Number.isNaN(s))) return "–";
  const ws = String(s).toLowerCase().split(" ");
  return ws.map((w, i) => (i && PEQUENAS.has(w) ? w : w.split("-").map(cap).join("-"))).join(" ");
}

/** Soma por pares do numpy (np.sum em float64). */
export function npSum(a) {
  const n = a.length;
  if (n < 8) { let r = 0; for (let i = 0; i < n; i++) r += a[i]; return r; }
  return pw(a, 0, n);
}
function pw(a, o, n) {
  if (n < 8) { let r = 0; for (let i = 0; i < n; i++) r += a[o + i]; return r; }
  if (n <= 128) {
    const r = [a[o], a[o + 1], a[o + 2], a[o + 3], a[o + 4], a[o + 5], a[o + 6], a[o + 7]];
    let i;
    for (i = 8; i < n - (n % 8); i += 8) for (let j = 0; j < 8; j++) r[j] += a[o + i + j];
    let res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
    for (; i < n; i++) res += a[o + i];
    return res;
  }
  let n2 = Math.floor(n / 2);
  n2 -= n2 % 8;
  return pw(a, o, n2) + pw(a, o + n2, n - n2);
}
