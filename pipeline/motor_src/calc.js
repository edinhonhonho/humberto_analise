// Motor de cálculo da análise eleitoral espacial (porte de run_analysis.py + eleicao/{tse_io,metrics,spatial,analises}.py).
// Entrada: o objeto de `UF.entrada()` (src/dados.js). Saída: o "ctx" (mesma forma que bundle.carregar() do Python, como JSON).
//
//   etapa1(entrada)        rápida, sem permutações: tabelas, cidades, gm (sem lisa_*), federação (parte barata).
//   etapa2(entrada, ctx1)  Moran global + LISA (gm.lisa_*), Moran de `comparacao`.
//   etapa3(entrada, ctx2)  análises completas: sobreposição (Moran bivariado), federação, modelo (WLS HC1), distância/bandas.
//   calcular(entrada, opcoes) = etapa1 + etapa2 + etapa3.
import { partidoDe, SIGLAS, partidosFederacao } from "./partidos.js";
import {
  criarPesos, lag, moran, moranLocal, moranBV, todosFinitos, todosIguais, media, desvio, pearson, spearman,
  lstsqQR, inversaDeRtR, tP2,
} from "./stats.js";

const N = (x) => (typeof x === "number" && Number.isFinite(x) ? x : null);
const CARGOS_PROPORCIONAIS = new Set([6, 7, 8, 9, 10, 11, 13]);
const CARGO_NOME = { 1: "Presidente", 3: "Governador", 5: "Senador", 6: "Deputado Federal", 7: "Deputado Estadual", 8: "Deputado Distrital" };
const LISA_LABELS = { hh: "Alto-Alto", ll: "Baixo-Baixo", out: "Outlier espacial", ns: "Não significativo" };

// ------------------------------------------------------------------------------------------ utilidades de texto
const titulo = (s) => s.toLowerCase().replace(/\p{L}[\p{L}\p{M}]*/gu, (w) => w[0].toUpperCase() + w.slice(1)); // str.title()
const normNome = (s) => String(s).normalize("NFKD").replace(/[^\x00-\x7F]/g, "").toUpperCase().replace(/[^A-Z0-9]/g, "");

function div(a, b) { return b > 0 ? a / b : NaN; }   // metrics._div

// rank method="min", decrescente; NaN -> NaN
function rankMinDesc(v) {
  const n = v.length, idx = [];
  for (let i = 0; i < n; i++) if (!Number.isNaN(v[i])) idx.push(i);
  idx.sort((a, b) => v[b] - v[a]);
  const r = new Float64Array(n).fill(NaN);
  for (let i = 0; i < idx.length; i++) r[idx[i]] = (i > 0 && v[idx[i]] === v[idx[i - 1]]) ? r[idx[i - 1]] : i + 1;
  return r;
}

function gini(x) {
  const a = Float64Array.from(x).sort();
  const n = a.length;
  let s = 0, ws = 0;
  for (let i = 0; i < n; i++) { s += a[i]; ws += (i + 1) * a[i]; }
  if (n === 0 || s === 0) return NaN;
  return (2 * ws) / (n * s) - (n + 1) / n;
}

// ------------------------------------------------------------------------------------------ base numérica (memoizada por entrada)
const _bases = new WeakMap();

function obterBase(e) {
  let b = _bases.get(e);
  if (!b) { b = montarBase(e); _bases.set(e, b); }
  return b;
}

function montarBase(e) {
  const { secoes: S, mc, votosCand: VC, malha } = e;
  const numero = Number(e.numero), cargo = e.cargo;
  const prop = CARGOS_PROPORCIONAIS.has(cargo);
  const partido = partidoDe(numero);

  // ---- seções: votos do candidato por seção
  const nS = S.n;
  const chave = (m, z, s) => (m * 1024 + z) * 16384 + s;
  const secIdx = new Map();
  for (let i = 0; i < nS; i++) secIdx.set(chave(S.mun[i], S.zona[i], S.secao[i]), i);
  const vCandSec = new Float64Array(nS);
  for (let i = 0; i < VC.n; i++) {
    const k = secIdx.get(chave(VC.mun[i], VC.zona[i], VC.secao[i]));
    if (k !== undefined) vCandSec[k] += VC.votos[i];
  }

  // ---- candidatos (sem branco/nulo; em proporcionais sem legenda) por município
  const mis = new Map(); // código TSE do município -> mi (índice local)
  const migCod = [];
  const mcN = mc.n;
  const cvot = new Int32Array(mcN), cmi = new Int32Array(mcN), cv = new Float64Array(mcN);
  let nc = 0;
  const partidoVotos = new Map(); // município -> votos válidos do partido do candidato (candidatos + legenda)
  for (let i = 0; i < mcN; i++) {
    const v = mc.votavel[i], mun = mc.mun[i], votos = mc.votos[i];
    if (partidoDe(v) === partido) partidoVotos.set(mun, (partidoVotos.get(mun) || 0) + votos);
    if (prop && v <= 99) continue;
    let mi = mis.get(mun);
    if (mi === undefined) { mi = migCod.length; mis.set(mun, mi); migCod.push(mun); }
    cvot[nc] = v; cmi[nc] = mi; cv[nc] = votos; nc++;
  }

  // ---- tabela municipal (metrics.tabela_municipal), antes da ordenação
  const gAgg = new Map();
  const secGi0 = new Int32Array(nS); // índice provisório do município
  const cods = [];
  for (let i = 0; i < nS; i++) {
    const mun = S.mun[i];
    let a = gAgg.get(mun);
    if (!a) {
      a = { cod: mun, votos: 0, validos: 0, brancos: 0, nulos: 0, comp: 0, eleit: 0, secoes: 0, idx: cods.length };
      gAgg.set(mun, a); cods.push(mun);
    }
    secGi0[i] = a.idx;
    a.votos += vCandSec[i]; a.validos += S.validos[i]; a.brancos += S.brancos[i]; a.nulos += S.nulos[i];
    a.comp += S.total[i];
    if (S.aptos[i] > 0) a.eleit += S.aptos[i];   // 0 = desconhecido (NaN no Python; soma ignora NaN)
    a.secoes++;
  }
  const ordem = [...gAgg.values()].sort((x, y) => (x.cod - y.cod));         // ordem do groupby
  ordem.sort((x, y) => (y.votos - x.votos));                                  // sort_values("votos", desc), estável
  const nG = ordem.length;
  const gCod = new Int32Array(nG), gIdx = new Map();
  const col = () => new Float64Array(nG);
  const votos = col(), validos = col(), brancos = col(), nulos = col(), comp = col(), eleit = col(), secN = col(), votosPart = col();
  const remap = new Int32Array(cods.length);
  ordem.forEach((a, i) => {
    gCod[i] = a.cod; gIdx.set(a.cod, i); remap[a.idx] = i;
    votos[i] = a.votos; validos[i] = a.validos; brancos[i] = a.brancos; nulos[i] = a.nulos; comp[i] = a.comp;
    eleit[i] = a.eleit; secN[i] = a.secoes; votosPart[i] = partidoVotos.get(a.cod) || 0;
  });
  const secGi = new Int32Array(nS);
  for (let i = 0; i < nS; i++) secGi[i] = remap[secGi0[i]];
  const gNome = Array.from(gCod, (c) => e.munNomes?.[c] ?? e.munNomes?.[String(c)] ?? String(c));

  const totVotos = votos.reduce((s, v) => s + v, 0), totValidos = validos.reduce((s, v) => s + v, 0);
  const pctEstado = totValidos ? 100 * totVotos / totValidos : NaN;

  const gmN = malha.municipios.length;
  const gmGi = new Int32Array(gmN), gOfGm = new Int32Array(nG).fill(-1);
  malha.municipios.forEach((m, j) => { const gi = gIdx.has(m.cod) ? gIdx.get(m.cod) : -1; gmGi[j] = gi; if (gi >= 0) gOfGm[gi] = j; });
  const W = criarPesos(malha.municipios.map((m) => m.viz));

  // município (mi) -> g
  const miG = Int32Array.from(migCod, (c) => (gIdx.has(c) ? gIdx.get(c) : -1));

  return {
    numero, cargo, prop, partido, secGi, vCandSec, nS, cvot, cmi, cv, nc, migCod, miG, nMi: migCod.length,
    nG, gCod, gIdx, gNome, votos, validos, brancos, nulos, comp, eleit, secN, votosPart, totVotos, totValidos, pctEstado,
    gmN, gmGi, gOfGm, W,
    centroides: { cx: Float64Array.from(malha.municipios, (m) => m.cx), cy: Float64Array.from(malha.municipios, (m) => m.cy) },
    pctCache: new Map(), nomesCache: null,
  };
}

// nomes e siglas (metrics.nomes_siglas): só existe a lista de candidatos (nomes.json)
function nomesSiglas(e) {
  const nomes = e.nomes || {};
  const sig = { ...SIGLAS };
  const vistos = new Set();
  for (const k of Object.keys(nomes)) {
    const s = nomes[k]?.[1];
    if (typeof s === "string" && s && s !== "nan") {
      const p = partidoDe(Number(k));
      if (!vistos.has(p)) { vistos.add(p); sig[p] = s; }
    }
  }
  const nome = (n) => { const x = nomes[n]?.[0]; return x && x !== "nan" ? x : String(n); };
  const sit = (n) => nomes[n]?.[2] ?? "";
  const sigla = (n) => { const p = partidoDe(n); return sig[p] ?? `Partido ${p}`; };
  return { nome, sit, sigla, sig };
}

// votos de um candidato (ou conjunto) por município de g
function vetorVotos(b, filtro) {
  const out = new Float64Array(b.nG);
  for (let i = 0; i < b.nc; i++) {
    const gi = b.miG[b.cmi[i]];
    if (gi >= 0 && filtro(b.cvot[i])) out[gi] += b.cv[i];
  }
  return out;
}
function vetorCand(b, num) {
  let v = b.pctCache.get(num);
  if (!v) { v = vetorVotos(b, (x) => x === num); b.pctCache.set(num, v); }
  return v;
}
function pctDe(v, validos) {   // analises._pct
  const o = new Float64Array(v.length);
  for (let i = 0; i < v.length; i++) o[i] = validos[i] > 0 ? 100 * v[i] / validos[i] : 0;
  return o;
}
// leva um vetor alinhado a g para a ordem de gm (sem dado = 0)
function alinhar(b, v) {
  const o = new Float64Array(b.gmN);
  for (let j = 0; j < b.gmN; j++) { const gi = b.gmGi[j]; o[j] = gi >= 0 ? v[gi] : 0; }
  return o;
}

// ================================================================================================ ETAPA 1
export function etapa1(e, opcoes = {}) {
  const topCidades = opcoes.topCidades ?? 3;
  const b = obterBase(e);
  const { numero, partido, nG } = b;
  const ns = nomesSiglas(e);

  // ---------------------------------------------------------------- tabela municipal
  const pctVal = new Float64Array(nG), v100 = new Float64Array(nG), share = new Float64Array(nG), ql = new Float64Array(nG);
  const abst = new Float64Array(nG), bn = new Float64Array(nG), pnp = new Float64Array(nG), ate = new Float64Array(nG);
  for (let i = 0; i < nG; i++) {
    pctVal[i] = 100 * div(b.votos[i], b.validos[i]);
    v100[i] = 100 * div(b.votos[i], b.eleit[i]);
    share[i] = 100 * div(b.votos[i], b.totVotos);
    ql[i] = div(pctVal[i], b.pctEstado);
    const a = 100 * (1 - div(b.comp[i], b.eleit[i]));
    abst[i] = Number.isNaN(a) ? NaN : Math.min(100, Math.max(0, a));
    bn[i] = 100 * div(b.brancos[i] + b.nulos[i], b.comp[i]);
    pnp[i] = 100 * div(b.votos[i], b.votosPart[i]);
    const x = b.pctEstado / 100 * b.validos[i] - b.votos[i];
    ate[i] = Number.isNaN(x) ? NaN : Math.max(0, x);
  }
  const rankVotos = rankMinDesc(b.votos), rankPct = rankMinDesc(pctVal);

  // ---------------------------------------------------------------- candidatos: totais, líderes, colegas
  const tot = new Map(); // número -> votos
  for (let i = 0; i < b.nc; i++) tot.set(b.cvot[i], (tot.get(b.cvot[i]) || 0) + b.cv[i]);
  if (!tot.has(numero) || !(tot.get(numero) > 0)) throw new Error(`Candidato ${numero} sem votos no arquivo.`);
  const votosTotal = tot.get(numero);

  const nMi = b.nMi;
  const lidV = new Float64Array(nMi).fill(-1), lidN = new Int32Array(nMi).fill(-1);
  const colV = new Float64Array(nMi).fill(-1), colN = new Int32Array(nMi).fill(-1);
  const meu = new Float64Array(nMi).fill(NaN);
  for (let i = 0; i < b.nc; i++) {
    const mi = b.cmi[i], v = b.cv[i], n = b.cvot[i];
    if (v > lidV[mi] || (v === lidV[mi] && n < lidN[mi])) { lidV[mi] = v; lidN[mi] = n; }
    if (n === numero) meu[mi] = v;
    else if (partidoDe(n) === partido && (v > colV[mi] || (v === colV[mi] && n < colN[mi]))) { colV[mi] = v; colN[mi] = n; }
  }
  const maiores = new Float64Array(nMi);
  for (let i = 0; i < b.nc; i++) { const mi = b.cmi[i]; if (b.cv[i] > meu[mi]) maiores[mi]++; }

  const nomeCand = ns.nome(numero);
  const municipal = new Array(nG);
  // g -> mi
  const giMi = new Int32Array(nG).fill(-1);
  for (let mi = 0; mi < nMi; mi++) if (b.miG[mi] >= 0) giMi[b.miG[mi]] = mi;
  for (let i = 0; i < nG; i++) {
    const mi = giMi[i];
    const tem = mi >= 0;
    const posic = tem && !Number.isNaN(meu[mi]) ? 1 + maiores[mi] : null;
    municipal[i] = {
      CD_MUNICIPIO: b.gCod[i], NM_MUNICIPIO: b.gNome[i], votos: b.votos[i], votos_partido: b.votosPart[i],
      validos: b.validos[i], brancos: b.brancos[i], nulos: b.nulos[i], comparecimento: b.comp[i],
      eleitores: b.eleit[i], secoes: b.secN[i], pct_validos: N(pctVal[i]), votos_por_100_aptos: N(v100[i]),
      share_votos_estado: N(share[i]), quociente_locacional: N(ql[i]), abstencao_pct: N(abst[i]),
      brancos_nulos_pct: N(bn[i]), pct_no_partido: N(pnp[i]), votos_ate_media_estadual: N(ate[i]),
      rank_votos: rankVotos[i], rank_pct: N(rankPct[i]),
      lider_nome: tem ? ns.nome(lidN[mi]) : null, lider_votos: tem ? lidV[mi] : null,
      posicao_no_municipio: posic,
      colega_nome: tem && colN[mi] >= 0 ? ns.nome(colN[mi]) : null, colega_votos: tem && colN[mi] >= 0 ? colV[mi] : null,
      lider_e_o_candidato: tem ? ns.nome(lidN[mi]) === nomeCand : null,
    };
  }

  // ---------------------------------------------------------------- concentração
  const vs = Float64Array.from(b.votos).sort().reverse();
  const tv = vs.reduce((s, v) => s + v, 0);
  const cum = new Float64Array(vs.length);
  let acc = 0, n50 = 1, n80 = 1, hh = 0, t5 = 0, t10 = 0, nvoto = 0;
  const pareto = new Array(vs.length);
  for (let i = 0; i < vs.length; i++) {
    acc += vs[i]; cum[i] = acc / tv;
    const sh = vs[i] / tv;
    hh += sh * sh;
    if (i < 5) t5 += sh;
    if (i < 10) t10 += sh;
    if (cum[i] < 0.5) n50++;
    if (cum[i] < 0.8) n80++;
    if (vs[i] > 0) nvoto++;
    pareto[i] = { n_municipios: i + 1, cum_share: N(100 * cum[i]) };
  }
  const conc = {
    n_municipios: vs.length, n_com_voto: nvoto, n_para_50: n50, n_para_80: n80, top1_share: N(100 * vs[0] / tv),
    top5_share: N(100 * t5), top10_share: N(100 * t10), gini: N(gini(vs)), hhi: N(hh * 10000), n_efetivo_municipios: N(1 / hh),
  };

  // ---------------------------------------------------------------- colegas (metrics.contexto_partido)
  const lista = [...tot.entries()].sort((x, y) => x[0] - y[0]);
  const todosVotos = lista.map((x) => x[1]);
  const doPartido = lista.filter(([n]) => partidoDe(n) === partido);
  const votosPartidoCands = doPartido.map((x) => x[1]);
  const somaCol = votosPartidoCands.reduce((s, v) => s + v, 0);
  const colegasRaw = doPartido.map(([n, v]) => {
    let re = 1, rp = 1;
    for (const w of todosVotos) if (w > v) re++;
    for (const w of votosPartidoCands) if (w > v) rp++;
    return { numero: n, nome: ns.nome(n), votos: v, partido_num: partido, rank_estado: re, rank_no_partido: rp, share_partido: N(100 * v / somaCol) };
  });
  const colegas = colegasRaw.sort((x, y) => y.votos - x.votos);

  // ---------------------------------------------------------------- comparação entre partidos (sem Moran)
  const tops = new Map(); // partido -> número do mais votado (empate: menor número)
  for (const [n, v] of lista) {
    const p = partidoDe(n);
    const t = tops.get(p);
    if (t === undefined || v > tot.get(t)) tops.set(p, n);
  }
  const topSet = new Set(tops.values());
  const sel = new Set([...topSet, numero]);
  const pv = new Map();
  for (const n of sel) pv.set(n, new Float64Array(nG));
  const t3 = new Float64Array(nMi * 3); // três maiores votos por município (para posição <= 3)
  for (let i = 0; i < b.nc; i++) {
    const mi = b.cmi[i], v = b.cv[i], a = pv.get(b.cvot[i]);
    if (a) { const gi = b.miG[mi]; if (gi >= 0) a[gi] += v; }
    const o = mi * 3;
    if (v > t3[o]) { t3[o + 2] = t3[o + 1]; t3[o + 1] = t3[o]; t3[o] = v; }
    else if (v > t3[o + 1]) { t3[o + 2] = t3[o + 1]; t3[o + 1] = v; }
    else if (v > t3[o + 2]) t3[o + 2] = v;
  }
  const top3 = new Map();
  for (let i = 0; i < b.nc; i++) {
    const n = b.cvot[i], v = b.cv[i];
    if (sel.has(n) && v > 0 && v >= t3[b.cmi[i] * 3 + 2]) top3.set(n, (top3.get(n) || 0) + 1);
  }
  const comparacao = [];
  for (const [n, vtot] of lista) {
    if (!sel.has(n)) continue;
    const v = pv.get(n);
    let sv = 0;
    for (let i = 0; i < nG; i++) sv += v[i];
    let n0 = 0, n05 = 0, n1 = 0, n5 = 0, mx = 0, hs = 0;
    for (let i = 0; i < nG; i++) {
      const p = b.validos[i] > 0 ? 100 * v[i] / b.validos[i] : 0;
      if (v[i] > 0) n0++;
      if (p >= 0.5) n05++;
      if (p >= 1) n1++;
      if (p >= 5) n5++;
      if (sv) { const s = v[i] / sv; if (s > mx) mx = s; hs += s * s; }
    }
    comparacao.push({
      numero: n, nome: ns.nome(n), sigla: ns.sigla(n), situacao: ns.sit(n), votos: vtot,
      pct_estado: N(b.totValidos ? 100 * vtot / b.totValidos : NaN), n_mun_voto: n0, n_mun_05pct: n05, n_mun_1pct: n1, n_mun_5pct: n5,
      n_top3: top3.get(n) || 0, top1_share: sv ? N(100 * mx) : null, gini: N(gini(v)), n_efetivo: sv ? N(1 / hs) : null,
      foco: n === numero, top_do_partido: topSet.has(n), n_municipios: nG,
    });
  }
  comparacao.sort((x, y) => y.votos - x.votos);

  // ---------------------------------------------------------------- top 5 por município
  const topK = 5;
  const tmV = new Float64Array(nMi * topK), tmN = new Int32Array(nMi * topK).fill(-1);
  for (let i = 0; i < b.nc; i++) {
    const v = b.cv[i];
    if (!(v > 0)) continue;
    const mi = b.cmi[i], n = b.cvot[i], o = mi * topK;
    let k = topK;
    // posição de inserção: ordem (votos desc, número asc)
    while (k > 0 && (tmN[o + k - 1] < 0 || v > tmV[o + k - 1] || (v === tmV[o + k - 1] && n < tmN[o + k - 1]))) k--;
    if (k >= topK) continue;
    for (let c = topK - 1; c > k; c--) { tmV[o + c] = tmV[o + c - 1]; tmN[o + c] = tmN[o + c - 1]; }
    tmV[o + k] = v; tmN[o + k] = n;
  }
  const mOrd = Array.from({ length: nMi }, (_, i) => i).sort((x, y) => b.migCod[x] - b.migCod[y]);
  const top_mun = [];
  for (const mi of mOrd) {
    const gi = b.miG[mi], val = gi >= 0 ? b.validos[gi] : 0;
    for (let k = 0; k < topK; k++) {
      const n = tmN[mi * topK + k];
      if (n < 0) break;
      top_mun.push({
        CD_MUNICIPIO: b.migCod[mi], posicao: k + 1, numero: n, nome: ns.nome(n), sigla: ns.sigla(n),
        votos: tmV[mi * topK + k], pct: val > 0 ? N(100 * tmV[mi * topK + k] / val) : null,
      });
    }
  }

  // ---------------------------------------------------------------- cidades (análise intraurbana, sem locais/coordenadas)
  const cidades = [];
  for (let r = 0; r < Math.min(topCidades, nG); r++) cidades.push(cidade(e, b, r, municipal[r]));

  // ---------------------------------------------------------------- gm (ordem da malha), sem lisa_*
  const gm = e.malha.municipios.map((m, j) => {
    const gi = b.gmGi[j];
    const r = gi >= 0 ? municipal[gi] : null;
    return {
      CD_MUNICIPIO: m.cod, NM_MUNICIPIO: r ? r.NM_MUNICIPIO : String(m.nome).toUpperCase(),
      votos: r ? r.votos : 0, validos: r ? r.validos : 0, eleitores: r ? r.eleitores : 0,
      pct_validos: r ? r.pct_validos : null, votos_por_100_aptos: r ? r.votos_por_100_aptos : null,
      quociente_locacional: r ? r.quociente_locacional : null, share_votos_estado: r ? r.share_votos_estado : null,
      abstencao_pct: r ? r.abstencao_pct : null, brancos_nulos_pct: r ? r.brancos_nulos_pct : null,
      posicao_no_municipio: r ? r.posicao_no_municipio : null, lider_nome: r ? r.lider_nome : null,
      colega_nome: r ? r.colega_nome : null, votos_ate_media_estadual: r ? r.votos_ate_media_estadual : null,
      rank_votos: r ? r.rank_votos : null,
    };
  });

  // ---------------------------------------------------------------- federação (parte barata de analises)
  const partidos = partidosFederacao(numero, opcoes.federacao);
  const { mun: fedMun, meta: fedMeta } = federacao(b, partidos);
  fedMeta.nome = partidos.map((p) => SIGLAS[p] ?? String(p)).join("/");

  const info = {
    numero, nome: nomeCand, partido_num: partido, cargo: e.cargo, turno: e.turno, uf: e.uf,
    linhas_lidas: null, votos_total: votosTotal,
  };
  return {
    info, ano: e.ano, uf: e.uf, cargo: e.cargo, cargo_nome: CARGO_NOME[e.cargo] ?? `Cargo ${e.cargo}`,
    conc, moran: null, pct_estado: N(b.pctEstado), cob_coord: 0, despesas: null, criterio_cidades: "top",
    analises_meta: { federacao: fedMeta }, municipal, pareto, colegas, comparacao, top_mun, regioes: null, gm, cidades,
    analises: { mun: fedMun, sobreposicao: [], modelo: null, bandas: [], meta: { federacao: fedMeta } },
  };
}

// ---------------------------------------------------------------- uma cidade (spatial.agregar_locais/zonas/bairros)
function cidade(e, b, gi, r) {
  const S = e.secoes;
  const nm = titulo(r.NM_MUNICIPIO);
  const locais = new Map(), zonas = new Map();
  const bairro = { locais: new Set(), secoes: 0, votos: 0, validos: 0, eleit: 0 };
  for (let i = 0; i < b.nS; i++) {
    if (b.secGi[i] !== gi) continue;
    const z = S.zona[i], l = S.loc[i], v = b.vCandSec[i], val = S.validos[i], el = S.aptos[i] > 0 ? S.aptos[i] : 0;
    const kl = z * 1e6 + l;
    let a = locais.get(kl);
    if (!a) { a = { z, l, secoes: 0, votos: 0, validos: 0, eleit: 0, comp: 0 }; locais.set(kl, a); }
    a.secoes++; a.votos += v; a.validos += val; a.eleit += el; a.comp += S.total[i];
    let zz = zonas.get(z);
    if (!zz) { zz = { z, locais: new Set(), secoes: 0, votos: 0, validos: 0, eleit: 0 }; zonas.set(z, zz); }
    zz.locais.add(l); zz.secoes++; zz.votos += v; zz.validos += val; zz.eleit += el;
    bairro.locais.add(l); bairro.secoes++; bairro.votos += v; bairro.validos += val; bairro.eleit += el;
  }
  const pct = (v, val) => (val > 0 ? N(100 * v / val) : null);
  const lista = [...locais.values()].sort((x, y) => (x.z - y.z) || (x.l - y.l)).sort((x, y) => y.votos - x.votos);
  const locaisOut = lista.map((a) => ({
    NR_ZONA: a.z, NR_LOCAL_VOTACAO: a.l, local_nome: `Local ${a.l}`, bairro: "(sem bairro)", endereco: null, lat: null, lon: null,
    secoes: a.secoes, votos: a.votos, validos: a.validos, eleitores: a.eleit, comparecimento: a.comp,
    pct_validos: pct(a.votos, a.validos), votos_por_100_aptos: a.eleit > 0 ? N(100 * a.votos / a.eleit) : null,
  }));
  const agreg = (a, extra) => ({
    ...extra, locais: a.locais.size, secoes: a.secoes, votos: a.votos, validos: a.validos, eleitores: a.eleit,
    pct_validos: pct(a.votos, a.validos), votos_por_100_aptos: a.eleit > 0 ? N(100 * a.votos / a.eleit) : null,
  });
  const totV = [...zonas.values()].reduce((s, z) => s + z.votos, 0);
  const zonasOut = [...zonas.values()].sort((x, y) => x.z - y.z).sort((x, y) => y.votos - x.votos).map((a) => {
    const o = agreg(a, { NR_ZONA: a.z });
    o.share_votos_cidade = totV > 0 ? N(100 * a.votos / totV) : null;
    return o;
  });
  const bairrosOut = bairro.secoes ? [(() => {
    const o = agreg(bairro, { bairro: "(sem bairro)" });
    o.share_votos_cidade = bairro.votos > 0 ? 100 : null;
    return o;
  })()] : [];
  return {
    nome: nm, slug: normNome(nm).toLowerCase(), votos: r.votos, pct: r.pct_validos, validos: r.validos, eleitores: r.eleitores,
    n_locais: locaisOut.length, n_coord: 0, n_fora: 0, res: null, area_km2: null, com_hex: false,
    locais: locaisOut, bairros: bairrosOut, zonas: zonasOut,
  };
}

// ---------------------------------------------------------------- federação (analises.federacao)
function vetorFed(b, partidos) {
  const set = new Set(partidos);
  return vetorVotos(b, (n) => set.has(partidoDe(n)));
}

function federacao(b, partidos) {
  const nG = b.nG, validos = b.validos, h = b.votos;
  const fed = vetorFed(b, partidos);
  let H = 0, F = 0, vsum = 0, igual = true;
  for (let i = 0; i < nG; i++) {
    if (fed[i] < h[i]) fed[i] = h[i];
    H += h[i]; F += fed[i]; vsum += validos[i];
    if (!(Math.abs(fed[i] - h[i]) <= 1e-8 + 1e-5 * Math.abs(h[i]))) igual = false;
  }
  const s = F ? H / F : NaN;
  const mun = new Array(nG);
  let nAcima = 0, nAbaixo = 0, aMais = 0;
  const esperado = new Float64Array(nG);
  for (let i = 0; i < nG; i++) {
    const esp = fed[i] * s; esperado[i] = esp;
    mun[i] = {
      CD_MUNICIPIO: b.gCod[i], fed_votos: fed[i], fed_pct: N(validos[i] > 0 ? 100 * fed[i] / validos[i] : 0),
      fed_outros_pct: N(validos[i] > 0 ? 100 * (fed[i] - h[i]) / validos[i] : 0),
      part_fed: fed[i] > 0 ? N(100 * h[i] / fed[i]) : null, esperado_fed: N(esp), dif_fed: N(esp - h[i]),
    };
    if (h[i] > esp + 0.5) nAcima++;
    if (h[i] < esp - 0.5 && esp >= 1) nAbaixo++;
    aMais += Math.max(esp - h[i], 0);
  }
  const meta = {
    fed_partidos: [...partidos], fed_votos: F, fed_pct_estado: N(100 * F / vsum), part_fed_estado: N(100 * s),
    n_acima: nAcima, n_abaixo: nAbaixo, votos_a_mais: N(aMais), sem_colegas: igual,
  };
  return { mun, meta, fed };
}

// ================================================================================================ ETAPA 2
export function etapa2(e, ctx1, opcoes = {}) {
  const perm = opcoes.permutacoes ?? 999, permComp = opcoes.permComp ?? 199, seed = opcoes.seed ?? 42;
  const b = obterBase(e);
  const { W, gmN } = b;
  const ctx = { ...ctx1 };

  // ---- LISA municipal de pct_validos (spatial.lisa_municipal)
  const y = new Float64Array(gmN);
  ctx1.gm.forEach((r, j) => { y[j] = r.pct_validos ?? 0; });
  const gm = ctx1.gm.map((r) => ({ ...r }));
  if (todosIguais(y)) {
    gm.forEach((r) => { r.lisa_cluster = LISA_LABELS.ns; r.lisa_detalhe = ""; r.lisa_p = null; r.lisa_I = null; });
    ctx.moran = { I: null, p: null };
  } else {
    const mo = moran(y, W, perm, seed);
    const lo = moranLocal(y, W, perm, seed);
    let nhh = 0, nll = 0, nout = 0;
    for (let j = 0; j < gmN; j++) {
      const sig = lo.p[j] < 0.05, q = lo.q[j], r = gm[j];
      let cl = LISA_LABELS.ns, det = "";
      if (sig) {
        if (q === 1) { cl = LISA_LABELS.hh; det = "Forte e cercado de vizinhos fortes"; nhh++; }
        else if (q === 3) { cl = LISA_LABELS.ll; det = "Fraco e cercado de vizinhos fracos"; nll++; }
        else { cl = LISA_LABELS.out; nout++; det = q === 4 ? "Forte em meio a vizinhos fracos" : "Fraco em meio a vizinhos fortes"; }
      }
      r.lisa_cluster = cl; r.lisa_detalhe = det; r.lisa_p = N(lo.p[j]); r.lisa_I = N(lo.Is[j]);
    }
    ctx.moran = { I: N(mo.I), p: N(mo.p), z: N(mo.z), n_hh: nhh, n_ll: nll, n_out: nout };
  }
  ctx.gm = gm;

  // ---- Moran de cada candidato da comparação (spatial.moran_varios)
  ctx.comparacao = ctx1.comparacao.map((r) => {
    const v = alinhar(b, pctDe(vetorCand(b, r.numero), b.validos));
    let I = null, p = null;
    if (todosFinitos(v) && !todosIguais(v)) { const m = moran(v, W, permComp, seed); I = N(m.I); p = N(m.p); }
    return { ...r, moran_I: I, moran_p: p };
  });
  return ctx;
}

// ================================================================================================ ETAPA 3
export function etapa3(e, ctx2, opcoes = {}) {
  const permComp = opcoes.permComp ?? 199, seed = opcoes.seed ?? 42;
  const b = obterBase(e);
  const numero = b.numero;
  const partidos = ctx2.analises_meta.federacao.fed_partidos;
  const { mun: fedMun, meta: fedMeta, fed } = federacao(b, partidos);
  fedMeta.nome = ctx2.analises_meta.federacao.nome;

  const sobre = sobreposicao(b, ctx2.comparacao, partidos, fed, permComp, seed);
  let coef = null, modMeta = {}, modMun = null;
  if (fedMeta.sem_colegas) { modMeta = {}; }
  else {
    try {
      const m = modelo(b, fed, permComp, seed);
      coef = m.coef; modMun = m.mun; modMeta = m.meta;
    } catch (err) {
      if (err && err.name === "LinAlgError") { fedMeta.sem_colegas = true; coef = null; modMeta = {}; modMun = null; }
      else throw err;
    }
  }
  const dist = distancia(b);
  const mun = fedMun.map((r, i) => {
    const o = { ...r };
    if (modMun) Object.assign(o, modMun[i]);
    Object.assign(o, dist.mun[i]);
    return o;
  });
  const meta = { federacao: fedMeta, modelo: modMeta, distancia: dist.meta };
  const ctx = { ...ctx2 };
  ctx.analises = { mun, sobreposicao: sobre, modelo: coef, bandas: dist.bandas, meta };
  ctx.analises_meta = { ...meta };
  return ctx;
}

// ---------------------------------------------------------------- sobreposição geográfica (analises.sobreposicao)
function sobreposicao(b, comp, partidos, fedVec, perm, seed) {
  const nG = b.nG, validos = b.validos, h = b.votos;
  const hPct = pctDe(h, validos);
  let hSum = 0;
  for (let i = 0; i < nG; i++) hSum += h[i];
  const hSh = Float64Array.from(h, (x) => x / hSum);
  const alvos = [];
  for (const r of comp) {
    if (r.foco || !r.top_do_partido || !(r.votos >= 1000)) continue;
    alvos.push({ nome: r.nome, sigla: r.sigla, v: vetorCand(b, r.numero), mesma: partidos.includes(partidoDe(r.numero)), tot: r.votos });
  }
  const set = new Set(partidos);
  const fedAll = vetorVotos(b, (n) => set.has(partidoDe(n)));
  const resto = new Float64Array(nG);
  let rs = 0;
  for (let i = 0; i < nG; i++) { resto[i] = Math.max(fedAll[i] - h[i], 0); rs += resto[i]; }
  if (rs > 0) {
    alvos.push({
      nome: partidos.length > 1 ? "Resto da federação" : "Resto do partido",
      sigla: partidos.map((p) => SIGLAS[p] ?? String(p)).join("/"), v: resto, mesma: true, tot: rs,
    });
  }
  const x = alinhar(b, hPct);
  const sx = desvio(x, 0);
  const linhas = alvos.map((a) => {
    const p = pctDe(a.v, validos);
    const yv = alinhar(b, p);
    let I = NaN, pv = NaN;
    if (!(sx === 0 || desvio(yv, 0) === 0)) { const m = moranBV(x, yv, b.W, perm, seed); I = m.I; pv = m.p; }
    let sv = 0;
    for (let i = 0; i < nG; i++) sv += a.v[i];
    let ov = 0;
    for (let i = 0; i < nG; i++) ov += Math.min(hSh[i], sv ? a.v[i] / sv : a.v[i]);
    const r = desvio(p, 0) > 0 && desvio(hPct, 0) > 0 ? pearson(hPct, p) : NaN;
    return {
      nome: a.nome, sigla: a.sigla, votos: a.tot, mesma_federacao: !!a.mesma, correlacao: N(r),
      sobreposicao: N(100 * ov), moran_bv: N(I), moran_bv_p: N(pv),
    };
  });
  return linhas.sort((p, q) => q.sobreposicao - p.sobreposicao);
}

// ---------------------------------------------------------------- modelo WLS (analises.modelo)
function erroLinAlg(msg) { const er = new Error(msg); er.name = "LinAlgError"; return er; }

function modelo(b, fedVec, perm, seed) {
  const nG = b.nG, W = b.W, validos = b.validos;
  const h = b.votos;
  const fedOutros = new Float64Array(nG);
  for (let i = 0; i < nG; i++) fedOutros[i] = validos[i] > 0 ? 100 * (fedVec[i] - h[i]) / validos[i] : 0;
  const lagGm = lag(W, alinhar(b, fedOutros));
  const fedViz = new Float64Array(nG);
  for (let i = 0; i < nG; i++) { const j = b.gOfGm[i]; fedViz[i] = j >= 0 ? lagGm[j] : 0; }
  const lnEl = Float64Array.from(b.eleit, (x) => Math.log(Math.max(x, 1)));
  // abstenção: NaN -> mediana (pandas, ignora NaN)
  const abstRaw = Float64Array.from(b.comp, (c, i) => {
    const q = div(c, b.eleit[i]);
    const a = 100 * (1 - q);
    return Number.isNaN(a) ? NaN : Math.min(100, Math.max(0, a));
  });
  const ok = Array.from(abstRaw).filter((x) => !Number.isNaN(x)).sort((p, q) => p - q);
  const med = ok.length ? (ok.length % 2 ? ok[(ok.length - 1) / 2] : (ok[ok.length / 2 - 1] + ok[ok.length / 2]) / 2) : NaN;
  const abst = abstRaw.map((x) => (Number.isNaN(x) ? med : x));
  const cand = [["ln_eleitores", lnEl], ["abstencao_pct", abst], ["fed_outros_pct", fedOutros], ["fed_viz_pct", fedViz]];
  const usadas = cand.filter(([, v]) => desvio(v, 0) > 1e-9);   // NaN > 1e-9 é falso: descarta
  const rot = {
    const: "Constante", ln_eleitores: "Tamanho do eleitorado (logaritmo)", abstencao_pct: "Abstenção (%)",
    fed_outros_pct: "Votos do resto da federação no município (%)", fed_viz_pct: "Votos do resto da federação nos vizinhos (%)",
  };
  const y = Float64Array.from({ length: nG }, (_, i) => 100 * div(h[i], validos[i]));
  if (!todosFinitos(y)) throw erroLinAlg("pct_validos com NaN");
  const wt = Float64Array.from(validos, (v) => Math.max(v, 1));
  const sw = wt.map(Math.sqrt);
  const cols = [new Float64Array(nG).fill(1), ...usadas.map(([, v]) => v)];
  const k = cols.length, n = nG;
  const A = cols.map((c) => c.map((v, i) => v * sw[i]));
  const bw = y.map((v, i) => v * sw[i]);
  const qr = lstsqQR(A, bw);
  if (!qr.ok) throw erroLinAlg("matriz singular");
  const beta = qr.beta;
  const pred = new Float64Array(n), res = new Float64Array(n);
  let sres = 0, sw2 = 0, ybarN = 0;
  for (let i = 0; i < n; i++) {
    let p = 0;
    for (let c = 0; c < k; c++) p += cols[c][i] * beta[c];
    pred[i] = p; res[i] = y[i] - p;
    sres += wt[i] * res[i] * res[i]; sw2 += wt[i]; ybarN += wt[i] * y[i];
  }
  const s2 = sres / (n - k);
  const bread = inversaDeRtR(qr.R, k);
  // meat = sum (wt res)^2 x x'
  const meat = new Float64Array(k * k);
  for (let i = 0; i < n; i++) {
    const f = wt[i] * res[i];
    for (let a = 0; a < k; a++) for (let c = 0; c < k; c++) meat[a * k + c] += f * f * cols[a][i] * cols[c][i];
  }
  const mm = (X, Y) => { const o = new Float64Array(k * k); for (let a = 0; a < k; a++) for (let c = 0; c < k; c++) { let s = 0; for (let d = 0; d < k; d++) s += X[a * k + d] * Y[d * k + c]; o[a * k + c] = s; } return o; };
  const sand = mm(mm(bread, meat), bread);
  const se = new Float64Array(k), seCl = new Float64Array(k), t = new Float64Array(k), pv = new Float64Array(k);
  for (let c = 0; c < k; c++) {
    se[c] = Math.sqrt(sand[c * k + c] * n / (n - k));
    seCl[c] = Math.sqrt(s2 * bread[c * k + c]);
    t[c] = beta[c] / se[c];
    pv[c] = tP2(Math.abs(t[c]), n - k);
  }
  const ybar = ybarN / sw2;
  let sst = 0;
  for (let i = 0; i < n; i++) sst += wt[i] * (y[i] - ybar) * (y[i] - ybar);
  const r2 = 1 - sres / sst;
  // resíduo padronizado (variância multiplicativa, Harvey 1976): log(res^2 + 1e-10) ~ 1 + log(wt)
  const lw = wt.map(Math.log), lr = res.map((r) => Math.log(r * r + 1e-10));
  let fit;
  const qz = lstsqQR([new Float64Array(n).fill(1), lw], lr);
  if (qz.ok) { fit = lw.map((l) => qz.beta[0] + qz.beta[1] * l); }
  else { const m = media(lr); fit = new Float64Array(n).fill(m); }
  const z = Float64Array.from(res, (r, i) => r / Math.sqrt(Math.exp(fit[i] + 1.2704)));

  const nomes = ["const", ...usadas.map(([nm]) => nm)];
  const sds = [NaN, ...usadas.map(([, v]) => desvio(v, 1))];
  const coef = nomes.map((nm, c) => ({
    variavel: nm, rotulo: rot[nm], coef: N(beta[c]), erro_padrao: N(se[c]), erro_padrao_classico: N(seCl[c]),
    t: N(t[c]), p: N(pv[c]), efeito_1dp: N(beta[c] * sds[c]),
  }));
  const mun = new Array(n);
  let nAc = 0, nAb = 0;
  for (let i = 0; i < n; i++) {
    const esp = pred[i] / 100 * validos[i];
    mun[i] = { pct_previsto: N(pred[i]), residuo_pp: N(res[i]), z_residuo: N(z[i]), votos_esperados: N(esp), dif_modelo: N(h[i] - esp) };
    if (z[i] > 2) nAc++;
    if (z[i] < -2) nAb++;
  }
  const mo = moran(alinhar(b, z), W, perm, seed);
  return { coef, mun, meta: { r2: N(r2), n, moran_res: N(mo.I), moran_res_p: N(mo.p), n_acima: nAc, n_abaixo: nAb } };
}

// ---------------------------------------------------------------- distância dos redutos (analises.distancia)
const BANDAS_CORTES = [-0.001, 0.001, 50, 100, 150, 200, 300, 1e9];
const BANDAS_ROT = ["Reduto", "até 50 km", "50 a 100 km", "100 a 150 km", "150 a 200 km", "200 a 300 km", "mais de 300 km"];

function distancia(b, k = 5) {
  const di = [];   // municípios de g que existem na malha, na ordem de g
  for (let i = 0; i < b.nG; i++) if (b.gOfGm[i] >= 0) di.push(i);
  return distanciaCom(b, di, k);
}

function distanciaCom(b, di, k) {
  const { cx, cy } = b.centroides;
  const nd = di.length;
  const X = di.map((i) => cx[b.gOfGm[i]]), Y = di.map((i) => cy[b.gOfGm[i]]);
  const ordem = di.map((_, p) => p).sort((p, q) => b.votos[di[q]] - b.votos[di[p]]);
  const top = ordem.slice(0, k);
  const dmin = new Float64Array(nd), dprin = new Float64Array(nd), prox = new Array(nd);
  for (let p = 0; p < nd; p++) {
    let best = Infinity, bi = 0, first = 0;
    for (let t = 0; t < top.length; t++) {
      const q = top[t], dx = X[p] - X[q], dy = Y[p] - Y[q];
      const d = Math.sqrt(dx * dx + dy * dy) / 1000;
      if (t === 0) first = d;
      if (d < best) { best = d; bi = t; }
    }
    dmin[p] = best; dprin[p] = first; prox[p] = b.gNome[di[top[bi]]];
  }
  const mun = new Array(b.nG).fill(null).map(() => ({ dist_reduto_km: null, reduto_proximo: null, dist_principal_km: null }));
  di.forEach((i, p) => { mun[i] = { dist_reduto_km: N(dmin[p]), reduto_proximo: prox[p], dist_principal_km: N(dprin[p]) }; });

  const nb = BANDAS_ROT.length;
  const cnt = new Float64Array(nb), vt = new Float64Array(nb), vl = new Float64Array(nb);
  for (let p = 0; p < nd; p++) {
    const d = dmin[p];
    let f = -1;
    for (let c = 0; c < nb; c++) if (d > BANDAS_CORTES[c] && d <= BANDAS_CORTES[c + 1]) { f = c; break; }
    if (f < 0) continue;
    cnt[f]++; vt[f] += b.votos[di[p]]; vl[f] += b.validos[di[p]];
  }
  const totVt = vt.reduce((s, v) => s + v, 0);
  const bandas = BANDAS_ROT.map((faixa, c) => ({
    faixa, municipios: cnt[c], votos: vt[c], validos: vl[c], pct_validos: vl[c] > 0 ? N(100 * vt[c] / vl[c]) : null,
    share_votos: N(100 * vt[c] / totVt),
  }));
  const dx = [], pctv = [];
  for (let p = 0; p < nd; p++) if (dmin[p] > 0.001) { dx.push(dmin[p]); pctv.push(100 * div(b.votos[di[p]], b.validos[di[p]])); }
  const sp = spearman(Float64Array.from(dx), Float64Array.from(pctv));
  let tot = 0;
  for (let p = 0; p < nd; p++) tot += b.votos[di[p]];
  const ate = (km) => { let s = 0; for (let p = 0; p < nd; p++) if (dmin[p] <= km) s += b.votos[di[p]]; return N(100 * s / tot); };
  let mv = 0;
  for (let p = 0; p < nd; p++) if (dmin[p] <= 100 && b.votos[di[p]] > 0) mv++;
  const meta = {
    k, redutos: top.map((p) => b.gNome[di[p]]), spearman: N(sp.rho), spearman_p: N(sp.p),
    votos_ate_50: ate(50), votos_ate_100: ate(100), votos_ate_200: ate(200), mun_voto_ate_100: mv, n_mun: nd,
  };
  return { mun, bandas, meta };
}

// ================================================================================================ API
async function avisar(opcoes, nome, ctx) { if (opcoes && opcoes.onEtapa) await opcoes.onEtapa(nome, ctx); }

export async function calcular(entrada, opcoes = {}) {
  const c1 = etapa1(entrada, opcoes);
  await avisar(opcoes, "etapa1", c1);
  const c2 = etapa2(entrada, c1, opcoes);
  await avisar(opcoes, "etapa2", c2);
  const c3 = etapa3(entrada, c2, opcoes);
  await avisar(opcoes, "etapa3", c3);
  return c3;
}

export { partidoDe, SIGLAS };
