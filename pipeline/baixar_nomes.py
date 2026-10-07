"""Baixa a lista de candidatos (nome, partido, votos) de Governador (3) e Senador (5) de cada UF.

Para completar os nomes de TODOS os cargos (inclusive Deputado Estadual, que não tem lista de resultados, e
os números de federal que ficaram de fora), use a lista de registro de candidaturas do TSE:
    python baixar_nomes.py --consulta                 (baixa o consulta_cand_2026.zip do TSE)
    python baixar_nomes.py --consulta arquivo.zip     (usa um zip já baixado)
Ela cria/completa dados/candidatos_2026_<UF>_c<cargo>.csv para os cargos 3, 5, 6 e 7. Depois rode
python aplicar_nomes.py para colocar os nomes nas análises já prontas.

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
ap.add_argument("--consulta", nargs="?", const="baixar", default=None,
                help="usa o consulta_cand do TSE (zip local ou, sem valor, baixa o arquivo)")
ap.add_argument("--eleicoes", default="6259,6258,6260,6257,6261,6256,6262,6255,6263,6254,6264,6253,6252,6265,6266")
a = ap.parse_args()
pasta = Path(a.pasta)
pasta.mkdir(exist_ok=True)


def consulta():
    import csv
    import zipfile

    import pandas as pd
    zp = a.consulta
    if zp == "baixar":
        zp = pasta / f"consulta_cand_{a.ano}.zip"
        if not zp.exists():
            urls = [f"https://cdn.tse.net.br/estatistica/sead/odsele/consulta_cand/consulta_cand_{a.ano}.zip",
                    f"https://cdn.tse.net.br/estatistica/sead/odsele/consulta_cand/consulta_cand_{a.ano}_BR.zip"]
            for u in urls:
                try:
                    print("baixando", u, "(pode levar alguns minutos)")
                    zp.write_bytes(baixar_bu.get(u, timeout=600))
                    break
                except Exception as e:  # noqa: BLE001
                    print("  falhou:", e)
            if not zp.exists():
                sys.exit("Não consegui baixar. Baixe o 'Candidatos 2026' em dadosabertos.tse.jus.br e rode: "
                         "python baixar_nomes.py --consulta caminho\\do\\arquivo.zip")
    zp = Path(zp)
    ufs = [u.strip().upper() for u in a.uf.split(",") if u.strip()]
    with zipfile.ZipFile(zp) as z:
        for uf in ufs:
            nm = next((n for n in z.namelist() if n.upper().endswith(f"_{uf}.CSV")), None)
            if nm is None:
                print(f"{uf}: arquivo da UF não encontrado no zip.")
                continue
            df = pd.read_csv(z.open(nm), sep=";", encoding="latin-1", dtype=str)
            df.columns = [c.strip().upper() for c in df.columns]
            for cargo in (3, 5, 6, 7, 8):
                d = df[df["CD_CARGO"].astype(str) == str(cargo)]
                if d.empty:
                    continue
                alvo = pasta / f"candidatos_{a.ano}_{uf}_c{cargo}.csv"
                antigo = {}
                if alvo.exists():
                    with alvo.open(encoding="utf-8", newline="") as fi:
                        for r in csv.DictReader(fi, delimiter=";"):
                            antigo[str(r["NR_CANDIDATO"]).strip()] = r
                novos = 0
                for _, r in d.iterrows():
                    n = str(r["NR_CANDIDATO"]).strip()
                    if n in antigo and str(antigo[n].get("NM_URNA_CANDIDATO", "")).strip():
                        continue
                    novos += n not in antigo
                    antigo[n] = {"NR_CANDIDATO": n, "NM_URNA_CANDIDATO": str(r.get("NM_URNA_CANDIDATO", "")).strip(),
                                 "NM_CANDIDATO": str(r.get("NM_CANDIDATO", "")).strip(),
                                 "SG_PARTIDO": str(r.get("SG_PARTIDO", "")).strip(), "FEDERACAO": "",
                                 "DS_SIT_TOT_TURNO": antigo.get(n, {}).get("DS_SIT_TOT_TURNO", ""),
                                 "QT_VOTOS_OFICIAL": antigo.get(n, {}).get("QT_VOTOS_OFICIAL", "")}
                cols = ["NR_CANDIDATO", "NM_URNA_CANDIDATO", "NM_CANDIDATO", "SG_PARTIDO", "FEDERACAO",
                        "DS_SIT_TOT_TURNO", "QT_VOTOS_OFICIAL"]
                with alvo.open("w", encoding="utf-8", newline="") as fo:
                    w = csv.writer(fo, delimiter=";", quoting=csv.QUOTE_ALL)
                    w.writerow(cols)
                    for r in antigo.values():
                        w.writerow([r.get(c, "") for c in cols])
                print(f"{uf}, cargo {cargo}: {len(antigo)} candidatos ({novos} acrescentados) -> {alvo.name}")


if a.consulta is not None:
    consulta()
    sys.exit(0)
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
