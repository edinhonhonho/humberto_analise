#!/usr/bin/env python3
"""Baixa os boletins de urna de TODOS os cargos de uma ou mais UFs (padrão: RS) e grava um CSV por UF.

Cada boletim de urna já traz todos os cargos votados na seção, então o download é o mesmo de
baixar_bu.py; a diferença é que aqui o CSV final inclui presidente (1), governador (3), senador (5),
deputado federal (6) e deputado estadual (7), e a lista de candidatos é baixada para cada cargo.

    python baixar_rs_completo.py                    # RS, 2026, todos os cargos
    python baixar_rs_completo.py --uf RJ,PE         # uma ou mais UFs (também baixa a malha do IBGE)
    python baixar_rs_completo.py --limite 30        # teste rápido

Pode ser interrompido (Ctrl+C) e retomado. Saídas, na pasta dados/:
  votacao_secao_2026_RS.csv          todos os cargos, uma linha por seção e candidato
  candidatos_2026_RS.csv             deputado estadual (nome usado pelo rodar.py)
  candidatos_2026_RS_c<cargo>.csv    um por cargo (6, 5, 3, 1), quando o TSE responder

Para analisar outro cargo depois, é só mudar "cargo" e "numero" no config.json: o rodar.py filtra
o cargo dentro do mesmo CSV.
"""
from __future__ import annotations

import argparse
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

import baixar_bu

TODOS = [7, 6, 5, 3, 1]  # o 7 vem primeiro: é o que o baixar_bu grava como candidatos_<ano>_<UF>.csv


IBGE = ("https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/"
        "municipio_{ano_malha}/UFs/{uf}/{uf}_Municipios_{ano_malha}.zip")


def baixar_malha(uf: str, pasta: Path, ano_malha: int = 2025) -> None:
    """Malha municipal do IBGE da UF (shapefile), se ainda não estiver na pasta."""
    if any(pasta.glob(f"{uf}_Municipios_*.shp")) or any(pasta.glob(f"{uf}_Municipios_*.gpkg")):
        return
    url = IBGE.format(uf=uf, ano_malha=ano_malha)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (analise-eleitoral)"})
        with urllib.request.urlopen(req, timeout=120) as r:
            dados = r.read()
        with zipfile.ZipFile(io.BytesIO(dados)) as z:
            z.extractall(pasta)
        print(f"  malha municipal de {uf} baixada do IBGE")
    except Exception as e:  # noqa: BLE001
        print(f"  não consegui baixar a malha de {uf} ({e}). Baixe {url} e extraia em {pasta}.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--uf", default="RS", help="uma ou mais UFs separadas por vírgula, ex.: RJ,PE")
    ap.add_argument("--ano", type=int, default=2026)
    ap.add_argument("--pasta", default="dados")
    ap.add_argument("--threads", type=int, default=6)
    ap.add_argument("--limite", type=int, default=0)
    ap.add_argument("--pleito", type=int, default=3220)
    ap.add_argument("--eleicao", type=int, default=6259, help="código da eleição dos cargos proporcionais")
    ap.add_argument("--eleicao-majoritaria", type=int, default=6258,
                    help="código da eleição de presidente, governador e senador no endereço do TSE")
    a = ap.parse_args()

    pasta = Path(a.pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    for uf in [x.strip().upper() for x in a.uf.split(",") if x.strip()]:
        print(f"\n===== {uf} =====")
        baixar_malha(uf, pasta)
        args = ["--uf", uf, "--ano", str(a.ano), "--pasta", a.pasta, "--threads", str(a.threads),
                "--pleito", str(a.pleito), "--eleicao", str(a.eleicao), "--cargos", ",".join(map(str, TODOS))]
        if a.limite:
            args += ["--limite", str(a.limite)]
        rc = baixar_bu.main(args)
        if rc:
            return rc
        print(f"\nListas de candidatos dos outros cargos ({uf}) ...")
        base_nome = pasta / f"candidatos_{a.ano}_{uf}.csv"
        guardado = base_nome.read_bytes() if base_nome.exists() else None
        for cargo in TODOS[1:]:
            eleicao = a.eleicao if cargo in (6, 7) else a.eleicao_majoritaria
            r = baixar_bu.baixar_candidatos(baixar_bu.BASE, a.ano, uf, eleicao, cargo, pasta)
            if r and base_nome.exists():
                base_nome.replace(pasta / f"candidatos_{a.ano}_{uf}_c{cargo}.csv")
                print(f"  cargo {cargo}: ok")
        if guardado is not None:
            base_nome.write_bytes(guardado)  # mantém o arquivo do deputado estadual como padrão
    print("\nConcluído. Use os votacao_secao_*.csv no config.json; o cargo é escolhido lá.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
