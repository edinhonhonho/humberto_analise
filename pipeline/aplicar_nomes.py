"""Coloca nos pacotes de análise já prontos (saida_*_lote/*/bundle) os nomes que estavam como 'CANDIDATO 12345'.

Usa dados/candidatos_<ano>_<UF>_c<cargo>.csv (veja baixar_nomes.py --consulta). Não recalcula nada: troca só o
texto. Pode rodar mais de uma vez. Depois: python rodar.py --relatorio  (refaz as páginas) e --indice.
Uso:  python aplicar_nomes.py [pasta_dados] [pasta_saida_lote ...]
"""
import csv
import io
import json
import re
import sys
from pathlib import Path

import pandas as pd

from eleicao import tse_io

pasta = Path(sys.argv[1] if len(sys.argv) > 1 else "dados")
lotes = [Path(p) for p in sys.argv[2:]] or sorted(Path(".").glob("saida_*_lote"))
RE = re.compile(r"^(?:CANDIDATO )?(\d+)$", re.I)   # nos boletins o nome vem vazio: só o número ou 'CANDIDATO 12345'
listas: dict = {}


def nomes(ano, uf, cargo):
    k = (ano, uf, cargo)
    if k not in listas:
        arq = pasta / f"candidatos_{ano}_{uf}_c{cargo}.csv"
        d = tse_io.load_candidatos(arq, None, log=lambda *_: None) if arq.exists() else None
        listas[k] = {} if d is None else {int(n): s for n, s in zip(d["numero"], d["nome"]) if s.strip() not in ("", "nan")}
    return listas[k]


def troca(v, nm):
    if isinstance(v, str):
        m = RE.match(v.strip())
        if m and int(m.group(1)) in nm:
            return nm[int(m.group(1))].upper()
    return v


def json_troca(o, nm):
    if isinstance(o, dict):
        return {k: json_troca(v, nm) for k, v in o.items()}
    if isinstance(o, list):
        return [json_troca(v, nm) for v in o]
    return troca(o, nm)


def processa(b):
    meta = json.loads((b / "meta.json").read_text(encoding="utf-8"))
    info = meta.get("info") or meta
    uf, cargo, ano = info.get("uf"), info.get("cargo"), info.get("ano") or meta.get("ano")
    if not uf:
        m = re.match(r"([A-Z]{2})_", b.parent.name)
        uf = m and m.group(1)
    nm = nomes(ano or 2026, uf, cargo)
    if not nm:
        return None
    mudou = False
    for arq in list(b.rglob("*.csv")) + [b / "meta.json"]:
        txt = arq.read_text(encoding="utf-8")
        if arq.suffix == ".json":
            novo = txt
            if '"nome"' in txt:   # só o campo nome (não números soltos)
                dados = json.loads(txt)
                if isinstance(dados.get("info"), dict):
                    dados["info"]["nome"] = troca(dados["info"].get("nome"), nm)
                novo = json.dumps(dados, ensure_ascii=False)
        else:
            linhas = list(csv.reader(io.StringIO(txt, newline="")))
            if not linhas:
                continue
            cols = [i for i, h in enumerate(linhas[0]) if h.strip().lower() in ("nome", "nm_votavel")]
            if not cols:
                continue
            out = io.StringIO()
            w = csv.writer(out, lineterminator="\n")
            w.writerow(linhas[0])
            for r in linhas[1:]:
                for i in cols:
                    if i < len(r):
                        r[i] = troca(r[i], nm)
                w.writerow(r)
            novo = out.getvalue()
        if novo != txt:
            arq.write_text(novo, encoding="utf-8", newline="")
            mudou = True
    return mudou


bundles = [b for lote in lotes for b in sorted(lote.glob("*/bundle"))]
for b in bundles:   # carrega as listas antes (evita corrida entre threads)
    pass
from concurrent.futures import ThreadPoolExecutor
for uf in ("RS", "RJ", "PE"):
    for c in (3, 5, 6, 7):
        nomes(2026, uf, c)
with ThreadPoolExecutor(24) as ex:   # pasta em disco de rede/VM: o gargalo é a espera por arquivo, não a CPU
    res = list(ex.map(processa, bundles))
print(f"{sum(r is not None for r in res)} pacotes verificados, {sum(bool(r) for r in res)} atualizados.")
