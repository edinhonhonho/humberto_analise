// Web Worker: calcula a análise de um candidato em etapas e devolve a página pronta (objeto P) a cada etapa.
// Mensagem de entrada:  {tipo:"calcular", id, base, ano, uf, cargo, turno, numero}
// Mensagens de saída:   {tipo:"etapa", id, etapa:1|2|3, final:bool, P}  |  {tipo:"erro", id, msg}
import { UF, fonteUrl } from "./dados.js";
import { etapa1, etapa2, etapa3 } from "./calc.js";
import { montar, paginaP } from "./report.js";

const ufs = new Map();
const PEND = {
  1: ["vizinhanca", "sobreposicao", "modelo", "distancia"],
  2: ["sobreposicao", "modelo", "distancia"],
  3: [],
};

function uf(base, ano, sigla) {
  const k = `${base}|${ano}|${sigla}`;
  if (!ufs.has(k)) ufs.set(k, new UF(fonteUrl(`${base}/${ano}/${sigla}`), sigla, ano));
  return ufs.get(k);
}

async function calcular(m) {
  const t0 = performance.now();
  const u = uf(m.base, m.ano, m.uf);
  const entrada = await u.entrada(m.turno, m.cargo, m.numero);
  const t1 = performance.now();
  const malha = entrada.malha;
  const enviar = (etapa, ctx) => {
    const P = paginaP(montar(ctx, malha, { pendentes: PEND[etapa] }), malha);
    P.m.tempos = { dados: Math.round(t1 - t0), total: Math.round(performance.now() - t0), etapa };
    self.postMessage({ tipo: "etapa", id: m.id, etapa, final: etapa === 3, P });
  };
  const opc = { topCidades: 10, permutacoes: 999, permComp: 199 };
  let ctx = etapa1(entrada, opc);
  enviar(1, ctx);
  await new Promise((r) => setTimeout(r, 0));
  ctx = etapa2(entrada, ctx, opc);
  enviar(2, ctx);
  await new Promise((r) => setTimeout(r, 0));
  ctx = etapa3(entrada, ctx, opc);
  enviar(3, ctx);
}

self.onmessage = async (e) => {
  const m = e.data;
  try {
    if (m.tipo === "calcular") await calcular(m);
    else if (m.tipo === "aquecer") { await uf(m.base, m.ano, m.uf).entrada(m.turno, m.cargo, m.numero); }
  } catch (err) {
    self.postMessage({ tipo: "erro", id: m.id, msg: String((err && err.message) || err) });
  }
};
