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
RE = re.compile(r"^CANDIDATO (\d+)$", re.I)
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


total = ajust = 0
for lote in lotes:
    for b in sorted(lote.glob("*/bundle")):
        meta = json.loads((b / "meta.json").read_text(encoding="utf-8"))
        info = meta.get("info") or meta
        uf, cargo, ano = info.get("uf"), info.get("cargo"), info.get("ano") or meta.get("ano")
        if not (uf and cargo and ano):
            m = re.match(r"([A-Z]{2})_", b.parent.name)
            uf = uf or (m and m.group(1))
        nm = nomes(ano or 2026, uf, cargo)
        if not nm:
            continue
        total += 1
        mudou = False
        for arq in list(b.rglob("*.csv")) + [b / "meta.json"]:
            txt = arq.read_text(encoding="utf-8")
            if "CANDIDATO " not in txt.upper():
                continue
            if arq.suffix == ".json":
                novo = json.dumps(json_troca(json.loads(txt), nm), ensure_ascii=False)
            else:
                linhas = list(csv.reader(io.StringIO(txt, newline="")))
                out = io.StringIO()
                w = csv.writer(out, lineterminator="\n")
                for r in linhas:
                    w.writerow([troca(c, nm) for c in r])
                novo = out.getvalue()
            if novo != txt:
                arq.write_text(novo, encoding="utf-8", newline="")
                mudou = True
        ajust += mudou
print(f"{total} pacotes verificados, {ajust} atualizados.")
