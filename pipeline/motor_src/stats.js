// Estatística à mão (sem dependências): PRNG, pesos espaciais, Moran / LISA / Moran bivariado (fórmulas do esda 2.x),
// distribuição t de Student, Spearman (scipy.stats.spearmanr) e álgebra de mínimos quadrados (QR de Householder).

// ------------------------------------------------------------------------------------------ PRNG
export function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// embaralha `a` (Float64Array/Int32Array) no lugar, Fisher-Yates, sem alocar
function embaralhar(a, rng) {
  for (let i = a.length - 1; i > 0; i--) {
    const j = (rng() * (i + 1)) | 0;
    const t = a[i]; a[i] = a[j]; a[j] = t;
  }
}

// ------------------------------------------------------------------------------------------ utilidades
export const eFinito = Number.isFinite;

export function todosFinitos(y) {
  for (let i = 0; i < y.length; i++) if (!Number.isFinite(y[i])) return false;
  return true;
}

// np.allclose(y, y[0])
export function todosIguais(y) {
  const y0 = y[0];
  for (let i = 1; i < y.length; i++) if (!(Math.abs(y[i] - y0) <= 1e-8 + 1e-5 * Math.abs(y0))) return false;
  return true;
}

export function media(y) { let s = 0; for (let i = 0; i < y.length; i++) s += y[i]; return s / y.length; }
export function desvio(y, ddof = 0) {
  const m = media(y); let s = 0;
  for (let i = 0; i < y.length; i++) { const d = y[i] - m; s += d * d; }
  return Math.sqrt(s / (y.length - ddof));
}

// ranks "average" (scipy.stats.rankdata)
export function rankMedio(v) {
  const n = v.length, idx = new Int32Array(n);
  for (let i = 0; i < n; i++) idx[i] = i;
  idx.sort((a, b) => v[a] - v[b]);
  const r = new Float64Array(n);
  for (let i = 0; i < n;) {
    let j = i;
    while (j + 1 < n && v[idx[j + 1]] === v[idx[i]]) j++;
    const m = (i + j) / 2 + 1;
    for (let k = i; k <= j; k++) r[idx[k]] = m;
    i = j + 1;
  }
  return r;
}

export function pearson(a, b) {
  const n = a.length, ma = media(a), mb = media(b);
  let sab = 0, saa = 0, sbb = 0;
  for (let i = 0; i < n; i++) { const x = a[i] - ma, y = b[i] - mb; sab += x * y; saa += x * x; sbb += y * y; }
  return sab / Math.sqrt(saa * sbb);
}

// ------------------------------------------------------------------------------------------ t de Student
function lgamma(x) {
  if (x < 0.5) return Math.log(Math.PI / Math.abs(Math.sin(Math.PI * x))) - lgamma(1 - x);
  x -= 1;
  const g = 7;
  const c = [0.99999999999980993, 676.5203681218851, -1259.1392167224028, 771.32342877765313,
    -176.61502916214059, 12.507343278686905, -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7];
  let a = c[0];
  const t = x + g + 0.5;
  for (let i = 1; i < g + 2; i++) a += c[i] / (x + i);
  return 0.5 * Math.log(2 * Math.PI) + (x + 0.5) * Math.log(t) - t + Math.log(a);
}

function betacf(a, b, x) {
  const FPMIN = 1e-300, EPS = 1e-16;
  const qab = a + b, qap = a + 1, qam = a - 1;
  let c = 1, d = 1 - qab * x / qap;
  if (Math.abs(d) < FPMIN) d = FPMIN;
  d = 1 / d;
  let h = d;
  for (let m = 1; m <= 1000; m++) {
    const m2 = 2 * m;
    let aa = m * (b - m) * x / ((qam + m2) * (a + m2));
    d = 1 + aa * d; if (Math.abs(d) < FPMIN) d = FPMIN;
    c = 1 + aa / c; if (Math.abs(c) < FPMIN) c = FPMIN;
    d = 1 / d; h *= d * c;
    aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2));
    d = 1 + aa * d; if (Math.abs(d) < FPMIN) d = FPMIN;
    c = 1 + aa / c; if (Math.abs(c) < FPMIN) c = FPMIN;
    d = 1 / d;
    const del = d * c;
    h *= del;
    if (Math.abs(del - 1) < EPS) break;
  }
  return h;
}

// função beta incompleta regularizada I_x(a, b)
export function betainc(a, b, x) {
  if (x <= 0) return 0;
  if (x >= 1) return 1;
  const lbt = lgamma(a + b) - lgamma(a) - lgamma(b) + a * Math.log(x) + b * Math.log1p(-x);
  const bt = Math.exp(lbt);
  if (x < (a + 1) / (a + b + 2)) return bt * betacf(a, b, x) / a;
  return 1 - bt * betacf(b, a, 1 - x) / b;
}

// p bicaudal da t de Student: 2 * sf(|t|, df)  (= 2*(1 - cdf(|t|)) sem perda de precisão nas caudas)
export function tP2(t, df) {
  if (Number.isNaN(t) || Number.isNaN(df)) return NaN;
  if (!Number.isFinite(t)) return 0;
  return betainc(df / 2, 0.5, df / (df + t * t));
}

// cdf da t de Student
export function tCdf(t, df) {
  const p2 = tP2(t, df);
  return t >= 0 ? 1 - p2 / 2 : p2 / 2;
}

// scipy.stats.spearmanr(x, y): { rho, p } (NaN se houver NaN ou entrada constante)
export function spearman(x, y) {
  const n = x.length;
  if (n <= 1 || !todosFinitos(x) || !todosFinitos(y)) return { rho: NaN, p: NaN };
  const rx = rankMedio(x), ry = rankMedio(y);
  const rs = pearson(rx, ry);
  if (Number.isNaN(rs)) return { rho: NaN, p: NaN };
  const dof = n - 2;
  const q = dof / ((rs + 1) * (1 - rs));
  const t = rs * Math.sqrt(Math.max(q, 0));   // +-Infinity quando |rs| = 1
  return { rho: rs, p: tP2(t, dof) };
}

// ------------------------------------------------------------------------------------------ pesos espaciais
// viz: array de arrays de índices vizinhos. Pesos linha-padronizados (libpysal transform="r"); ilhas ficam sem pesos.
export function criarPesos(viz) {
  const n = viz.length;
  const ptr = new Int32Array(n + 1);
  for (let i = 0; i < n; i++) ptr[i + 1] = ptr[i] + viz[i].length;
  const idx = new Int32Array(ptr[n]), w = new Float64Array(ptr[n]);
  let s0 = 0, ilhas = 0, maxCard = 0;
  for (let i = 0; i < n; i++) {
    const v = viz[i], c = v.length;
    if (c === 0) ilhas++;
    if (c > maxCard) maxCard = c;
    for (let k = 0; k < c; k++) { idx[ptr[i] + k] = v[k]; w[ptr[i] + k] = 1 / c; }
    if (c) s0 += 1;
  }
  return { n, ptr, idx, w, s0, ilhas, maxCard };
}

// out = W y
export function lag(W, y, out) {
  const { n, ptr, idx, w } = W;
  out = out || new Float64Array(n);
  for (let i = 0; i < n; i++) {
    let s = 0;
    for (let k = ptr[i]; k < ptr[i + 1]; k++) s += w[k] * y[idx[k]];
    out[i] = s;
  }
  return out;
}

// ------------------------------------------------------------------------------------------ Moran global (esda.Moran)
// p_sim: dobra a contagem para a menor cauda, como o esda: (min(larger, P - larger) + 1) / (P + 1).
export function moran(y, W, perm = 999, seed = 42) {
  const n = y.length, m = media(y);
  const z = new Float64Array(n);
  let z2 = 0;
  for (let i = 0; i < n; i++) { z[i] = y[i] - m; z2 += z[i] * z[i]; }
  const calc = (zz) => {
    const { ptr, idx, w } = W;
    let inum = 0;
    for (let i = 0; i < n; i++) {
      let s = 0;
      for (let k = ptr[i]; k < ptr[i + 1]; k++) s += w[k] * zz[idx[k]];
      inum += zz[i] * s;
    }
    return n / W.s0 * inum / z2;
  };
  const I = calc(z);
  const res = { I, p: NaN, z: NaN };
  if (perm) {
    const rng = mulberry32(seed), zp = Float64Array.from(z);
    let larger = 0, s1 = 0, s2 = 0;
    for (let k = 0; k < perm; k++) {
      embaralhar(zp, rng);
      const v = calc(zp);
      if (v >= I) larger++;
      s1 += v; s2 += v * v;
    }
    if (perm - larger < larger) larger = perm - larger;
    res.p = (larger + 1) / (perm + 1);
    const mu = s1 / perm, sd = Math.sqrt(Math.max(s2 / perm - mu * mu, 0));
    res.z = (I - mu) / sd;
  }
  return res;
}

// ------------------------------------------------------------------------------------------ LISA (esda.Moran_Local, alternative "directed")
// Permutação condicional (a vizinhança de i recebe valores sorteados dos demais municípios). Os sorteios são compartilhados
// entre os municípios, como no crand do esda. Devolve { Is, q (1..4), p }.
export function moranLocal(y, W, perm = 999, seed = 42) {
  const n = y.length, m = media(y), sy = desvio(y, 0);
  const z = new Float64Array(n);
  let den = 0;
  for (let i = 0; i < n; i++) { z[i] = (y[i] - m) / sy; den += z[i] * z[i]; }
  const zl = lag(W, z);
  const Is = new Float64Array(n), q = new Int8Array(n);
  const scal = (n - 1) / den;
  for (let i = 0; i < n; i++) {
    Is[i] = (n - 1) * z[i] * zl[i] / den;
    const zp = z[i] > 0, lp = zl[i] > 0;
    q[i] = zp ? (lp ? 1 : 4) : (lp ? 2 : 3);
  }
  const p = new Float64Array(n).fill(NaN);
  if (perm) {
    const { ptr, idx, w, maxCard } = W;
    const m1 = n - 1, ncols = Math.min(Math.max(maxCard, 1), m1);
    const ids = new Int32Array(m1);
    for (let i = 0; i < m1; i++) ids[i] = i;
    const rng = mulberry32(seed);
    const larger = new Int32Array(n);
    for (let k = 0; k < perm; k++) {
      // sorteia ncols ids distintos entre os n-1 "demais" (Fisher-Yates parcial; o vetor continua uma permutação)
      for (let c = 0; c < ncols; c++) {
        const j = c + ((rng() * (m1 - c)) | 0);
        const t = ids[c]; ids[c] = ids[j]; ids[j] = t;
      }
      for (let i = 0; i < n; i++) {
        let s = 0;
        for (let a = ptr[i], c = 0; a < ptr[i + 1]; a++, c++) {
          const id = ids[c];
          s += w[a] * z[id < i ? id : id + 1];
        }
        if (z[i] * s * scal >= Is[i]) larger[i]++;
      }
    }
    for (let i = 0; i < n; i++) {
      let l = larger[i];
      if (perm - l < l) l = perm - l;
      p[i] = (l + 1) / (perm + 1);
    }
  }
  return { Is, q, p };
}

// ------------------------------------------------------------------------------------------ Moran bivariado (esda.Moran_BV)
// x de cada unidade contra a média de y na vizinhança; permuta y globalmente. Devolve { I, p }.
export function moranBV(x, y, W, perm = 199, seed = 42) {
  const n = x.length;
  const mx = media(x), my = media(y), sx = desvio(x, 1), sy = desvio(y, 1);
  const zx = new Float64Array(n), zy = new Float64Array(n);
  for (let i = 0; i < n; i++) { zx[i] = (x[i] - mx) / sx; zy[i] = (y[i] - my) / sy; }
  const den = n - 1;
  const calc = (zz) => {
    const { ptr, idx, w } = W;
    let num = 0;
    for (let i = 0; i < n; i++) {
      let s = 0;
      for (let k = ptr[i]; k < ptr[i + 1]; k++) s += w[k] * zz[idx[k]];
      num += zx[i] * s;
    }
    return num / den;
  };
  const I = calc(zy);
  let p = NaN;
  if (perm) {
    const rng = mulberry32(seed), zp = Float64Array.from(zy);
    let larger = 0;
    for (let k = 0; k < perm; k++) { embaralhar(zp, rng); if (calc(zp) >= I) larger++; }
    if (perm - larger < larger) larger = perm - larger;
    p = (larger + 1) / (perm + 1);
  }
  return { I, p };
}

// ------------------------------------------------------------------------------------------ mínimos quadrados (QR de Householder)
// cols: array de k colunas (Float64Array de tamanho n); b: Float64Array(n). Devolve { beta, R (k x k, linha a linha), ok }.
// ok = false se alguma coluna for (quase) combinação linear das anteriores (matriz singular).
export function lstsqQR(cols, b) {
  const k = cols.length, n = b.length;
  const A = cols.map((c) => Float64Array.from(c));
  const y = Float64Array.from(b);
  const norma0 = A.map((c) => Math.sqrt(c.reduce((s, v) => s + v * v, 0)));
  const R = new Float64Array(k * k);
  let ok = true;
  for (let j = 0; j < k; j++) {
    const a = A[j];
    let nrm = 0;
    for (let i = j; i < n; i++) nrm += a[i] * a[i];
    nrm = Math.sqrt(nrm);
    if (!(nrm > 1e-10 * (norma0[j] || 1))) { ok = false; break; }
    const alpha = a[j] > 0 ? -nrm : nrm;
    const v = new Float64Array(n - j);
    for (let i = j; i < n; i++) v[i - j] = a[i];
    v[0] -= alpha;
    let vv = 0;
    for (let i = 0; i < v.length; i++) vv += v[i] * v[i];
    if (vv > 0) {
      for (let c = j; c < k; c++) {
        const col = A[c];
        let d = 0;
        for (let i = j; i < n; i++) d += v[i - j] * col[i];
        const f = 2 * d / vv;
        for (let i = j; i < n; i++) col[i] -= f * v[i - j];
      }
      let d = 0;
      for (let i = j; i < n; i++) d += v[i - j] * y[i];
      const f = 2 * d / vv;
      for (let i = j; i < n; i++) y[i] -= f * v[i - j];
    }
    for (let c = j; c < k; c++) R[j * k + c] = A[c][j];
  }
  if (!ok) return { beta: null, R, ok };
  const beta = new Float64Array(k);
  for (let j = k - 1; j >= 0; j--) {
    let s = y[j];
    for (let c = j + 1; c < k; c++) s -= R[j * k + c] * beta[c];
    beta[j] = s / R[j * k + j];
  }
  return { beta, R, ok };
}

// (R'R)^-1 = R^-1 R^-T, para a "ponte" do estimador sanduíche. R: k x k triangular superior.
export function inversaDeRtR(R, k) {
  const Ri = new Float64Array(k * k);
  for (let c = 0; c < k; c++) {
    for (let j = k - 1; j >= 0; j--) {
      let s = j === c ? 1 : 0;
      for (let m = j + 1; m < k; m++) s -= R[j * k + m] * Ri[m * k + c];
      Ri[j * k + c] = s / R[j * k + j];
    }
  }
  const out = new Float64Array(k * k);
  for (let i = 0; i < k; i++) for (let j = 0; j < k; j++) {
    let s = 0;
    for (let m = 0; m < k; m++) s += Ri[i * k + m] * Ri[j * k + m];
    out[i * k + j] = s;
  }
  return out;
}
