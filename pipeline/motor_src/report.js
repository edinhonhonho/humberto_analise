// Porte de eleicao/report.py (modo "blocos") + site.py (_compactar, formato P). Sem DOM, sem dependências.
//
//   montar(ctx, malha, opcoes) -> {titulo, corpo, blocos, geo, det, ano, uf, cargo_cod, numero, nome, cargo, turno, votos}
//   compactar(blocos, det)     -> blocos com as dicas dos mapas compactadas (site._compactar)
//   paginaP(pag, malha)        -> P = {t, h, b, d, gs, m} que o app.js consome em desenhar(P, P.gs)
//
// ctx: forma de fixtures/ctx/<nome>.json (linhas como objetos; gm na ordem de malha.municipios, sem geometria).
// malha: malha.json da UF ({vb, municipios:[{cod, d, ...}]}); a geometria vem de municipios[i].d.
// opcoes: {pendentes: Set|Array de ids de seção em cálculo, estrito: bool (lança em vez de degradar)}.
import { REFS, PARTES, NOTAS, GUIA } from "./conteudo.js";
import { esc, fnum, fmtF, pyRound, nomePt, numJ, nn, num, npSum, PF } from "./format.js";
import {
  classesQuantil, classesQl, classesCategoria, geoDefs, mapBloco, barChart, paretoChart,
} from "./svgviz.js";

export { fnum, fdyn, esc, nomePt } from "./format.js";

// Foice e martelo: ícone "hammer-sickle" do Material Design Icons (Pictogrammers), licença Apache 2.0
const HS_PATH = "M22 20.59L20.59 22l-3.14-3.14c-.56.37-1.15.7-1.79.92c-1.66.58-3.46.62-5.13.1c-1.03-.3-1.97-.83-2.78-1.51l-3.19 3.19c-.56.59-1.53.59-2.12 0c-.58-.56-.58-1.56 0-2.12l3.38-3.38l2.65-.52a6.1 6.1 0 0 0 2.81 1.96c1.16.35 2.44.34 3.59-.04c.29-.09.57-.2.83-.34L7.6 9l-1.77 1.78L3 7.95L7.95 3l4.24 1.41L9 7.6l8.31 8.29c.19-.18.34-.36.49-.56c1.5-1.97 1.62-4.91.29-7.33C16.78 5.57 14.5 3.55 12 2c1.41.5 2.76 1.17 4 2.04s2.43 1.89 3.33 3.21c.9 1.29 1.54 2.87 1.67 4.54c.1 1.68-.34 3.44-1.3 4.86c-.2.35-.46.63-.7.91z";
const HS_VIEWBOX = "0 0 24 24";
export const ICON = `<svg class="hs" viewBox="${HS_VIEWBOX}" fill="currentColor" aria-hidden="true"><path d="${HS_PATH}"/></svg>`;
export const NAV = '<nav class="top"><div class="in"><span class="brand"><i>' + ICON + '</i>Eleições</span>'
  + '<a href="#guia">Como ler</a></div>'
  + '<div class="sec" id="secbar" hidden><span class="n"></span><span class="t"></span></div></nav>';

// ------------------------------------------------------------------ utilidades de "dataframe"
const arr = (x) => (Array.isArray(x) ? x : []);
const head = (rows, n) => rows.slice(0, n);
const pyStr = (v) => (nn(v) ? String(v) : "nan");   // str(NaN) do pandas
const trunc = (v) => Math.trunc(Number(v));

/** sort_values estável, NaN por último (como o pandas). keys: [[coluna, desc]]. */
function sortBy(rows, keys, desc = false) {
  if (typeof keys === "string") keys = [[keys, desc]];
  const idx = rows.map((r, i) => [r, i]);
  idx.sort((A, B) => {
    for (const [k, d] of keys) {
      const a = num(A[0][k]), b = num(B[0][k]);
      const an = Number.isNaN(a), bn = Number.isNaN(b);
      if (an || bn) { if (an && bn) continue; return an ? 1 : -1; }
      if (a !== b) return d ? b - a : a - b;
    }
    return A[1] - B[1];
  });
  return idx.map((x) => x[0]);
}

const colunas = (rows) => { const s = new Set(); for (const r of arr(rows)) for (const k of Object.keys(r)) s.add(k); return s; };

// ------------------------------------------------------------------ estado de uma montagem
class Estado {
  constructor() { this.blk = []; this.usadas = []; this.semNota = new Set(); }
  registrar(b) { this.blk.push(b); return `<div class="blk" data-b="${this.blk.length - 1}"></div>`; }
}

function tabela(S, rows, cols, maxLinhas = 25, uid = null, search = false) {
  const d = rows.slice(0, maxLinhas);
  const linhas = d.map((r) => cols.map(([c, , t]) => {
    const v = r[c];
    if (t === "t" || t === "tw") return nn(v) && v !== "" ? String(v) : null;
    return nn(v) ? numJ(v, 6) : null;
  }));
  return S.registrar({ t: "tab", id: uid, s: search ? 1 : 0, c: cols.map(([, h, t]) => [h, t]), r: linhas });
}

const kpi = (valor, rotulo, dica = "", hero = false) =>
  `<div class="kpi${hero ? " hero" : ""}"><b>${esc(valor)}</b><span>${esc(rotulo)}</span>${dica ? `<small>${esc(dica)}</small>` : ""}</div>`;

const tip = (titulo, linhas) => [titulo, linhas.filter(([, v]) => v !== null && v !== undefined && v !== "").map(([k, v]) => [k, v])];

/** p pseudo por permutação: o menor valor possível é 1/(perms+1), então escreve-se "≤". */
function fp(p, perms = 999) {
  if (!nn(p)) return "p indefinido";
  const piso = 1 / (perms + 1);
  return p <= piso + 1e-9 ? `p ≤ ${fnum(piso, 3)}` : `p = ${fnum(p, 3)}`;
}

function metodo(S, texto, chaves = []) {
  for (const k of chaves) if (!S.usadas.includes(k)) S.usadas.push(k);
  const lis = chaves.map((k) => `<li>${REFS[k]}</li>`).join("");
  const rl = lis ? `<span class="rl">Referências</span><ul class="refs">${lis}</ul>` : "";
  return `<aside class="metodo"><span class="lab">Nota metodológica</span><p>${texto}</p>${rl}</aside>`;
}

// ------------------------------------------------------------------ estrutura: notas, partes, sumário
function estruturar(S, html) {
  const pat = /<h2 id="([a-z]+)"><span class="n">([^<]*)<\/span>([^<]*)<\/h2>/g;
  const ms = [...html.matchAll(pat)];
  if (!ms.length) return [html, []];
  const out = [html.slice(0, ms[0].index)], idx = [];
  const parteDe = {};
  for (const [L, tit, ids] of PARTES) for (const i of ids) parteDe[i] = [L, tit];
  const vistas = new Set();
  ms.forEach((m, k) => {
    const fim = k + 1 < ms.length ? ms[k + 1].index : null;
    const ini = m.index + m[0].length;
    let corpo = fim !== null ? html.slice(ini, fim) : html.slice(ini);
    const sid = m[1];
    let cab = m[0];
    if (parteDe[sid] && !vistas.has(parteDe[sid][0])) {
      const [L, tit] = parteDe[sid];
      vistas.add(L);
      cab = `<div class="parte"><span>Parte ${L}</span><b>${tit}</b></div>` + cab;
    }
    idx.push([sid, m[2], m[3], parteDe[sid] ? parteDe[sid][0] : ""]);
    let resto = "";
    if (fim === null) {
      const j = corpo.indexOf("<footer>");
      if (j >= 0) { resto = corpo.slice(j); corpo = corpo.slice(0, j); }
    }
    if (Object.hasOwn(NOTAS, sid) && sid !== "metodo" && !S.semNota.has(sid)) {
      let [t, ch] = NOTAS[sid];
      if (sid === "cidades" && corpo.includes("Ponto quente")) {
        t += " <b>Hexágonos</b>: os locais de votação são agregados em hexágonos H3 e a estatística Gi* (Getis e Ord) identifica pontos quentes e frios, "
          + "com os 6 vizinhos mais próximos e 999 permutações, só em hexágonos com ao menos 30 votos válidos.";
        ch = ch.concat(["getis", "ord95"]);
      }
      corpo += metodo(S, t, ch);
    }
    out.push(cab + corpo + resto);
  });
  return [out.join(""), idx];
}

function toc(idx) {
  let grupos = "";
  for (const [L, tit] of PARTES) {
    const its = idx.filter((x) => x[3] === L);
    if (!its.length) continue;
    const lis = its.map(([a, n, t]) => `<a href="#${a}"><i>${n}</i>${t}</a>`).join("");
    grupos += `<div><h4><b>${L}</b>${tit}</h4>${lis}</div>`;
  }
  return grupos;
}

// ------------------------------------------------------------------ montagem da página
const calc = (id, n, titulo) => `<h2 id="${id}"><span class="n">${n}</span>${titulo}</h2><p class="calc">Calculando…</p>`;

export function montar(ctx, malha, opcoes = {}) {
  const pend = new Set(opcoes.pendentes ? Array.from(opcoes.pendentes) : []);
  const estrito = !!opcoes.estrito;
  const S = new Estado();
  const info = ctx.info, conc = ctx.conc || {}, mo = ctx.moran || {};
  const gm0 = arr(ctx.gm), mun = arr(ctx.municipal);
  const nome = nomePt(info.nome);
  const partes = [];
  const a = (s) => partes.push(s);
  const colsGm = colunas(gm0), colsMun = colunas(mun);

  // ---- cabeçalho e KPIs
  a('<header class="hd"><div class="mark">' + ICON + '</div>'
    + `<p class="eyebrow">${esc(ctx.cargo_nome)} · ${esc(ctx.uf)} · ${ctx.ano} · ${info.turno}º turno · nº ${info.numero}</p><h1>${esc(nome)}</h1>`
    + '<p class="sub">Análise espacial da votação por município e nas principais cidades.</p></header>');
  a('<div class="kpis">');
  a(kpi(fnum(info.votos_total), "votos nominais", `${fnum(ctx.pct_estado, 2)}% dos votos válidos do estado`, true));
  a(kpi(`${conc.n_com_voto} de ${conc.n_municipios}`, "municípios com voto",
    `em ${conc.n_municipios - conc.n_com_voto} municípios não teve nenhum voto`));
  a(kpi(String(conc.n_para_50), "município(s) para 50% dos votos", `${conc.n_para_80} para 80%`));
  a(kpi(fnum(conc.gini, 2), "concentração (Gini)", "0 = espalhado · 1 = concentrado"));
  const moI = nn(mo.I) ? mo.I : null;
  if (moI !== null) a(kpi(fnum(moI, 2), "vizinhança (Moran)", `−1 a 1 · 0 = sem padrão · ${fp(mo.p)}`));
  a("</div>");
  a(GUIA);

  // ---- 1. Panorama
  const dmap = new Map(arr(malha && malha.municipios).map((m) => [Number(m.cod), m.d]));
  const vb = (malha && malha.vb) || "0 0 760 400";
  const gm = gm0.map((r, i) => ({
    ...r, nm: nomePt(r.NM_MUNICIPIO),
    _d: dmap.has(Number(r.CD_MUNICIPIO)) ? dmap.get(Number(r.CD_MUNICIPIO)) : ((malha && malha.municipios[i] && malha.municipios[i].d) || ""),
  }));
  const [cV, legV] = classesQuantil(gm.map((r) => r.votos), 6, "", true);
  const [cP, legP] = classesQuantil(gm.map((r) => r.pct_validos), 6, "%");
  const [cQ, legQ] = classesQl(gm.map((r) => r.quociente_locacional));
  const polys = gm.map((r, i) => ({
    id: trunc(r.CD_MUNICIPIO), d: r._d, cls: [cV[i], cP[i], cQ[i]],
    tip: tip(r.nm, [
      ["Votos", fnum(r.votos)], ["% dos votos válidos", fnum(r.pct_validos, 2) + "%"],
      ["Votos por 100 eleitores aptos", fnum(r.votos_por_100_aptos, 2)],
      ["Quociente locacional", fnum(r.quociente_locacional, 2)],
      ["Posição do candidato aqui", nn(r.posicao_no_municipio) ? `${trunc(r.posicao_no_municipio)}º` : ""],
      ["Mais votado no município", nn(r.lider_nome) ? nomePt(r.lider_nome) : ""]]),
  }));
  const metr = [
    { key: "votos", label: "Votos", legend: legV, note: "Quantidade de votos que o candidato teve em cada município. Mostra onde está o volume." },
    { key: "pct", label: "% dos válidos", legend: legP,
      note: "Percentual dos votos válidos do município que foram para o candidato. Mostra a força proporcional, sem favorecer cidade grande." },
    { key: "ql", label: "Mais forte que a média", legend: legQ,
      note: "Quociente locacional: a % dele no município dividida pela % dele no estado. Acima de 1, o município vota nele mais do que a média." },
  ];
  a('<h2 id="panorama"><span class="n">1</span>Panorama estadual</h2>');
  a('<p class="lead">Passe o mouse em um município para ver os números e <b>clique nele para abrir um card com os detalhes</b>. Os três botões trocam o que o mapa '
    + 'mostra: volume de votos, força proporcional e onde ele é mais forte que a média do estado.</p>');
  const geo = geoDefs(polys);
  a('<div class="card"><div class="msearch"><input type="search" id="msq" placeholder="Buscar município pelo nome" '
    + 'autocomplete="off" role="combobox" aria-expanded="false" aria-controls="msl" aria-label="Buscar município pelo nome">'
    + '<ul id="msl" role="listbox" hidden></ul></div>'
    + '<p class="mhint dica"><span>Clique em um município, em qualquer mapa, para ver os detalhes dele: <b>votos, posição, mais votados e indicadores</b>.</span></p>'
    + S.registrar(mapBloco("mapa-estado", polys, metr, vb, "Mapa de votos por município")) + "</div>");

  const top = head(mun, 30).map((r) => ({
    ...r, NM_MUNICIPIO: nomePt(r.NM_MUNICIPIO), ...(colsMun.has("lider_nome") ? { lider_nome: nomePt(r.lider_nome) } : {}),
  }));
  a("<h3>Municípios com mais votos</h3>");
  const ranking = head(mun, 12).map((r) => ({
    label: nomePt(r.NM_MUNICIPIO), value: Number(r.votos), fmt: fnum(r.votos),
    tip: tip(nomePt(r.NM_MUNICIPIO), [["Votos", fnum(r.votos)], ["% dos válidos", fnum(r.pct_validos, 2) + "%"],
      ["Eleitores aptos", fnum(r.eleitores)]]),
  }));
  a('<div class="card"><div class="scroll">' + barChart(ranking, "Municípios com mais votos") + "</div></div>");
  a(tabela(S, top, [["NM_MUNICIPIO", "Município", "t"], ["votos", "Votos", "i"],
    ["pct_validos", "% válidos", "d2"], ["votos_por_100_aptos", "Votos/100 aptos", "d2"],
    ["quociente_locacional", "Quociente locacional", "d2"],
    ["abstencao_pct", "Abstenção %", "d1"],
    ["posicao_no_municipio", "Posição no município", "i"],
    ["lider_nome", "Mais votado no município", "t"]], 30, "tb-top"));
  const forte = sortBy(mun.filter((r) => num(r.validos) >= 2000), "pct_validos", true).map((r) => ({ ...r, NM_MUNICIPIO: nomePt(r.NM_MUNICIPIO) }));
  a("<h3>Maior % de votos válidos (municípios com pelo menos 2.000 votos válidos)</h3>");
  a(tabela(S, forte, [["NM_MUNICIPIO", "Município", "t"], ["pct_validos", "% válidos", "d2"],
    ["votos", "Votos", "i"], ["validos", "Votos válidos", "i"]], 12, "tb-forte"));
  const todos = mun.map((r) => ({ ...r, NM_MUNICIPIO: nomePt(r.NM_MUNICIPIO) }));
  a(`<details><summary>Tabela completa dos ${todos.length} municípios (com busca)</summary>`);
  a(tabela(S, todos, [["NM_MUNICIPIO", "Município", "t"], ["votos", "Votos", "i"],
    ["pct_validos", "% válidos", "d2"], ["votos_por_100_aptos", "Votos/100 aptos", "d2"],
    ["quociente_locacional", "Quociente locacional", "d2"],
    ["eleitores", "Eleitores aptos", "i"], ["abstencao_pct", "Abstenção %", "d1"]], 10000, "tb-todos", true));
  a("</details>");

  // ---- 2. Concentração
  const par = arr(ctx.pareto);
  const cum = par.map((r) => Number(r.cum_share));
  const nomes = mun.map((r) => nomePt(r.NM_MUNICIPIO));
  const votos = mun.map((r) => trunc(r.votos));
  const n80 = conc.n_para_80;
  const xmax = trunc(Math.min(Math.max(conc.n_com_voto, 2), Math.max(20, 3 * n80)));
  const series = [];
  for (let i = 0; i < Math.min(nomes.length, xmax, cum.length); i++) series.push([i + 1, nomes[i], votos[i], new PF(pyRound(cum[i], 2))]);
  const marcos = [];
  for (const n of [conc.n_para_50, n80]) {
    if (!(n >= 1 && n <= cum.length)) continue;
    marcos.push({ x: n, y: cum[n - 1],
      rotulo: `${n === 1 ? "O maior município" : "Os " + n + " maiores"} somam ${fnum(cum[n - 1], 0)}% dos votos` });
  }
  a('<h2 id="concentracao"><span class="n">2</span>Concentração</h2>');
  a(`<p class="lead">${conc.n_para_50} município(s) concentram 50% dos votos e ${n80} concentram 80%. `
    + `O maior município responde por ${fnum(conc.top1_share, 1)}% e os 10 maiores por `
    + `${fnum(conc.top10_share, 1)}%. Em termos práticos, a base se comporta como se fossem `
    + `${fnum(conc.n_efetivo_municipios, 1)} municípios de peso igual. Passe o mouse sobre a curva.</p>`);
  a('<div class="card"><div class="scroll">' + (series.length ? paretoChart(series, marcos, xmax) : "") + "</div></div>");

  // ---- 3. Vizinhança
  const temLisa = gm.some((r) => typeof r.lisa_cluster === "string");
  if (pend.has("vizinhanca") || !temLisa) {
    S.semNota.add("vizinhanca");
    a(calc("vizinhanca", 3, "Autocorrelação espacial: vizinhança"));
  } else {
    vizinhanca();
  }
  function vizinhanca() {
    const nmap = { "Alto-Alto": "hh", "Baixo-Baixo": "ll", "Outlier espacial": "ou", "Não significativo": "ns" };
    const [cL, legL] = classesCategoria(gm.map((r) => r.lisa_cluster), nmap,
      ["Alto-Alto", "Baixo-Baixo", "Outlier espacial", "Não significativo"]);
    const polysL = gm.map((r, i) => {
      const det = typeof r.lisa_detalhe === "string" && r.lisa_detalhe ? r.lisa_detalhe : "Sem padrão significativo";
      return { id: polys[i].id, d: polys[i].d, cls: [cL[i]],
        tip: tip(r.nm, [["Padrão", r.lisa_cluster !== "Não significativo" ? r.lisa_cluster : "Sem padrão"],
          ["Leitura", det], ["% dos votos válidos", fnum(r.pct_validos, 2) + "%"], ["Votos", fnum(r.votos)]]) };
    });
    a('<h2 id="vizinhanca"><span class="n">3</span>Autocorrelação espacial: vizinhança</h2>');
    if (moI !== null) {
      const forca = moI >= 0.5 ? "forte" : moI >= 0.25 ? "moderada" : moI >= 0.1 ? "fraca" : "praticamente inexistente";
      const sig = (nn(mo.p) && mo.p !== 0 ? mo.p : 1) < 0.05
        ? "e isso é estatisticamente significativo: a chance de ser acaso é menor que 5%." : "mas não dá para descartar que seja acaso.";
      a(`<p class="lead">O índice de Moran da % de votos válidos é <b>${fnum(moI, 3)}</b> (${fp(mo.p)}): `
        + `a vizinhança importa de forma <b>${forca}</b>, ${sig}</p>`);
    }
    a('<div class="prose"><p><b>O que é autocorrelação espacial.</b> É a pergunta &quot;o que acontece num lugar se parece com '
      + 'o que acontece ao lado?&quot;. Aqui, cada lugar é um município e &quot;ao lado&quot; são os municípios que fazem divisa com ele. '
      + 'Se a votação do candidato estivesse espalhada ao acaso, saber a % dele numa cidade não diria nada sobre a da cidade vizinha. '
      + 'Quando a autocorrelação é positiva, cidades fortes tendem a ter vizinhas fortes e cidades fracas tendem a ter vizinhas fracas: '
      + 'o voto forma <em>manchas</em> no mapa. Isso costuma ter causa concreta, como a região onde o candidato fez campanha, a base de '
      + 'uma liderança local, uma categoria profissional ou um perfil regional de eleitorado.</p>'
      + '<p><b>O índice de Moran</b> resume isso num número entre −1 e +1. Perto de 0, não há padrão. Positivo, há manchas. Negativo, '
      + 'vizinhos tendem a ser opostos. Ele usa a <em>% de votos válidos</em>, e não o total de votos, para que cidade grande não '
      + 'apareça forte só por ter mais gente.</p></div>');
    a('<div class="card">' + S.registrar(mapBloco("mapa-lisa", polysL, [{ key: "lisa", label: "LISA", legend: legL,
      note: "Cada município é comparado com os vizinhos que fazem divisa. Só aparecem as diferenças estatisticamente significativas (p < 0,05)." }],
    vb, "Clusters espaciais LISA")) + "</div>");
    a('<p class="lead" style="margin-top:16px">O Moran diz <em>se</em> há manchas; o mapa acima (LISA) diz <em>onde</em> elas estão. '
      + `Foram ${nn(mo.n_hh) ? mo.n_hh : 0} município(s) em núcleo de força, ${nn(mo.n_ll) ? mo.n_ll : 0} em vazio e ${nn(mo.n_out) ? mo.n_out : 0} em contraste `
      + '(ilha de voto ou lacuna). Só entra o que é estatisticamente significativo; o resto fica cinza.</p>');
    a('<div class="expl">'
      + '<div><h4><i style="background:var(--hh)"></i>Núcleo de força</h4><p>Município com % alta, cercado de vizinhos também altos. '
      + 'É a base consolidada: o candidato é conhecido na região inteira, não só numa cidade. O caminho natural de crescimento é puxar '
      + 'os vizinhos que ainda estão abaixo.</p></div>'
      + '<div><h4><i style="background:var(--ou)"></i>Ilha de voto</h4><p>Município forte cercado de vizinhos fracos. O voto vem de um '
      + 'motivo local (uma liderança, uma comunidade, um cabo eleitoral) e não transborda para a região. Mostra que há voto ali, mas '
      + 'também que ele pode depender de uma pessoa só.</p></div>'
      + '<div><h4><i style="background:var(--ou);opacity:.45"></i>Lacuna</h4><p>Município fraco cercado de vizinhos fortes. Costuma ser '
      + 'a oportunidade mais barata: o candidato já é conhecido ao redor, e a cidade ficou para trás.</p></div>'
      + '<div><h4><i style="background:var(--ll)"></i>Vazio</h4><p>Município fraco cercado de vizinhos fracos. Sem voto e sem presença. '
      + 'Quando o candidato tem poucos votos no estado, essa classe domina o mapa e diz pouco; o mais útil é o resto.</p></div></div>');
    const gm2 = sortBy(gm.map((r) => ({ ...r, NM_MUNICIPIO: r.nm, lisa_detalhe: nn(r.lisa_detalhe) ? String(r.lisa_detalhe) : "" })), "votos", true);
    const colunasL = [["NM_MUNICIPIO", "Município", "t"], ["votos", "Votos", "i"], ["pct_validos", "% válidos", "d2"]];
    const blocos = [
      ["Núcleos de força", gm2.filter((r) => r.lisa_cluster === "Alto-Alto"),
        "Municípios fortes cercados de vizinhos fortes. É onde a base está consolidada.", "tb-nucleo"],
      ["Ilhas de voto", gm2.filter((r) => r.lisa_cluster === "Outlier espacial" && r.lisa_detalhe.startsWith("Forte")),
        "Municípios fortes em meio a vizinhos fracos. Voto concentrado, que não se espalhou.", "tb-ilha"],
      ["Lacunas (oportunidades)", gm2.filter((r) => r.lisa_cluster === "Outlier espacial" && r.lisa_detalhe.startsWith("Fraco")),
        "Municípios fracos em meio a vizinhos fortes. Tendem a ser os alvos mais baratos de crescimento.", "tb-lacuna"],
    ];
    for (const [tit, df, expl, uid] of blocos) {
      if (df.length) {
        a(`<h3>${tit}</h3><p class="lead" style="margin-bottom:10px">${expl}</p>`);
        a(tabela(S, df, colunasL, 20, uid));
      }
    }
  }

  // ---- 4. Cidades
  a('<h2 id="cidades"><span class="n">4</span>Cidades</h2>');
  const cidades = arr(ctx.cidades);
  const comNomes = cidades.some((c) => !arr(c.locais).every((l) => String(l.local_nome).startsWith("Local ")));
  if (comNomes) {
    a('<div class="callout"><b>Leitura com cuidado:</b> o TSE não publica voto por bairro. A unidade mínima é a seção eleitoral, '
      + 'que funciona num local de votação. Por isso as cidades são detalhadas por <b>local de votação</b>, bairro e zona '
      + 'eleitoral, que são dados oficiais. Eles descrevem onde a pessoa <b>vota</b>, que costuma ser perto de onde mora, '
      + 'mas não é a mesma coisa.</div>');
  }
  if (cidades.length) {
    if (ctx.criterio_cidades === "manual") {
      a(`<p class="lead">Cidades escolhidas manualmente no <code>config.json</code> (${cidades.length}), em ordem decrescente de votos.</p>`);
    } else {
      a(`<p class="lead">Aparecem as ${cidades.length} cidades em que o candidato teve <b>mais votos</b>, em ordem `
        + 'decrescente (o critério é o volume absoluto de votos, não o percentual). Para escolher outras, use '
        + '<code>"cidades"</code> no <code>config.json</code>.</p>');
    }
    a('<div class="tabset"><div class="cscroll">'
      + '<button class="arr l" type="button" aria-label="Cidades anteriores" hidden>'
      + '<svg viewBox="0 0 24 24"><path d="M15 5l-7 7 7 7"/></svg></button>'
      + '<button class="arr r" type="button" aria-label="Próximas cidades" hidden>'
      + '<svg viewBox="0 0 24 24"><path d="M9 5l7 7-7 7"/></svg></button>'
      + '<div class="ctabs" role="tablist" aria-label="Cidades">');
    for (const c of cidades) {
      a(`<button class="ctab" type="button" role="tab"><b>${esc(c.nome)}</b><span>${fnum(c.votos)} votos · ${fnum(c.pct, 1)}%</span></button>`);
    }
    a("</div></div>");
    cidades.forEach((c, ci) => a(cidade(S, ci, c)));
    a("</div>");
  }

  // ---- 5. Comparação com outros candidatos
  const cmp = arr(ctx.comparacao);
  let sec = 4;
  const nxt = () => ++sec;
  if (cmp.length && cmp.some((r) => r.foco)) comparacao();
  function comparacao() {
    a(`<h2 id="comparacao"><span class="n">${nxt()}</span>Comparação com os mais votados de cada partido</h2>`);
    const f = cmp.find((r) => r.foco);
    const outros = cmp.filter((r) => !r.foco && r.top_do_partido);
    const N = trunc(f.n_municipios);
    const maisAmplos = outros.filter((r) => r.n_mun_1pct > f.n_mun_1pct).length;
    const maisVotos = outros.filter((r) => r.votos > f.votos).length;
    const melhor = outros.length ? sortBy(outros, "n_mun_1pct", true)[0] : null;
    const qtd = (n, o) => (n === 0 ? `nenhum ${o[0]}` : n === 1 ? `1 ${o[0]}` : `${n} ${o[1]}`);
    let txt = `<b>${esc(nome)}</b> teve voto em <b>${trunc(f.n_mun_voto)} de ${N}</b> municípios, pelo menos 0,5% dos votos válidos em `
      + `${trunc(f.n_mun_05pct)}, pelo menos 1% em ${trunc(f.n_mun_1pct)} e pelo menos 5% em ${trunc(f.n_mun_5pct)}. `
      + `Entre os ${outros.length + 1} candidatos comparados, `
      + `${qtd(maisAmplos, ["teve", "tiveram"])} presença de 1% em mais municípios do que ele, e `
      + `${qtd(maisVotos, ["teve", "tiveram"])} mais votos no total.`;
    if (melhor !== null && melhor.n_mun_1pct > f.n_mun_1pct) {
      txt += ` A maior abrangência é de ${esc(nomePt(melhor.nome))} (${esc(pyStr(melhor.sigla))}), com ${trunc(melhor.n_mun_1pct)} municípios.`;
    }
    const pl = outros.filter((r) => r.sigla === "PL");
    if (pl.length) {
      const x = pl[0];
      const cmpv = x.n_mun_1pct > f.n_mun_1pct ? "mais" : x.n_mun_1pct < f.n_mun_1pct ? "menos" : "o mesmo número de";
      txt += ` O mais votado do PL, ${esc(nomePt(x.nome))}, fez ${fnum(x.votos)} votos e chegou a 1% em `
        + `${trunc(x.n_mun_1pct)} municípios, ${cmpv} que ${esc(nome)}.`;
    }
    a(`<p class="lead">${txt}</p>`);
    const base = cmp.filter((r) => r.foco || r.top_do_partido);
    const medidas = [["n_mun_voto", "Qualquer voto", "Em quantos municípios o candidato teve pelo menos um voto"],
      ["n_mun_05pct", "0,5% ou mais", "Em quantos municípios o candidato teve 0,5% ou mais dos votos válidos"],
      ["n_mun_1pct", "1% ou mais", "Em quantos municípios o candidato teve 1% ou mais dos votos válidos"]];
    a('<div class="tabset"><div class="tablist" role="tablist">'
      + medidas.map(([, r]) => `<button type="button" role="tab">${esc(r)}</button>`).join("") + "</div>");
    for (const [col, , tit] of medidas) {
      const ordem = sortBy(base, [[col, true], ["votos", true]]);
      const rows = ordem.map((r) => ({
        label: Array.from(`${nomePt(r.nome)} (${pyStr(r.sigla)})`).slice(0, 34).join(""), value: Number(r[col]),
        fmt: String(trunc(r[col])), hl: !!r.foco,
        tip: tip(`${nomePt(r.nome)} (${pyStr(r.sigla)})`, [["Votos", fnum(r.votos)], ["% dos válidos no estado", fnum(r.pct_estado, 2) + "%"],
          ["Municípios com algum voto", `${trunc(r.n_mun_voto)} de ${trunc(r.n_municipios)}`],
          ["Municípios com 0,5% ou mais", String(trunc(r.n_mun_05pct))],
          ["Municípios com 1% ou mais", String(trunc(r.n_mun_1pct))],
          ["Municípios com 5% ou mais", String(trunc(r.n_mun_5pct))],
          ["Entre os 3 mais votados em", `${trunc(r.n_top3)} municípios`],
          ["Situação", typeof r.situacao === "string" ? r.situacao : ""]]),
      }));
      a(`<div class="pane"><div class="card"><h3>${esc(tit)}</h3><div class="scroll">` + barChart(rows, tit) + "</div>"
        + '<p style="margin:10px 0 0;font-size:12.5px;color:var(--muted)">O candidato desta análise aparece em dourado. '
        + `Total de municípios: ${N}.</p></div></div>`);
    }
    a("</div>");
    const ordem = sortBy(base, "n_mun_1pct", true);
    const tb = ordem.map((r) => ({ ...r, candidato: nomePt(r.nome) + (r.foco ? " (foco)" : "") }));
    const colsC = [["candidato", "Candidato", "t"], ["sigla", "Partido", "t"], ["votos", "Votos", "i"],
      ["pct_estado", "% válidos no estado", "d2"], ["n_mun_voto", "Municípios com algum voto", "i"],
      ["n_mun_05pct", "Municípios com 0,5%+", "i"], ["n_mun_1pct", "Municípios com 1%+", "i"],
      ["n_mun_5pct", "Municípios com 5%+", "i"], ["n_top3", "Entre os 3 mais votados", "i"],
      ["top1_share", "% dos votos na maior cidade", "d1"], ["gini", "Gini", "d2"]];
    if (colunas(cmp).has("moran_I")) colsC.push(["moran_I", "Moran", "d2"]);
    a(tabela(S, tb, colsC, 40, "tb-comp"));
    a('<div class="prose" style="margin-top:14px"><p><b>Como ler.</b> Quase todo candidato recebe algum voto em quase todo '
      + 'município, então contar municípios com pelo menos um voto não distingue ninguém. Por isso o gráfico mostra três '
      + 'réguas: <em>qualquer voto</em> (o alcance bruto, que quase todos têm), <em>0,5% ou mais</em> e <em>1% ou mais</em> dos '
      + 'votos válidos do município (presença relevante, cada vez mais exigente). A tabela traz ainda 5%. As outras colunas '
      + 'ajudam a separar volume de alcance:</p><ul>'
      + '<li><b>Entre os 3 mais votados</b>: em quantos municípios ele ficou no pódio. Mede força local, não só presença.</li>'
      + '<li><b>% dos votos na maior cidade</b>: quanto do total vem do município onde mais votou. Alto significa dependência '
      + 'de uma cidade (Porto Alegre, em geral); baixo, votos espalhados.</li>'
      + '<li><b>Gini</b> e <b>Moran</b>: os mesmos das seções 2 e 3, calculados para cada candidato. Gini alto = concentrado; '
      + 'Moran alto = votos formam manchas contínuas no mapa.</li></ul>'
      + '<p>Cada partido entra com o seu candidato mais votado, mais o candidato desta análise. O partido é a sigla, não a '
      + 'federação (o PCdoB, por exemplo, está na Federação Brasil da Esperança com PT e PV). Candidatos de partidos com chapas '
      + 'enormes e dinheiro de campanha muito diferente não são comparáveis em esforço, só em resultado.</p></div>');
  }

  // ---- Análises complementares
  const an = ctx.analises && typeof ctx.analises === "object" ? ctx.analises : null;
  analises();

  // ---- Potencial
  a(`<h2 id="potencial"><span class="n">${nxt()}</span>Eficiência e potencial</h2>`);
  a('<p class="lead">Duas medidas para responder onde vale concentrar esforço: uma diz o quanto o candidato já converte do '
    + 'eleitorado de cada município, a outra diz quantos votos ainda há para buscar.</p>');
  a('<div class="prose"><ul>'
    + '<li><b>Eficiência: votos por 100 eleitores aptos.</b> De cada 100 pessoas que podem votar no município, quantas votaram no '
    + 'candidato. Compara cidades de tamanhos diferentes na mesma régua e mostra onde ele converte melhor o eleitorado.</li>'
    + '<li><b>Potencial: votos até a média.</b> Se o município votasse nele na mesma proporção do estado inteiro, quantos votos '
    + 'a mais ele teria. A conta é: <em>% dele no estado × votos válidos do município − votos que ele teve</em>. Se der '
    + 'negativo (o município já está acima da média), vale zero.</li></ul></div>');
  const pot = sortBy(mun, "votos_ate_media_estadual", true);
  if (pot.length && num(pot[0].votos_ate_media_estadual) > 0) {
    const r0 = pot[0];
    const esp = ctx.pct_estado / 100 * Number(r0.validos);
    a('<div class="exemplo"><b>Exemplo com os números dele.</b> '
      + `${esc(nomePt(r0.NM_MUNICIPIO))} teve ${fnum(r0.validos)} votos válidos. Na média do estado (${fnum(ctx.pct_estado, 2)}%), `
      + `${esc(nome)} receberia cerca de ${fnum(esp)} votos ali. Teve ${fnum(r0.votos)} (${fnum(r0.pct_validos, 2)}%). `
      + `A diferença, <b>${fnum(r0.votos_ate_media_estadual)} votos</b>, é o potencial do município.</div>`);
  }
  a('<div class="callout"><b>Como usar:</b> não é uma projeção nem uma promessa de que dá para chegar à média. Cidades grandes '
    + 'sobem para o topo simplesmente porque têm muito eleitor, então a lista mostra onde a diferença em votos é maior, não onde é '
    + 'mais fácil. Para achar a oportunidade realista, cruze com a seção 3: um município de potencial alto que é uma <em>lacuna</em> '
    + '(fraco entre vizinhos fortes) tende a custar menos do que um município fraco cercado de municípios fracos.</div>');
  a(tabela(S, pot.map((r) => ({ ...r, NM_MUNICIPIO: nomePt(r.NM_MUNICIPIO) })),
    [["NM_MUNICIPIO", "Município", "t"], ["eleitores", "Eleitores aptos", "i"], ["votos", "Votos", "i"],
      ["pct_validos", "% válidos", "d2"], ["votos_por_100_aptos", "Votos/100 aptos", "d2"],
      ["votos_ate_media_estadual", "Votos até a média", "i"]], 20, "tb-pot"));

  // ---- Contexto
  a(`<h2 id="contexto"><span class="n">${nxt()}</span>Contexto: partido, abstenção, brancos e nulos</h2>`);
  a("<h3>Candidatos do mesmo partido</h3>");
  a(tabela(S, arr(ctx.colegas).map((r) => ({ ...r, nome: nomePt(r.nome) })),
    [["nome", "Candidato", "t"], ["numero", "Número", "i"], ["votos", "Votos", "i"],
      ["rank_estado", "Posição no estado", "i"], ["share_partido", "% dos votos do partido", "d1"]], 15, "tb-col"));
  a("<h3>Municípios com maior abstenção</h3>");
  const ab = sortBy(mun.filter((r) => num(r.votos) > 0), "abstencao_pct", true).map((r) => ({ ...r, NM_MUNICIPIO: nomePt(r.NM_MUNICIPIO) }));
  a(tabela(S, ab, [["NM_MUNICIPIO", "Município", "t"], ["abstencao_pct", "Abstenção %", "d1"],
    ["brancos_nulos_pct", "Brancos+nulos %", "d1"], ["votos", "Votos", "i"],
    ["pct_validos", "% válidos", "d2"]], 15, "tb-abs"));
  if (nn(ctx.regioes) && Array.isArray(ctx.regioes)) {
    const r = ctx.regioes;
    a("<h3>Por região</h3>");
    const c0 = r.length ? Object.keys(r[0])[0] : "regiao";
    a(tabela(S, r, [[c0, "Região", "t"], ["municipios", "Municípios", "i"], ["votos", "Votos", "i"],
      ["pct_validos", "% válidos", "d2"], ["share_votos_estado", "% dos votos do candidato", "d1"]], 40, "tb-reg"));
  }
  const d = ctx.despesas;
  if (d && typeof d === "object") {
    a(`<h2 id="contas"><span class="n">${nxt()}</span>Prestação de contas</h2>`);
    a('<div class="kpis">' + kpi("R$ " + fnum(d.total, 2), "despesas declaradas") + kpi("R$ " + fnum(d.custo_por_voto, 2), "custo por voto") + "</div>");
    if (arr(d.por_categoria).length) {
      a(tabela(S, d.por_categoria.map((r) => ({ ...r, Valor: r.valor })), [["categoria", "Categoria", "t"], ["Valor", "R$", "d2"]], 15, "tb-desp"));
    }
  }

  a('<h2 id="metodo"><span class="n">M</span>Notas metodológicas</h2>');
  a('<h3>Fontes de dados</h3><div class="prose"><p>Votação por seção (boletins de urna), perfil do eleitorado e eleitorado por local de votação, do '
    + 'Portal de Dados Abertos do TSE, e malha municipal do IBGE.</p></div>');
  a('<h3>Definições</h3><div class="prose"><ul>'
    + '<li><b>% de votos válidos</b>: votos do candidato ÷ (votos nominais + de legenda), sem brancos e nulos.</li>'
    + '<li><b>Moran e LISA</b>: vizinhança por divisa, 999 permutações, p &lt; 0,05. O Gini é calculado sobre todos os municípios do estado, incluindo os sem voto.</li>'
    + '<li><b>Abstenção</b>: 1 − (votos de todos os candidatos, brancos e nulos ÷ eleitores aptos). É uma aproximação.</li>'
    + '</ul></div>');
  a('<h3>Referências consolidadas</h3><div class="metodo" style="margin-top:0"><ul class="refs">@@REFS@@</ul></div>');

  let [corpo, idx] = estruturar(S, partes.join(""));
  const usadas = S.usadas.slice().sort((x, y) => (REFS[x] < REFS[y] ? -1 : REFS[x] > REFS[y] ? 1 : 0));
  corpo = corpo.split("@@REFS@@").join(usadas.map((k) => `<li>${REFS[k]}</li>`).join(""));
  const sumario = `<section class="toc" id="sumario"><h3>Sumário</h3><div class="tocg">${toc(idx)}</div></section>`;
  const p0 = corpo.indexOf('<div class="parte">');
  if (p0 >= 0) corpo = corpo.slice(0, p0) + sumario + corpo.slice(p0);

  return {
    titulo: `${nome} · análise espacial ${ctx.ano}`, corpo, blocos: S.blk, geo,
    det: detalhes(ctx, gm, !!an, an, colsMun), ano: ctx.ano, uf: ctx.uf, cargo_cod: trunc(nn(ctx.cargo) ? ctx.cargo : 7),
    numero: info.numero, nome, cargo: ctx.cargo_nome, turno: info.turno, votos: trunc(info.votos_total),
  };

  // ================================================================== análises complementares
  function analises() {
    const meta = (an && an.meta) || {};
    const temFed = meta.federacao ? !meta.federacao.sem_colegas : null;
    const ordem = [
      ["sobreposicao", "Sobreposição com outros candidatos", () => !!an || pend.has("sobreposicao"), () => Array.isArray(an.sobreposicao), secSobreposicao],
      ["federacao", "Participação na federação", () => temFed === true || (temFed === null && pend.has("federacao")),
        () => !!(an && Array.isArray(an.mun) && meta.federacao), secFederacao],
      ["modelo", "Modelo: acima e abaixo do esperado", () => temFed === true || (temFed === null && pend.has("modelo")),
        () => !!(an && Array.isArray(an.mun) && Array.isArray(an.modelo) && meta.modelo), secModelo],
      ["distancia", "Distância dos redutos", () => !!an || pend.has("distancia"), () => !!(Array.isArray(an.mun) && Array.isArray(an.bandas) && meta.distancia), secDistancia],
    ];
    function montarGmx() {
      const anMap = new Map(an.mun.map((r) => [Number(r.CD_MUNICIPIO), r]));
      const colsAn = colunas(an.mun);
      const fill = ["fed_votos", "fed_pct", "part_fed", "dif_fed", "esperado_fed", "z_residuo", "residuo_pp", "dif_modelo",
        "votos_esperados", "pct_previsto", "dist_reduto_km"];
      return gm.map((r) => {
        const x = { ...(anMap.get(Number(r.CD_MUNICIPIO)) || {}), ...r };
        for (const c of fill) if (colsAn.has(c) || colsGm.has(c)) x[c] = nn(x[c]) ? x[c] : 0;
        x.reduto_proximo = colsAn.has("reduto_proximo") ? (nn(x.reduto_proximo) ? x.reduto_proximo : "") : "";
        return x;
      });
    }

    const semVotos = (leg, novo) => leg.map(([c, r]) => [c, r === "sem votos" ? novo : r]);
    const mapaExtra = (uid, gmx, metricas, tipFn, aria) => {
      const ps = gmx.map((r, i) => ({ id: polys[i].id, d: polys[i].d, cls: metricas.map((m) => m[3][i]), tip: tipFn(r) }));
      const mm = metricas.map((m) => ({ key: m[0], label: m[1], note: m[2], legend: m[4] }));
      return '<div class="card">' + S.registrar(mapBloco(uid, ps, mm, vb, aria)) + "</div>";
    };

    // ---------------- Sobreposição
    function secSobreposicao(n, titulo) {
      const sob = an.sobreposicao;
      const sv = sumVotos(mun, "votos"), sva = sumVotos(mun, "validos");
      const base = 100 * npSum(mun.map((r) => Math.min(r.votos / sv, r.validos / sva)));
      a(`<h2 id="sobreposicao"><span class="n">${n}</span>${titulo}</h2>`);
      if (sob.length) {
        const alto = sortBy(sob, "sobreposicao", true)[0];
        const baixo = sortBy(sob, "sobreposicao", false)[0];
        const comp = sortBy(sob.filter((r) => nn(r.correlacao)), "correlacao", false);
        let txt = `A distribuição dos votos de <b>${esc(nome)}</b> pelos municípios coincide mais com a de `
          + `<b>${esc(nomePt(alto.nome))}</b> (${esc(pyStr(alto.sigla))}), com ${fnum(alto.sobreposicao, 0)}% de sobreposição, e menos `
          + `com a de ${esc(nomePt(baixo.nome))} (${esc(pyStr(baixo.sigla))}), com ${fnum(baixo.sobreposicao, 0)}%. `
          + `Como referência, só pelo tamanho do eleitorado de cada município a sobreposição esperada seria de ${fnum(base, 0)}%.`;
        if (comp.length) {
          const c0 = comp[0];
          txt += ` A relação mais &quot;complementar&quot; é com ${esc(nomePt(c0.nome))} (${esc(pyStr(c0.sigla))}), `
            + `com correlação de ${fnum(c0.correlacao, 2)}.`;
        }
        const acima = sob.filter((r) => r.sobreposicao > base + 2).length;
        txt += acima ? ` ${acima} de ${sob.length} ficam acima da referência por mais de 2 pontos.`
          : " Nenhum passa da referência por mais de 2 pontos: a sobreposição se explica, em grande parte, só pelo tamanho dos municípios.";
        a(`<p class="lead">${txt}</p>`);
      }
      a(`<div class="prose"><p>Esta seção responde se ${esc(nome)} disputa o mesmo eleitor de outros candidatos ou abriu território próprio. `
        + 'Cada candidato é comparado com ele de três formas:</p><ul>'
        + '<li><b>Sobreposição de base</b>: distribui os votos de cada candidato pelos municípios (cada município com a sua fatia do total) e '
        + 'soma a parte que coincide. 100% é a mesma distribuição; 0% é nenhum município em comum. Quem ganha votos em Porto Alegre '
        + 'naturalmente se sobrepõe a todos, porque lá há muito eleitor; por isso a referência acima mostra o que o tamanho do eleitorado '
        + 'sozinho produziria. Só vale destacar o que passa dela.</li>'
        + '<li><b>Correlação</b>: entre as % de votos válidos dos dois, município a município. Positiva, onde um vai bem o outro também; '
        + 'negativa, os dois se complementam e um é forte onde o outro é fraco.</li>'
        + '<li><b>Moran bivariado</b>: compara a % dele num município com a % do outro nos municípios vizinhos. Positivo, os dois formam manchas '
        + 'nas mesmas regiões. Negativo, onde ele é forte a vizinhança do outro é fraca: territórios diferentes.</li></ul>'
        + '<p>&quot;Resto da federação&quot; soma os votos dos demais candidatos dos partidos da federação dele.</p></div>');
      if (sob.length) {
        const rows = sob.map((r) => ({
          label: Array.from(nomePt(r.nome) + ` (${pyStr(r.sigla)})`).slice(0, 34).join(""), value: Number(r.sobreposicao), fmt: fnum(r.sobreposicao, 0),
          tip: tip(`${nomePt(r.nome)} (${pyStr(r.sigla)})`, [["Sobreposição de base", fnum(r.sobreposicao, 1) + "%"],
            ["Correlação", fnum(r.correlacao, 2)], ["Moran bivariado", fnum(r.moran_bv, 2)], ["Votos", fnum(r.votos)]]),
        }));
        a('<div class="card"><h3>Sobreposição de base (%)</h3><div class="scroll">' + barChart(rows, "Sobreposição")
          + `</div><p style="margin:10px 0 0;font-size:12.5px;color:var(--muted)">Referência pelo tamanho do eleitorado: ${fnum(base, 0)}%.</p></div>`);
        const t = sob.map((r) => ({ ...r, candidato: nomePt(r.nome) + (r.mesma_federacao ? " (federação)" : ""), vs_ref: r.sobreposicao - base }));
        a(tabela(S, t, [["candidato", "Candidato", "t"], ["sigla", "Partido", "t"], ["votos", "Votos", "i"],
          ["sobreposicao", "Sobreposição %", "d1"], ["vs_ref", "Contra a referência (p.p.)", "d1"], ["correlacao", "Correlação", "d2"],
          ["moran_bv", "Moran bivariado", "d2"], ["moran_bv_p", "p do Moran", "d2"]], 30, "tb-sobre"));
      }
    }

    // ---------------- Federação
    function secFederacao(n, titulo, gx) {
      const gmx = gx();
      const f = meta.federacao;
      a(`<h2 id="federacao"><span class="n">${n}</span>${titulo}</h2>`);
      a(`<p class="lead">A federação ${esc(nn(f.nome) ? f.nome : "")} teve ${fnum(f.fed_votos)} votos nominais no estado `
        + `(${fnum(f.fed_pct_estado, 1)}% dos votos válidos). <b>${esc(nome)}</b> ficou com <b>${fnum(f.part_fed_estado, 1)}%</b> deles. `
        + `Em ${f.n_abaixo} municípios ele recebeu menos do que essa participação média indicaria e em ${f.n_acima} recebeu mais.</p>`);
      a(`<div class="prose"><p>${esc(nome)} divide o eleitor da federação com os colegas de chapa. A pergunta aqui é: dado quanto a federação `
        + 'votou em cada município, ele ficou com mais ou menos do que a sua participação média? <b>Participação</b> é a parcela dos votos '
        + 'da federação que foi para ele. <b>Esperado</b> é o que ele teria se tivesse a participação média do estado '
        + `(${fnum(f.part_fed_estado, 1)}%) em cada município. <b>Diferença</b> é esperado menos o que teve: positiva quando ele `
        + 'ficou abaixo.</p><p>Soma da diferença nos municípios em que ele ficou abaixo: '
        + `<b>${fnum(f.votos_a_mais)} votos</b>. Não é uma projeção: esses votos sairiam de colegas de federação, não de adversários. `
        + 'Serve para apontar onde o eleitor do campo existe e a campanha dele não chegou.</p></div>');
      const [cq1, l1a] = classesQuantil(gmx.map((r) => (num(r.fed_votos) > 0 ? r.part_fed : 0)), 6, "%");
      const [cq2, l2] = classesQuantil(gmx.map((r) => r.fed_pct), 6, "%");
      const [cq3, l3a] = classesQuantil(gmx.map((r) => { const x = num(r.dif_fed); return Number.isNaN(x) ? x : Math.max(x, 0); }), 6, "", true);
      const l1 = semVotos(l1a, "sem votos da federação");
      const l3 = semVotos(l3a, "sem diferença");
      const tipF = (r) => tip(nomePt(r.NM_MUNICIPIO), [["Votos dele", fnum(r.votos)], ["Votos da federação", fnum(r.fed_votos)],
        ["Participação dele", fnum(r.part_fed, 1) + "%"], ["Esperado pela participação média", fnum(r.esperado_fed)],
        ["Diferença", fnum(r.dif_fed)]]);
      a(mapaExtra("mapa-fed", gmx, [
        ["part", "Participação dele", "Parcela dos votos da federação no município que foi para ele.", cq1, l1],
        ["fed", "% válidos da federação", "Força da federação no município, sem contar a participação dele.", cq2, l2],
        ["dif", "Votos abaixo do esperado", "Quantos votos a mais ele teria se tivesse a participação média da federação.", cq3, l3],
      ], tipF, "Participação na federação"));
      const topF = sortBy(gmx.filter((r) => num(r.dif_fed) > 0), "dif_fed", true).map((r) => ({ ...r, NM: nomePt(r.NM_MUNICIPIO) }));
      a("<h3>Onde ele ficou mais abaixo do esperado pela federação</h3>");
      a(tabela(S, topF, [["NM", "Município", "t"], ["votos", "Votos dele", "i"], ["fed_votos", "Votos da federação", "i"],
        ["part_fed", "Participação %", "d1"], ["esperado_fed", "Esperado", "i"], ["dif_fed", "Diferença", "i"]], 20, "tb-fed"));
    }

    // ---------------- Modelo
    function secModelo(n, titulo, gx) {
      const gmx = gx();
      const m = meta.modelo;
      const coef = an.modelo;
      a(`<h2 id="modelo"><span class="n">${n}</span>${titulo}</h2>`);
      const moTxt = m.moran_res_p < 0.05
        ? "ainda há um padrão geográfico que o modelo não explica (resíduos com autocorrelação), o que costuma indicar efeitos regionais"
        : "os resíduos não formam manchas, então o modelo capturou o essencial da geografia";
      a(`<p class="lead">Um modelo simples explica ${fnum(100 * m.r2, 0)}% da variação (R² ponderado pelo tamanho dos municípios) da % de votos válidos do ${esc(nome)} entre os `
        + `${m.n} municípios. Os resíduos mostram onde ele vota bem acima ou abaixo do que o modelo prevê: ${m.n_acima} municípios acima e `
        + `${m.n_abaixo} abaixo. Sobre os resíduos, ${moTxt}.</p>`);
      a('<div class="prose"><p><b>O que o modelo faz.</b> Prevê a % de votos válidos dele em cada município a partir de quatro coisas que '
        + 'não dependem da campanha dele: o tamanho do eleitorado, a abstenção, a votação do resto da federação no município e a votação do '
        + 'resto da federação nos vizinhos. Municípios maiores pesam mais na estimativa (ponderação pelos votos válidos). A diferença entre o '
        + 'que ele teve e o que o modelo previu é o <b>resíduo</b>: positivo, ele foi melhor do que o contexto indica; negativo, pior.</p>'
        + '<p><b>Como usar.</b> Resíduo muito positivo sugere liderança local, campanha forte ou voto de nicho: vale entender e replicar. '
        + 'Resíduo muito negativo, em município onde a federação vai bem, é o lugar onde mais falta: o contexto favorece e o voto não veio. '
        + 'É um retrato do que aconteceu, não uma explicação causal. Variáveis que não entraram (renda, escolaridade, religião, '
        + 'visitas de campanha) ficam nos resíduos.</p></div>');
      const ct = coef.filter((r) => r.variavel !== "const");
      const fr = [];
      for (const r of ct) {
        if (num(r.p) < 0.05) {
          const sinal = r.efeito_1dp > 0 ? "mais" : "menos";
          fr.push(`${String(r.rotulo).toLowerCase()}: 1 desvio-padrão acima da média está associado a ${fnum(Math.abs(r.efeito_1dp), 2)} ponto(s) `
            + `percentual(is) ${sinal} de votos válidos`);
        }
      }
      if (fr.length) a('<div class="callout"><b>Efeitos estatisticamente significativos (p &lt; 0,05):</b> ' + fr.join("; ") + ".</div>");
      else a('<div class="callout">Nenhuma das variáveis tem efeito estatisticamente significativo isolado.</div>');
      const fedP = ct.filter((r) => ["fed_outros_pct", "fed_viz_pct"].includes(r.variavel)).map((r) => num(r.p));
      if (fedP.length && fedP.every((p) => p >= 0.05)) {
        a('<div class="callout">A votação do resto da federação, no município e nos vizinhos, não acrescenta poder de explicação depois de '
          + 'considerado o tamanho do município. Ou seja, o voto dele não acompanha a força da federação: ele vai bem e mal em lugares '
          + 'diferentes dos colegas de chapa.</div>');
      }
      a('<div style="margin-bottom:16px">' + tabela(S, ct, [["rotulo", "Variável", "t"], ["efeito_1dp", "Efeito de +1 desvio-padrão (p.p.)", "d2"],
        ["t", "t (erro robusto)", "d2"], ["p", "p", "d2"]], 10, "tb-modelo") + "</div>");
      const z = gmx.map((r) => num(r.z_residuo));
      const cat = z.map((x) => (x > 2 ? "Acima do esperado" : x < -2 ? "Abaixo do esperado" : "Dentro do esperado"));
      const [ccat, lcat] = classesCategoria(cat, { "Acima do esperado": "hh", "Abaixo do esperado": "ll", "Dentro do esperado": "ns" },
        ["Acima do esperado", "Abaixo do esperado", "Dentro do esperado"]);
      const [cq4, l4] = classesQuantil(gmx.map((r) => { const x = num(r.pct_previsto); return Number.isNaN(x) ? x : Math.max(x, 0); }), 6, "%");
      const tipM = (r) => tip(nomePt(r.NM_MUNICIPIO), [["% válidos dele", fnum(r.pct_validos, 2) + "%"],
        ["% previsto pelo modelo", fnum(r.pct_previsto, 2) + "%"], ["Votos dele", fnum(r.votos)],
        ["Votos esperados", fnum(r.votos_esperados)], ["Diferença em votos", fnum(r.dif_modelo)]]);
      a(mapaExtra("mapa-modelo", gmx, [
        ["res", "Resíduo", "Vermelho: ele vai melhor que o previsto. Azul: pior. Só destaca desvios acima de 2 desvios-padrão.", ccat, lcat],
        ["prev", "% previsto", "O que o modelo previu para cada município.", cq4, l4],
      ], tipM, "Resíduos do modelo"));
      const g2 = gmx.map((r) => ({ ...r, NM: nomePt(r.NM_MUNICIPIO) }));
      const pos = sortBy(g2.filter((r) => num(r.z_residuo) > 0), "dif_modelo", true);
      const neg = sortBy(g2.filter((r) => num(r.z_residuo) < 0), "dif_modelo", false);
      const colsM = [["NM", "Município", "t"], ["votos", "Votos", "i"], ["votos_esperados", "Votos esperados", "i"],
        ["dif_modelo", "Diferença", "i"], ["z_residuo", "Resíduo padronizado", "d2"]];
      a("<h3>Onde foi mais acima do esperado (em votos)</h3>");
      a(tabela(S, pos, colsM, 15, "tb-mod-pos"));
      a("<h3>Onde ficou mais abaixo do esperado (em votos)</h3>");
      a(tabela(S, neg, colsM, 15, "tb-mod-neg"));
    }

    // ---------------- Distância
    function secDistancia(n, titulo, gx) {
      const gmx = gx();
      const dm = meta.distancia;
      a(`<h2 id="distancia"><span class="n">${n}</span>${titulo}</h2>`);
      const sinal = dm.spearman < -0.1 ? "cai" : dm.spearman > 0.1 ? "sobe" : "quase não muda";
      a(`<p class="lead">${fnum(dm.votos_ate_100, 0)}% dos votos dele vêm de municípios a até 100 km do reduto mais próximo e `
        + `${fnum(dm.votos_ate_200, 0)}% a até 200 km. Fora dos redutos, a % de votos válidos ${sinal} com a distância `
        + `(correlação de Spearman ${fnum(dm.spearman, 2)}, descritiva).</p>`);
      a('<div class="prose"><p><b>Como foi calculado.</b> Os redutos são os ' + String(dm.k) + ' municípios onde ele mais votou: '
        + esc(arr(dm.redutos).map((x) => nomePt(x)).join(", ")) + '. Para cada município mede-se a distância em linha reta, entre os centros dos '
        + 'municípios, até o reduto mais próximo. Os municípios são agrupados em faixas de distância e, em cada faixa, calcula-se a % de votos '
        + 'válidos que ele teve (votos dele ÷ votos válidos de todos os municípios da faixa).</p>'
        + '<p><b>Como ler.</b> Se a % cai de forma regular com a distância, o voto &quot;irradia&quot; dos redutos e a campanha pode crescer pelas '
        + 'bordas. Se ela se mantém ou aparece em manchas longe dos redutos, o voto vem de redes próprias (lideranças, categorias) que não '
        + 'dependem da proximidade e exigem outra estratégia. A distância em linha reta não considera estradas nem a rede urbana.</p></div>');
      const ba = an.bandas.filter((r) => num(r.municipios) > 0).map((r) => ({ ...r, rotulo: String(r.faixa) }));
      const rows = ba.map((r) => ({
        label: r.rotulo, value: nn(r.pct_validos) ? Number(r.pct_validos) : 0.0,
        fmt: nn(r.pct_validos) ? fnum(r.pct_validos, 2) + "%" : "–",
        tip: tip(r.rotulo, [["Municípios", fnum(r.municipios)], ["Votos dele", fnum(r.votos)],
          ["% dos votos dele", fnum(r.share_votos, 1) + "%"],
          ["% dos votos válidos", nn(r.pct_validos) ? fnum(r.pct_validos, 2) + "%" : ""]]),
      }));
      a('<div class="card"><h3>% dos votos válidos por distância do reduto mais próximo</h3><div class="scroll">'
        + barChart(rows, "Votação por faixa de distância") + "</div></div>");
      a(tabela(S, ba, [["rotulo", "Faixa de distância", "t"], ["municipios", "Municípios", "i"], ["votos", "Votos", "i"],
        ["share_votos", "% dos votos dele", "d1"], ["pct_validos", "% válidos", "d2"]], 10, "tb-dist"));
      const [cd, ld0] = classesQuantil(gmx.map((r) => r.dist_reduto_km), 6, " km");
      const ld = semVotos(ld0, "reduto");
      const tipD = (r) => tip(nomePt(r.NM_MUNICIPIO), [["Distância ao reduto mais próximo", fnum(r.dist_reduto_km, 0) + " km"],
        ["Reduto mais próximo", r.reduto_proximo ? nomePt(r.reduto_proximo) : ""],
        ["% válidos dele", fnum(r.pct_validos, 2) + "%"], ["Votos", fnum(r.votos)]]);
      a(mapaExtra("mapa-dist", gmx, [["dist", "Distância", "Distância em linha reta ao reduto mais próximo.", cd, ld]], tipD, "Distância dos redutos"));
    }
    let gmx = null;
    const getGmx = () => (gmx = gmx || montarGmx());
    for (const [id, titulo, existe, dadosOk, fn] of ordem) {
      if (!existe()) continue;
      const n = nxt();
      if (pend.has(id) || !dadosOk()) { S.semNota.add(id); a(calc(id, n, titulo)); continue; }
      if (estrito) { fn(n, titulo, getGmx); continue; }
      const nP = partes.length, nB = S.blk.length, nU = S.usadas.length;
      try { fn(n, titulo, getGmx); } catch (e) {
        partes.length = nP; S.blk.length = nB; S.usadas.length = nU;
        S.semNota.add(id); a(calc(id, n, titulo));
      }
    }
  }
}

function sumVotos(rows, k) { let s = 0; for (const r of rows) s += Number(r[k]); return s; }

// ------------------------------------------------------------------ painel de cidade
function cidade(S, ci, c) {
  const out = [];
  const a = (s) => out.push(s);
  a('<section class="pane cpanel">');
  a(`<h3 class="cn">${esc(c.nome)}</h3>`);
  const locais = arr(c.locais);
  const loc = sortBy(locais, "votos", true);
  const nomesReais = !loc.every((l) => String(l.local_nome).startsWith("Local "));
  const zonas = arr(c.zonas);
  let mini = `<span><b>${fnum(c.votos)}</b>votos</span><span><b>${fnum(c.pct, 2)}%</b>dos votos válidos</span>`
    + `<span><b>${zonas.length}</b>zona(s) eleitoral(is)</span>`;
  if (nomesReais) mini += `<span><b>${c.n_locais}</b>locais de votação</span>`;
  mini += `<span><b>${fnum(c.eleitores)}</b>eleitores aptos</span>`;
  a(`<div class="mini">${mini}</div>`);

  const abas = [];
  if (zonas.length) {
    const cz = [["NR_ZONA", "Zona", "i"]];
    if (nomesReais) cz.push(["locais", "Locais", "i"]);
    cz.push(["votos", "Votos", "ib"], ["pct_validos", "% válidos", "d2"], ["eleitores", "Eleitores aptos", "i"],
      ["share_votos_cidade", "% dos votos da cidade", "d1"]);
    abas.push(["Zonas eleitorais", tabela(S, zonas, cz, 30, `tb-z${ci}`)]);
  }
  const bai = arr(c.bairros);
  if (bai.some((b) => b.bairro !== "(sem bairro)")) {
    abas.push(["Bairros", tabela(S, bai, [["bairro", "Bairro", "t"], ["locais", "Locais", "i"], ["votos", "Votos", "i"],
      ["pct_validos", "% válidos", "d2"], ["share_votos_cidade", "% dos votos da cidade", "d1"]], 60, `tb-b${ci}`)]);
  }
  if (nomesReais) {
    const cols = [["local_nome", "Local de votação", "t"]];
    if (loc.some((l) => l.bairro !== "(sem bairro)")) cols.push(["bairro", "Bairro", "t"]);
    cols.push(["NR_ZONA", "Zona", "i"], ["votos", "Votos", "i"], ["pct_validos", "% válidos", "d2"],
      ["eleitores", "Eleitores", "i"], ["votos_por_100_aptos", "Votos/100 aptos", "d2"]);
    abas.push(["Locais de votação", tabela(S, loc, cols, 60, `tb-l${ci}`)]);
  }
  if (abas.length === 1) {
    a(abas[0][1]);
  } else {
    a('<div class="tabset"><div class="tablist" role="tablist">'
      + abas.map(([r]) => `<button type="button" role="tab">${esc(r)}</button>`).join("") + "</div>");
    for (const [, h] of abas) a(`<div class="pane">${h}</div>`);
    a("</div>");
  }
  a("</section>");
  return out.join("");
}

// ------------------------------------------------------------------ painel de detalhes
function detalhes(ctx, gm, temAn, an, colsMun) {
  const anRows = temAn && Array.isArray(an.mun) ? an.mun : [];
  const anMap = new Map(anRows.map((r) => [Number(r.CD_MUNICIPIO), r]));
  const colsG = new Set([...colunas(gm), ...colunas(anRows)]);
  const campos = [["Votos", "v", "i", "votos"], ["% dos votos válidos", "pv", "p2", "pct_validos"],
    ["Votos por 100 eleitores aptos", "v100", "d2", "votos_por_100_aptos"],
    ["Quociente locacional", "ql", "d2", "quociente_locacional"],
    ["Posição do candidato aqui", "pos", "pos", "posicao_no_municipio"],
    ["Mais votado no município", "lid", "t", "lider_nome"],
    ["Colega de partido mais votado", "col", "t", "colega_nome"],
    ["Eleitores aptos", "el", "i", "eleitores"],
    ["Abstenção", "ab", "p1", "abstencao_pct"], ["Brancos e nulos", "bn", "p1", "brancos_nulos_pct"],
    ["Votos até a média do estado", "pot", "i", "votos_ate_media_estadual"],
    ["Vizinhança (LISA)", "lisa", "t", "lisa_cluster"], ["Leitura da vizinhança", "lisad", "t", "lisa_detalhe"],
    ["Esperado pela federação (votos)", "esp", "i", "esperado_fed"],
    ["Diferença para o esperado da federação", "dif", "s", "dif_fed"],
    ["% prevista pelo modelo", "prev", "p2", "pct_previsto"],
    ["Resíduo do modelo (desvios)", "z", "d1", "z_residuo"],
    ["Distância ao reduto mais próximo", "dist", "km", "dist_reduto_km"],
    ["Reduto mais próximo", "red", "t", "reduto_proximo"]].filter((c) => colsG.has(c[3]) || colsMun.has(c[3]));
  const nomesCols = new Set(["lider_nome", "colega_nome", "reduto_proximo"]);
  const out = {};
  for (const r0 of gm) {
    const cd0 = r0.CD_MUNICIPIO;
    if (!nn(cd0)) continue;
    const cd = trunc(cd0);
    const r = { ...(anMap.get(cd) || {}), ...r0 };
    const m = { n: nomePt(r.NM_MUNICIPIO || r.nm_ibge) };
    for (const [, k, , col] of campos) {
      let v = r[col];
      if (v === null || v === undefined || (typeof v !== "string" && !nn(v))) continue;
      if (nomesCols.has(col) && typeof v === "string") v = nomePt(v);
      if (col === "lisa_cluster" && v === "Não significativo") v = "Sem padrão significativo";
      m[k] = typeof v === "string" ? v : pyRound(Number(v), 4);
    }
    if (m.v === 0) delete m.pos;
    out[cd] = m;
  }
  const top = {};
  const tm = arr(ctx.top_mun);
  if (tm.length) {
    const foco = trunc(ctx.info.numero);
    for (const r of tm) {
      const cd = trunc(r.CD_MUNICIPIO);
      (top[cd] = top[cd] || []).push([trunc(r.posicao), nomePt(r.nome), pyStr(r.sigla), trunc(r.votos),
        nn(r.pct) ? pyRound(Number(r.pct), 2) : 0, trunc(r.numero) === foco]);
    }
  }
  return { fields: campos.map((c) => [c[0], c[1], c[2]]), mun: out, top };
}

// ------------------------------------------------------------------ site.py
/** Dicas dos mapas: rótulos comuns numa tabela por mapa; título igual ao nome do município vira 0. */
export function compactar(blocos, det) {
  const mun = (det && det.mun) || {};
  return arr(blocos).map((b) => {
    if (b.t !== "map" || "tl" in b) return b;
    const tl = [], tp = {};
    for (const [cd, [tit, linhas]] of Object.entries(b.tp)) {
      const rs = [];
      for (const [k, v] of linhas) {
        let i = tl.indexOf(k);
        if (i < 0) { tl.push(k); i = tl.length - 1; }
        rs.push([i, v]);
      }
      const nome = (mun[cd] || {}).n;
      tp[cd] = [tit === nome ? 0 : tit, rs];
    }
    return { ...b, tp, tl };
  });
}

/** P = {t, h, b, d, gs, m}: o objeto que app.js consome em desenhar(P, P.gs). */
export function paginaP(pag, malha) {
  let gs = pag.geo;
  if (!gs && malha) {
    gs = geoDefs(arr(malha.municipios).map((m) => ({ id: Number(m.cod), d: m.d })));
  }
  return {
    t: pag.titulo, h: pag.corpo, b: compactar(pag.blocos, pag.det), d: pag.det, gs: gs || "",
    m: { ano: trunc(pag.ano), uf: pag.uf, cargo: pag.cargo_cod, numero: trunc(pag.numero), nome: pag.nome, cargo_nome: pag.cargo, votos: trunc(pag.votos) },
  };
}
