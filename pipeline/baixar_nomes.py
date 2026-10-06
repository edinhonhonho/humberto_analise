"""Baixa a lista de candidatos (nome, partido, votos) de Governador (3) e Senador (5) de cada UF.

O código da eleição desses cargos não é o mesmo em todos os pleitos; o script testa os códigos mais
prováveis até um responder. Uso:  python baixar_nomes.py --uf RS,RJ,PE
Grava dados/candidatos_<ano>_<UF>_c<cargo>.csv (o rodar.py usa esses arquivos sozinho).
"""
import argparse
import contextlib
import io
import sys
from pathlib import Path

import baixar_bu

ap = argparse.ArgumentParser()
ap.add_argument("--uf", default="RS,RJ,PE")
ap.add_argument("--ano", type=int, default=2026)
ap.add_argument("--cargos", default="3,5")
ap.add_argument("--pasta", default="dados")
ap.add_argument("--eleicoes", default="6259,6258,6260,6257,6261,6256,6262,6255,6263,6254,6264,6253,6252,6265,6266")
a = ap.parse_args()
pasta = Path(a.pasta)
pasta.mkdir(exist_ok=True)
codigos = [int(x) for x in a.eleicoes.split(",")]
falhou = False
for uf in [u.strip().upper() for u in a.uf.split(",") if u.strip()]:
    for cargo in [int(x) for x in a.cargos.split(",")]:
        alvo = pasta / f"candidatos_{a.ano}_{uf}_c{cargo}.csv"
        ok = False
        for e in codigos:
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                r = baixar_bu.baixar_candidatos(baixar_bu.BASE, a.ano, uf, e, cargo, pasta)
            if r:
                r.replace(alvo)
                print(f"{uf}, cargo {cargo}: ok (eleição {e}) -> {alvo.name}  {buf.getvalue().strip().splitlines()[-1] if buf.getvalue().strip() else ''}")
                ok = True
                break
        if not ok:
            falhou = True
            print(f"{uf}, cargo {cargo}: nenhum código de eleição respondeu ({codigos[0]}..{codigos[-1]}).")
sys.exit(1 if falhou else 0)
