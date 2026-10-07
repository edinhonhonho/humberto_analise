// Porte de eleicao/partidos.py (partido_de) e das constantes de eleicao/metrics.py (SIGLAS) e eleicao/analises.py (FEDERACOES_2026).

// Número do partido (2 dígitos) a partir do número do candidato: presidente/governador 2 dígitos,
// senador 3, deputado federal 4, estadual 5; voto de legenda também tem 2 dígitos.
export function partidoDe(n) {
  n = Math.trunc(n);
  if (n < 100) return n;
  if (n < 1000) return Math.floor(n / 10);
  if (n < 10000) return Math.floor(n / 100);
  if (n < 100000) return Math.floor(n / 1000);
  let d = 1, t = n;
  while (t >= 10) { t = Math.floor(t / 10); d++; }
  return Math.floor(n / 10 ** (d - 2));
}

export const SIGLAS = {
  10: "REPUBLICANOS", 11: "PP", 12: "PDT", 13: "PT", 14: "MISSÃO", 15: "MDB", 16: "PSTU", 18: "REDE",
  20: "PODE", 22: "PL", 23: "CIDADANIA", 30: "NOVO", 35: "DEMOCRATA", 40: "PSB", 43: "PV",
  44: "UNIÃO", 45: "PSDB", 50: "PSOL", 55: "PSD", 65: "PCDOB", 80: "UP",
};

// Federações partidárias de 2026 (número do partido -> números dos partidos da federação).
export const FEDERACOES_2026 = {
  13: [13, 43, 65], 43: [13, 43, 65], 65: [13, 43, 65],   // Brasil da Esperança (PT, PV, PCdoB)
  23: [23, 45], 45: [23, 45],                              // PSDB Cidadania
  18: [18, 50], 50: [18, 50],                              // PSOL Rede
  11: [11, 44], 44: [11, 44],                              // União Progressista (PP, União)
  25: [25, 77], 77: [25, 77],                              // Renovação Solidária (PRD, Solidariedade)
};

// Números dos partidos da federação do candidato (ou só o do próprio partido). `texto` = "13,43,65" (opcional).
export function partidosFederacao(numero, texto) {
  if (texto) return String(texto).replace(/;/g, ",").split(",").filter((x) => x.trim()).map((x) => parseInt(x, 10));
  const p = partidoDe(numero);
  return FEDERACOES_2026[p] ? [...FEDERACOES_2026[p]] : [p];
}
