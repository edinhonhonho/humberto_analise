// Acesso aos dados por UF (Parquet + JSON). Funciona no Node (testes) e no navegador (Worker).
// `fonte` = { arquivo(nome) -> AsyncBuffer (Parquet), json(nome) -> objeto }.
import { parquetMetadataAsync, parquetReadObjects } from "hyparquet";

export function colunas(linhas, nomes) {
  const o = {};
  for (const n of nomes) o[n] = new Array(linhas.length);
  linhas.forEach((r, i) => { for (const n of nomes) o[n][i] = r[n]; });
  o.n = linhas.length;
  return o;
}

const num = (x) => (typeof x === "bigint" ? Number(x) : x);

export class UF {
  constructor(fonte, sigla, ano = 2026) {
    this.fonte = fonte; this.uf = sigla; this.ano = ano; this._meta = {}; this._buf = {};
  }
  async _abrir(nome) {
    if (!this._buf[nome]) {
      const file = await this.fonte.arquivo(nome);
      this._buf[nome] = { file, metadata: await parquetMetadataAsync(file) };
    }
    return this._buf[nome];
  }
  async json(nome) { return this.fonte.json(nome); }

  // lê as linhas do arquivo cujas colunas-chave (ordenadas: turno, cargo, votavel) casam com `filtro`
  async _ler(nome, cols, filtro) {
    const { file, metadata } = await this._abrir(nome);
    const esq = metadata.schema.slice(1).map((s) => s.name);
    let ini = null, fim = 0, acc = 0;
    for (const rg of metadata.row_groups) {
      const n = Number(rg.num_rows);
      let ok = true;
      for (const [col, v] of Object.entries(filtro)) {
        const st = rg.columns[esq.indexOf(col)]?.meta_data?.statistics;
        if (st && st.min_value != null && st.max_value != null && (v < num(st.min_value) || v > num(st.max_value))) { ok = false; break; }
      }
      if (ok) { if (ini === null) ini = acc; fim = acc + n; }
      acc += n;
    }
    if (ini === null) return colunas([], cols);
    const todas = [...new Set([...cols, ...Object.keys(filtro)])];
    let linhas = await parquetReadObjects({ file, metadata, columns: todas, rowStart: ini, rowEnd: fim });
    linhas = linhas.filter((r) => Object.entries(filtro).every(([k, v]) => num(r[k]) === v));
    linhas.forEach((r) => { for (const k of todas) r[k] = num(r[k]); });
    return colunas(linhas, cols);
  }
  // votos do candidato por seção: {mun, zona, secao, loc, votos}
  votosCandidato(turno, cargo, numero) {
    return this._ler("votos.parquet", ["mun", "zona", "secao", "loc", "votos"], { turno, cargo, votavel: numero });
  }
  // uma linha por seção do cargo: {mun, zona, secao, loc, aptos, validos, brancos, nulos, total}
  secoes(turno, cargo) {
    return this._ler("secoes.parquet", ["mun", "zona", "secao", "loc", "aptos", "validos", "brancos", "nulos", "total"], { turno, cargo });
  }
  // votos por município de cada votável (candidatos e legenda, sem brancos e nulos): {votavel, mun, votos}
  mc(turno, cargo) {
    return this._ler("mc.parquet", ["votavel", "mun", "votos"], { turno, cargo });
  }
  // tudo o que `calcular` precisa para um candidato
  async entrada(turno, cargo, numero) {
    const [malha, nomes, meta] = await Promise.all([this.json("malha.json"), this.json("nomes.json"), this.json("meta.json")]);
    const [votosCand, secoes, mc] = await Promise.all([this.votosCandidato(turno, cargo, numero), this.secoes(turno, cargo), this.mc(turno, cargo)]);
    return { ano: this.ano, uf: this.uf, cargo, turno, numero, malha, nomes: nomes[String(cargo)] || {},
             munNomes: meta.municipios, votosCand, secoes, mc };
  }
}

// fonte para o Node: pasta no disco
export async function fonteDisco(pasta) {
  const fs = await import("node:fs/promises");
  const { asyncBufferFromFile } = await import("hyparquet");
  return {
    arquivo: (n) => asyncBufferFromFile(`${pasta}/${n}`),
    json: async (n) => JSON.parse(await fs.readFile(`${pasta}/${n}`, "utf-8")),
  };
}
// fonte para o navegador: URL base
export function fonteUrl(base) {
  return {
    arquivo: async (n) => {
      const { asyncBufferFromUrl, cachedAsyncBuffer } = await import("hyparquet");
      return cachedAsyncBuffer(await asyncBufferFromUrl({ url: `${base}/${n}` }));
    },
    json: async (n) => (await fetch(`${base}/${n}`)).json(),
  };
}
