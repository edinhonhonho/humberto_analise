"""Pacote intermediário (JSON/CSV/GeoJSON) com tudo que o dashboard precisa.

Separar o cálculo (pesado, lê GBs) da montagem do relatório (leve) permite refazer o visual
sem reprocessar os dados: `python rodar.py --relatorio`.
"""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

TOL_SIMPLIFICA = 0.003  # graus (~300 m): suficiente para o mapa estadual


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (float, np.floating)):
        return None if (np.isnan(o) or np.isinf(o)) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, pd.DataFrame):
        return _clean(o.astype(object).where(o.notna(), None).to_dict("records"))
    return o


def _dump(obj, path: Path):
    path.write_text(json.dumps(_clean(obj), ensure_ascii=False), encoding="utf-8")


COLS_MUN = ["CD_MUNICIPIO", "NM_MUNICIPIO", "votos", "validos", "eleitores", "pct_validos",
            "votos_por_100_aptos", "quociente_locacional", "share_votos_estado", "abstencao_pct",
            "brancos_nulos_pct", "posicao_no_municipio", "lider_nome", "colega_nome",
            "votos_ate_media_estadual", "rank_votos", "lisa_cluster", "lisa_detalhe", "lisa_p"]


def exportar(ctx: dict, destino) -> Path:
    pasta = Path(destino) / "bundle"
    (pasta / "cidades").mkdir(parents=True, exist_ok=True)

    gm = ctx["gm"].copy()
    gm["geometry"] = gm.geometry.simplify(TOL_SIMPLIFICA, preserve_topology=True)
    cols = [c for c in COLS_MUN if c in gm.columns] + ["geometry"]
    gm = gm[cols]
    (pasta / "municipios.geojson").write_text(gm.to_json(na="null", drop_id=True), encoding="utf-8")

    ctx["municipal"].to_csv(pasta / "municipal.csv", index=False)
    ctx["pareto"].to_csv(pasta / "pareto.csv", index=False)
    ctx["colegas"].to_csv(pasta / "colegas.csv", index=False)
    if ctx.get("comparacao") is not None:
        ctx["comparacao"].to_csv(pasta / "comparacao.csv", index=False)
    if ctx.get("top_mun") is not None:
        ctx["top_mun"].to_csv(pasta / "top_municipio.csv", index=False)
    if ctx.get("regioes") is not None:
        ctx["regioes"].to_csv(pasta / "regioes.csv", index=False)

    an = ctx.get("analises")
    an_meta = None
    if an:
        an["mun"].to_csv(pasta / "analise_mun.csv", index=False)
        an["sobreposicao"].to_csv(pasta / "analise_sobreposicao.csv", index=False)
        if an["modelo"] is not None:
            an["modelo"].to_csv(pasta / "analise_modelo.csv", index=False)
        elif (pasta / "analise_modelo.csv").exists():
            (pasta / "analise_modelo.csv").unlink()
        an["bandas"].to_csv(pasta / "analise_bandas.csv", index=False)
        an_meta = an["meta"]
    d = ctx.get("despesas")
    desp = None
    if d:
        desp = {"total": d["total"], "custo_por_voto": d["custo_por_voto"],
                "por_categoria": d["por_categoria"]}
    meta = {"info": ctx["info"], "ano": ctx["ano"], "uf": ctx["uf"], "cargo": ctx.get("cargo", 7), "cargo_nome": ctx["cargo_nome"],
            "conc": ctx["conc"], "moran": ctx["moran"], "pct_estado": ctx["pct_estado"],
            "cob_coord": ctx["cob_coord"], "despesas": desp,
            "criterio_cidades": ctx.get("criterio_cidades", "top"), "analises_meta": an_meta,
            "cidades": [c["slug"] for c in ctx["cidades"]]}
    _dump(meta, pasta / "meta.json")

    for c in ctx["cidades"]:
        cd = pasta / "cidades" / c["slug"]
        cd.mkdir(parents=True, exist_ok=True)
        _dump({k: c[k] for k in ("nome", "slug", "votos", "pct", "validos", "eleitores", "n_locais",
                                 "n_coord", "n_fora", "res", "area_km2")}
              | {"com_hex": c.get("cells") is not None}, cd / "meta.json")
        c["locais"].to_csv(cd / "locais.csv", index=False)
        c["bairros"].to_csv(cd / "bairros.csv", index=False)
        c["zonas"].to_csv(cd / "zonas.csv", index=False)
        if c.get("cells") is not None:
            (cd / "hex.geojson").write_text(c["cells"].to_json(na="null", drop_id=True), encoding="utf-8")
        if c.get("geom") is not None:
            (cd / "limite.geojson").write_text(
                gpd.GeoSeries([c["geom"]], crs=4326).simplify(0.0005).to_json(drop_id=True),
                encoding="utf-8")
        if c.get("html_map"):
            (cd / "ruas.html").write_text(c["html_map"], encoding="utf-8")
    return pasta


def carregar(pasta) -> dict:
    pasta = Path(pasta)
    meta = json.loads((pasta / "meta.json").read_text(encoding="utf-8"))
    ctx = dict(meta)
    ctx["gm"] = gpd.read_file(pasta / "municipios.geojson")
    ctx["municipal"] = pd.read_csv(pasta / "municipal.csv")
    ctx["pareto"] = pd.read_csv(pasta / "pareto.csv")
    ctx["colegas"] = pd.read_csv(pasta / "colegas.csv")
    if (pasta / "analise_mun.csv").exists() and meta.get("analises_meta"):
        ctx["analises"] = {"mun": pd.read_csv(pasta / "analise_mun.csv"),
                           "sobreposicao": pd.read_csv(pasta / "analise_sobreposicao.csv"),
                           "modelo": pd.read_csv(pasta / "analise_modelo.csv") if (pasta / "analise_modelo.csv").exists() else None,
                           "bandas": pd.read_csv(pasta / "analise_bandas.csv"),
                           "meta": meta["analises_meta"]}
    else:
        ctx["analises"] = None
    cmp_ = pasta / "comparacao.csv"
    ctx["comparacao"] = pd.read_csv(cmp_) if cmp_.exists() else None
    tm = pasta / "top_municipio.csv"
    ctx["top_mun"] = pd.read_csv(tm) if tm.exists() else None
    reg = pasta / "regioes.csv"
    ctx["regioes"] = pd.read_csv(reg) if reg.exists() else None
    cidades = []
    for slug in meta["cidades"]:
        cd = pasta / "cidades" / slug
        c = json.loads((cd / "meta.json").read_text(encoding="utf-8"))
        c["locais"] = pd.read_csv(cd / "locais.csv")
        c["bairros"] = pd.read_csv(cd / "bairros.csv")
        c["zonas"] = pd.read_csv(cd / "zonas.csv")
        hx = cd / "hex.geojson"
        c["cells"] = gpd.read_file(hx) if (hx.exists() and c.get("com_hex")) else None
        lm = cd / "limite.geojson"
        c["geom"] = gpd.read_file(lm).geometry.iloc[0] if lm.exists() else None
        ru = cd / "ruas.html"
        c["html_map"] = ru.read_text(encoding="utf-8") if (ru.exists() and c.get("com_hex")) else None
        cidades.append(c)
    ctx["cidades"] = cidades
    return ctx
