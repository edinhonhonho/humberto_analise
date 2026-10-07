#!/usr/bin/env python3
"""Converte os dados de uma UF para os arquivos que o navegador lê (análise calculada na hora).

    python converter_parquet.py --uf PE            (uma UF)
    python converter_parquet.py --uf todas         (todas as que têm votacao_secao_2026_<UF>.csv)

Cria dados_web/<ano>/<UF>/ com:
  votos.parquet    votos por seção e candidato, ordenados por (turno, cargo, votável): o navegador lê só o trecho
                   do candidato escolhido (blocos do rodapé do Parquet + requisições parciais)
  secoes.parquet   uma linha por seção e cargo: local, aptos, válidos, brancos, nulos, total
  mc.parquet       votos por município e votável (todos os candidatos do cargo): base de rankings e comparações
  malha.json       municípios (código TSE, nome, caminho do mapa, vizinhos Queen e centroide em metros)
  nomes.json       nome, sigla e situação de cada candidato, por cargo
  meta.json        nomes dos municípios segundo o TSE e contagens
Os arquivos de votos usam Snappy (lido por qualquer biblioteca de navegador, sem WASM).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE))

from eleicao import svgviz, tse_io  # noqa: E402

TOL_SIMPLIFICA = 0.003  # igual ao bundle.py


def sniff(path: Path):
    head = path.open("rb").read(65536)
    enc = tse_io._sniff_encoding(head)
    sep = ";" if head.count(b";") >= head.count(b",") else ","
    return enc, sep


def converter_votos(csv: Path, destino: Path, uf: str, ano: int):
    import duckdb
    enc, sep = sniff(csv)
    con = duckdb.connect()
    con.execute("SET preserve_insertion_order=false")
    rel = f"read_csv('{csv.as_posix()}', delim='{sep}', header=true, all_varchar=true, quote='\"', " \
          f"encoding='{'utf-8' if enc == 'utf-8' else 'latin-1'}', ignore_errors=true)"
    cols = {r[0].strip().upper() for r in con.execute(f"DESCRIBE SELECT * FROM {rel}").fetchall()}
    falta = [c for c in ("NR_TURNO", "CD_CARGO", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO", "NR_VOTAVEL", "QT_VOTOS")
             if c not in cols]
    if falta:
        raise SystemExit(f"{csv.name}: faltam colunas {falta}")
    loc = "TRY_CAST(NR_LOCAL_VOTACAO AS INTEGER)" if "NR_LOCAL_VOTACAO" in cols else "NULL"
    apt = "TRY_CAST(QT_APTOS AS INTEGER)" if "QT_APTOS" in cols else "NULL"
    uf_f = f"AND SG_UF = '{uf}'" if "SG_UF" in cols else ""
    con.execute(f"""
    CREATE TABLE raw AS
    SELECT CAST(NR_TURNO AS UTINYINT) turno, CAST(CD_CARGO AS UTINYINT) cargo, CAST(CD_MUNICIPIO AS INTEGER) mun,
           ANY_VALUE(trim(NM_MUNICIPIO)) nm_mun, CAST(NR_ZONA AS USMALLINT) zona, CAST(NR_SECAO AS USMALLINT) secao,
           COALESCE(ANY_VALUE({loc}), 0) loc, CAST(NR_VOTAVEL AS INTEGER) votavel,
           SUM(CAST(QT_VOTOS AS INTEGER)) votos, COALESCE(MAX({apt}), 0) aptos
    FROM {rel}
    WHERE CD_CARGO IN ('1','3','5','6','7','8') {uf_f}
    GROUP BY turno, cargo, mun, zona, secao, votavel""")
    destino.mkdir(parents=True, exist_ok=True)
    con.execute(f"""COPY (SELECT turno, cargo, votavel, mun, zona, secao, loc, votos FROM raw
                    ORDER BY turno, cargo, votavel, mun, zona, secao)
                    TO '{(destino / 'votos.parquet').as_posix()}' (FORMAT PARQUET, COMPRESSION SNAPPY, ROW_GROUP_SIZE 20000)""")
    con.execute(f"""COPY (SELECT turno, cargo, mun, zona, secao, ANY_VALUE(loc) loc, MAX(aptos) aptos,
                           SUM(CASE WHEN votavel NOT IN (95,96) THEN votos ELSE 0 END) validos,
                           SUM(CASE WHEN votavel = 95 THEN votos ELSE 0 END) brancos,
                           SUM(CASE WHEN votavel = 96 THEN votos ELSE 0 END) nulos,
                           SUM(votos) total
                    FROM raw GROUP BY turno, cargo, mun, zona, secao ORDER BY turno, cargo, mun, zona, secao)
                    TO '{(destino / 'secoes.parquet').as_posix()}' (FORMAT PARQUET, COMPRESSION SNAPPY, ROW_GROUP_SIZE 50000)""")
    con.execute(f"""COPY (SELECT turno, cargo, votavel, mun, SUM(votos) votos FROM raw WHERE votavel NOT IN (95,96)
                    GROUP BY turno, cargo, votavel, mun HAVING SUM(votos) > 0 ORDER BY turno, cargo, votavel, mun)
                    TO '{(destino / 'mc.parquet').as_posix()}' (FORMAT PARQUET, COMPRESSION SNAPPY, ROW_GROUP_SIZE 50000)""")
    muns = con.execute("SELECT mun, ANY_VALUE(nm_mun) FROM raw GROUP BY mun ORDER BY mun").fetchall()
    cargos = [int(r[0]) for r in con.execute("SELECT DISTINCT cargo FROM raw ORDER BY 1").fetchall()]
    turnos = [int(r[0]) for r in con.execute("SELECT DISTINCT turno FROM raw ORDER BY 1").fetchall()]
    return {int(c): n for c, n in muns}, cargos, turnos


def converter_malha(shp: Path, uf: str, muns: dict, destino: Path):
    import geopandas as gpd
    from eleicao import spatial
    mun_tse = pd.DataFrame({"CD_MUNICIPIO": list(muns), "NM_MUNICIPIO": list(muns.values())})
    malha = tse_io.load_malha(shp, uf, mun_tse, log=lambda *a, **k: None)
    gp = malha.to_crs(spatial.utm_crs(malha)).reset_index(drop=True)
    if len(gp) < 3:
        viz = [[] for _ in range(len(gp))]
    else:
        from libpysal import weights
        w = weights.Queen.from_dataframe(gp, use_index=False)
        if w.islands:
            w = weights.KNN.from_dataframe(gp, k=5)
        viz = [sorted(int(x) for x in w.neighbors[i]) for i in range(len(gp))]
    cen = gp.geometry.centroid
    simp = malha.copy()
    simp["geometry"] = simp.geometry.simplify(TOL_SIMPLIFICA, preserve_topology=True)
    # o bundle grava e relê um GeoJSON; o arredondamento de 6 casas é o mesmo
    simp["geometry"] = gpd.GeoSeries.from_wkt(
        simp.geometry.apply(lambda g: __import__("shapely").wkt.dumps(g, rounding_precision=6)), crs=4326).values
    proj = svgviz.Proj(svgviz.bounds_principais(simp), 760)
    itens = []
    for i, r in enumerate(simp.itertuples(index=False)):
        itens.append({"cod": int(r.CD_MUNICIPIO), "ibge": str(r.cd_ibge), "nome": str(r.nm_ibge),
                      "d": svgviz.geom_path(r.geometry, proj), "viz": viz[i],
                      "cx": round(float(cen.iloc[i].x), 1), "cy": round(float(cen.iloc[i].y), 1)})
    out = {"uf": uf, "W": proj.W, "H": round(proj.H), "vb": f"0 0 {proj.W:g} {proj.H:.0f}", "municipios": itens}
    (destino / "malha.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return len(itens)


def converter_nomes(pasta_dados: Path, uf: str, ano: int, destino: Path):
    nomes = {}
    for cargo in (3, 5, 6, 7, 8):
        f = next(iter(pasta_dados.rglob(f"candidatos_{ano}_{uf}_c{cargo}.csv")), None)
        if f is None:
            continue
        df = tse_io.load_candidatos(f, cargo, log=lambda *a, **k: None)
        if df is None:
            continue
        nomes[str(cargo)] = {str(int(r.numero)): [r.nome, r.sigla, r.situacao]
                             for r in df.itertuples() if r.nome and r.nome != "nan"}
    (destino / "nomes.json").write_text(json.dumps(nomes, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return sum(len(v) for v in nomes.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uf", default="todas")
    ap.add_argument("--ano", type=int, default=2026)
    ap.add_argument("--dados", default="dados")
    ap.add_argument("--saida", default="dados_web")
    ap.add_argument("--refazer", action="store_true")
    a = ap.parse_args()
    dados = Path(a.dados).resolve()
    ufs = ([p.stem.split("_")[-1] for p in sorted(dados.glob(f"votacao_secao_{a.ano}_??.csv"))]
           if a.uf.lower() == "todas" else [u.strip().upper() for u in a.uf.split(",")])
    for uf in ufs:
        destino = Path(a.saida).resolve() / str(a.ano) / uf
        if (destino / "meta.json").exists() and not a.refazer:
            print(f"{uf}: já convertida (use --refazer)")
            continue
        csv = next(iter(dados.glob(f"votacao_secao_{a.ano}_{uf}.csv")), None)
        if csv is None:
            print(f"{uf}: sem votacao_secao_{a.ano}_{uf}.csv")
            continue
        shp = next((p for p in dados.rglob(f"{uf}_Municipios*.shp")), None) or next(
            (p for p in dados.rglob(f"{uf}_municipios*.*") if p.suffix.lower() in (".shp", ".gpkg", ".json", ".geojson", ".zip")), None)
        print(f"{uf}: convertendo {csv.name}...", flush=True)
        muns, cargos, turnos = converter_votos(csv, destino, uf, a.ano)
        nm = converter_nomes(dados, uf, a.ano, destino)
        nmal = converter_malha(shp, uf, muns, destino) if shp else 0
        (destino / "meta.json").write_text(json.dumps(
            {"uf": uf, "ano": a.ano, "cargos": cargos, "turnos": turnos, "municipios": {str(k): v for k, v in muns.items()},
             "n_nomes": nm, "n_malha": nmal}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        tam = sum(f.stat().st_size for f in destino.iterdir()) / 1e6
        print(f"{uf}: {len(muns)} municípios, {nm} nomes, {nmal} polígonos, {tam:.1f} MB", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
