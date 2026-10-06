#!/usr/bin/env python3
"""Análise espacial da votação de um candidato em eleição proporcional.

Exemplo (teste com 2022):
    python run_analysis.py --ano 2022 --uf RS --cargo 7 --numero 65065 \
        --votacao dados/votacao_secao_2022_RS.zip \
        --locais dados/eleitorado_local_votacao_2022.zip \
        --malha dados/RS_Municipios_2022.zip --saida saida_2022

Para 2026, troque os três arquivos e o ano; nada mais muda.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd

from eleicao import analises, bundle, metrics, report, spatial, tse_io, viz


def log(msg=""):
    print(msg, flush=True)


def salvar_gpkg(gdf, destino, layer):
    """Grava num diretório temporário e copia: o SQLite falha em algumas pastas (rede, nuvem)."""
    destino = Path(destino)
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t) / destino.name
        gdf.to_file(tmp, layer=layer, driver="GPKG")
        shutil.copyfile(tmp, destino)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--ano", type=int, required=True)
    ap.add_argument("--uf", default="RS")
    ap.add_argument("--cargo", type=int, default=7, help="7 = Deputado Estadual (padrão)")
    ap.add_argument("--turno", type=int, default=1)
    ap.add_argument("--numero", type=int, required=True, help="número do candidato (5 dígitos)")
    ap.add_argument("--nome", default=None, help="nome do candidato (se o arquivo não trouxer, como nos boletins de urna)")
    ap.add_argument("--votacao", required=True, help="votacao_secao_ANO_UF (.zip ou .csv)")
    ap.add_argument("--locais", default=None, help="eleitorado por local de votação (.zip/.csv); traz coordenadas e bairro")
    ap.add_argument("--perfil", default=None, help="perfil do eleitorado por seção (.zip/.csv); traz eleitores aptos")
    ap.add_argument("--malha", required=True, help="malha municipal IBGE da UF")
    ap.add_argument("--saida", default="saida")
    ap.add_argument("--h3-res", default="auto", help="resolução H3: auto (padrão) ou 6 a 9 (8 ≈ 0,7 km²)")
    ap.add_argument("--hex", action="store_true",
                    help="gera hexágonos H3 e Gi* por cidade (desligado por padrão: o local de votação é só um proxy)")
    ap.add_argument("--png", action="store_true", help="também gera figuras PNG estáticas (matplotlib)")
    ap.add_argument("--top-cidades", type=int, default=10)
    ap.add_argument("--cidades", default="", help="lista separada por vírgula (sobrepõe o top)")
    ap.add_argument("--min-locais", type=int, default=12,
                    help="mínimo de locais com coordenada para análise intraurbana")
    ap.add_argument("--col-eleitores", default=None, help="força a coluna de eleitores aptos")
    ap.add_argument("--candidatos", default=None,
                    help="lista de candidatos (candidatos_ANO_UF.csv do baixar_bu.py ou consulta_cand do TSE): nomes e siglas")
    ap.add_argument("--federacao", default=None,
                    help='números dos partidos da federação do candidato, ex.: "13,43,65" (padrão: tabela de 2026)')
    ap.add_argument("--despesas", default=None, help="CSV de despesas (prestação de contas)")
    ap.add_argument("--regioes", default=None, help="CSV município->regiao (ex.: COREDE)")
    ap.add_argument("--permutacoes", type=int, default=999)
    ap.add_argument("--site", default=None, help="pasta do site em pastas (padrão: ao lado da pasta de saída)")
    a = ap.parse_args(argv)

    t0 = time.time()
    out = Path(a.saida)
    for d in ("figuras", "tabelas", "geo"):
        (out / d).mkdir(parents=True, exist_ok=True)

    log("1/7 Lendo votação por seção")
    secoes, cand, info = tse_io.load_votacao_secao(a.votacao, a.numero, a.cargo, a.turno, a.uf,
                                                    log=log)

    cands = tse_io.load_candidatos(a.candidatos, a.cargo, log=log) if a.candidatos else None
    if cands is not None and len(cands):
        nm = cands.set_index("numero")["nome"].to_dict()
        vazio = cand["NM_VOTAVEL"].astype(str).str.fullmatch(r"\d+")
        cand.loc[vazio, "NM_VOTAVEL"] = cand.loc[vazio, "NR_VOTAVEL"].map(nm).fillna(cand.loc[vazio, "NM_VOTAVEL"])
        if info.get("nome", "").strip().isdigit() and a.numero in nm:
            info["nome"] = nm[a.numero]
    if a.nome:
        info["nome"] = a.nome
    log("2/7 Lendo eleitorado (perfil por seção e/ou locais de votação)")
    perfil = tse_io.load_perfil(a.perfil, a.uf, log=log) if a.perfil else None
    locais, nivel = (tse_io.load_locais(a.locais, a.uf, a.col_eleitores, log=log)
                     if a.locais else (None, "secao"))
    if perfil is None and locais is None:
        log("  AVISO: sem arquivo de eleitorado; taxas por eleitor e abstenção ficarão vazias.")

    log("3/7 Lendo malha e cruzando códigos TSE x IBGE")
    mun_tse = secoes[["CD_MUNICIPIO", "NM_MUNICIPIO"]].drop_duplicates()
    malha = tse_io.load_malha(a.malha, a.uf, mun_tse, log=log)

    m = tse_io.juntar_secoes_locais(secoes, perfil, locais, nivel, log=log)
    m = tse_io.filtrar_coordenadas(m, malha.total_bounds, log=log)
    cob_coord = float(m["lat"].notna().mean())

    log("4/7 Indicadores municipais, concentração e contexto")
    g = metrics.tabela_municipal(m)
    pct_estado = g.attrs["pct_estado"]
    conc, pareto = metrics.concentracao(g)
    colegas = metrics.contexto_partido(cand, a.numero)
    lid = metrics.lideres_municipio(cand, a.numero)
    g = g.merge(lid, on="CD_MUNICIPIO", how="left")
    regioes = metrics.agregar_regioes(g, a.regioes) if a.regioes else None
    desp = None
    if a.despesas:
        desp = metrics.resumo_despesas(tse_io.load_despesas(a.despesas, a.numero, log=log),
                                       info["votos_total"])

    log("5/7 Autocorrelação espacial entre municípios (Moran / LISA)")
    gm = malha.merge(g, on="CD_MUNICIPIO", how="left")
    for c in ("votos", "validos", "eleitores"):
        gm[c] = gm[c].fillna(0)
    gm["NM_MUNICIPIO"] = gm["NM_MUNICIPIO"].fillna(gm["nm_ibge"].str.upper())
    gm, moran = spatial.lisa_municipal(gm, "pct_validos", a.permutacoes)
    log(f"  Moran I = {moran.get('I'):.3f} (p = {moran.get('p'):.3f})")

    log("  Comparação com o mais votado de cada partido")
    comp = metrics.comparar_partidos(cand, g, a.numero, gm, cands, permutacoes=min(a.permutacoes, 199))

    log("  Análises complementares (sobreposição, federação, modelo, distância)")
    parts = analises.partidos_federacao(a.numero, a.federacao)
    anal = analises.rodar_todas(cand, g, gm, a.numero, comp, parts, min(a.permutacoes, 199))
    anal["meta"]["federacao"]["nome"] = "/".join(metrics.SIGLAS.get(p_, str(p_)) for p_ in parts)

    log("6/7 Mapas estaduais")
    nome = info["nome"].title()
    if a.png:
        sub = f"{a.uf} · {a.ano}"
        viz.choropleth(gm, "votos", f"{nome}: votos por município", out / "figuras/mapa_votos.png", sub,
                       zero_class=True, inteiro=True)
        viz.choropleth(gm, "pct_validos", f"{nome}: % de votos válidos",
                       out / "figuras/mapa_pct_validos.png", sub, zero_class=True, unidade="%")
        viz.choropleth_lq(gm, f"{nome}: quociente locacional",
                          out / "figuras/mapa_quociente_locacional.png", sub)
        viz.lisa_map(gm, f"{nome}: clusters espaciais (LISA)", out / "figuras/mapa_lisa.png", sub)
        viz.pareto_chart(pareto, conc, "Concentração dos votos por município", out / "figuras/pareto.png")
        viz.barh_top(g, "votos", "Municípios com mais votos", out / "figuras/top_municipios.png",
                     unidade="votos")

    log("7/7 Análise intraurbana")
    if a.cidades:
        alvo = [norm for norm in (tse_io.norm_nome(x) for x in a.cidades.split(",") if x.strip())]
        escolhidas = g[g["NM_MUNICIPIO"].map(tse_io.norm_nome).isin(alvo)]
    else:
        escolhidas = g.head(max(a.top_cidades * 2, a.top_cidades))
    h3_res = "auto" if str(a.h3_res).lower() == "auto" else int(a.h3_res)
    cidades, todos_locais, todas_celulas = [], [], []
    geom_mun = malha.set_index("CD_MUNICIPIO").geometry
    for _, r in escolhidas.iterrows():
        if len(cidades) >= (len(escolhidas) if a.cidades else a.top_cidades):
            break
        cod, nm = int(r["CD_MUNICIPIO"]), r["NM_MUNICIPIO"].title()
        mc = m[m["CD_MUNICIPIO"] == cod]
        loc = spatial.agregar_locais(mc)
        geom = geom_mun.get(cod)
        loc, n_fora = spatial.validar_pontos(loc, geom)
        if n_fora:
            log(f"  {nm}: {n_fora} local(is) com coordenada fora do município, descartado(s)")
        n_coord = int(loc["lat"].notna().sum())
        cells = None
        if a.hex and n_coord >= a.min_locais:
            cells = spatial.celulas_h3(loc, h3_res)
            cells = spatial.gi_star(cells, "pct_validos", permutacoes=a.permutacoes)
        elif a.hex:
            log(f"  {nm}: só {n_coord} locais com coordenada; sem hexágonos")
        slug = tse_io.norm_nome(nm).lower()
        slug_png = f"cidade_{slug}"
        if a.png and cells is not None:
            viz.city_cells_map(nm, geom, cells, out / f"figuras/{slug_png}_pct.png")
            viz.city_gi_map(nm, geom, cells, out / f"figuras/{slug_png}_gi.png")
        item = {"nome": nm, "slug": slug, "votos": float(r["votos"]), "pct": float(r["pct_validos"]),
                "validos": float(r["validos"]), "eleitores": float(r["eleitores"]),
                "n_locais": int(len(loc)), "n_coord": n_coord, "n_fora": int(n_fora),
                "res": None if cells is None else int(cells.attrs.get("res")),
                "area_km2": None if cells is None else cells.attrs.get("area_km2"),
                "locais": loc, "bairros": spatial.agregar_bairros(mc), "zonas": spatial.agregar_zonas(mc),
                "cells": cells, "geom": geom,
                "html_map": viz.mapa_interativo(nm, geom, loc, cells) if cells is not None else None}
        cidades.append(item)
        todos_locais.append(loc.assign(municipio=nm))
        if cells is not None:
            todas_celulas.append(cells.assign(municipio=nm))
            log(f"  {nm}: {len(loc)} locais -> {len(cells)} hexágonos (H3 res {item['res']})")
        else:
            log(f"  {nm}: {len(loc)} locais de votação")

    # ---- saídas tabulares e geográficas
    g.to_csv(out / "tabelas/municipios.csv", index=False, sep=";", decimal=",")
    colegas.to_csv(out / "tabelas/colegas_partido.csv", index=False, sep=";", decimal=",")
    pareto.to_csv(out / "tabelas/pareto.csv", index=False, sep=";", decimal=",")
    with pd.ExcelWriter(out / "tabelas/resultados.xlsx") as xw:
        g.to_excel(xw, sheet_name="municipios", index=False)
        colegas.to_excel(xw, sheet_name="colegas_partido", index=False)
        if regioes is not None:
            regioes.to_excel(xw, sheet_name="regioes", index=False)
        for c in cidades:
            c["locais"].to_excel(xw, sheet_name=f"locais_{c['nome'][:20]}", index=False)
            c["zonas"].to_excel(xw, sheet_name=f"zonas_{c['nome'][:20]}", index=False)
            c["bairros"].to_excel(xw, sheet_name=f"bairros_{c['nome'][:19]}", index=False)
    salvar_gpkg(gm, out / "geo/municipios.gpkg", "municipios")
    L = (pd.concat(todos_locais, ignore_index=True).dropna(subset=["lat", "lon"])
         if todos_locais else pd.DataFrame())
    if len(L):
        salvar_gpkg(gpd.GeoDataFrame(L, geometry=gpd.points_from_xy(L["lon"], L["lat"]), crs=4326),
                    out / "geo/locais_votacao.gpkg", "locais")
    if todas_celulas:
        salvar_gpkg(gpd.GeoDataFrame(pd.concat(todas_celulas, ignore_index=True), crs=4326),
                    out / "geo/hexagonos_h3.gpkg", "hexagonos")

    ctx = {"info": info, "ano": a.ano, "uf": a.uf, "cargo": a.cargo,
           "cargo_nome": tse_io.CARGOS_PROPORCIONAIS.get(a.cargo, f"Cargo {a.cargo}"),
           "conc": conc, "moran": moran, "municipal": g, "pct_estado": pct_estado, "gm": gm,
           "pareto": pareto, "cidades": cidades, "colegas": colegas, "regioes": regioes,
           "despesas": desp, "cob_coord": cob_coord, "comparacao": comp, "analises": anal,
           "criterio_cidades": "manual" if a.cidades else "top",
           "top_mun": metrics.top_por_municipio(cand, g, cands)}
    pasta_bundle = bundle.exportar(ctx, out)
    dash = report.build_from_bundle(pasta_bundle, out / "dashboard.html", Path(a.site) if a.site else out.resolve().parent / "site")
    log(f"\nPronto em {time.time() - t0:.0f}s -> {dash}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
