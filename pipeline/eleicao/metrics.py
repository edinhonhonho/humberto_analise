"""Indicadores tabulares: panorama municipal, concentração, eficiência e contexto."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .partidos import partido_de
from .tse_io import norm_nome


def _div(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(b > 0, a / b, np.nan)


# --------------------------------------------------------------------------- 1. panorama
def tabela_municipal(m: pd.DataFrame) -> pd.DataFrame:
    """m = seções já unidas ao eleitorado. Devolve uma linha por município."""
    g = m.groupby(["CD_MUNICIPIO", "NM_MUNICIPIO"], as_index=False).agg(
        votos=("v_cand", "sum"), votos_partido=("v_partido", "sum"),
        validos=("v_validos", "sum"), brancos=("v_brancos", "sum"), nulos=("v_nulos", "sum"),
        comparecimento=("v_total", "sum"), eleitores=("eleitores", "sum"),
        secoes=("NR_SECAO", "count"))

    tot_votos, tot_validos = g["votos"].sum(), g["validos"].sum()
    pct_estado = 100 * tot_votos / tot_validos if tot_validos else np.nan

    g["pct_validos"] = 100 * _div(g["votos"], g["validos"])
    g["votos_por_100_aptos"] = 100 * _div(g["votos"], g["eleitores"])
    g["share_votos_estado"] = 100 * _div(g["votos"], tot_votos)
    g["quociente_locacional"] = _div(g["pct_validos"], pct_estado)
    g["abstencao_pct"] = (100 * (1 - _div(g["comparecimento"], g["eleitores"]))).clip(0, 100)
    g["brancos_nulos_pct"] = 100 * _div(g["brancos"] + g["nulos"], g["comparecimento"])
    g["pct_no_partido"] = 100 * _div(g["votos"], g["votos_partido"])
    # votos adicionais se o município chegasse à % média estadual de votos válidos
    g["votos_ate_media_estadual"] = np.maximum(0, pct_estado / 100 * g["validos"] - g["votos"])
    g["rank_votos"] = g["votos"].rank(ascending=False, method="min").astype(int)
    g["rank_pct"] = g["pct_validos"].rank(ascending=False, method="min")
    g.attrs["pct_estado"] = pct_estado
    return g.sort_values("votos", ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------- 2. concentração
def gini(x) -> float:
    x = np.sort(np.asarray(x, dtype=float))
    n = x.size
    if n == 0 or x.sum() == 0:
        return float("nan")
    i = np.arange(1, n + 1)
    return float((2 * (i * x).sum()) / (n * x.sum()) - (n + 1) / n)


def concentracao(g: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    v = np.sort(g["votos"].to_numpy(float))[::-1]
    tot = v.sum()
    cum = np.cumsum(v) / tot
    share = v / tot
    par = pd.DataFrame({"n_municipios": np.arange(1, len(v) + 1), "cum_share": 100 * cum})
    res = {
        "n_municipios": int(len(v)),
        "n_com_voto": int((v > 0).sum()),
        "n_para_50": int((cum < 0.5).sum() + 1),
        "n_para_80": int((cum < 0.8).sum() + 1),
        "top1_share": float(100 * share[0]),
        "top5_share": float(100 * share[:5].sum()),
        "top10_share": float(100 * share[:10].sum()),
        "gini": gini(v),
        "hhi": float((share ** 2).sum() * 10000),
        "n_efetivo_municipios": float(1 / (share ** 2).sum()),
    }
    return res, par


# --------------------------------------------------------------------------- 8. contexto
def contexto_partido(cand: pd.DataFrame, numero: int):
    """Ranking estadual do candidato e dos colegas de partido."""
    partido = partido_de(numero)
    tot = (cand.groupby(["NR_VOTAVEL", "NM_VOTAVEL"], as_index=False)["QT_VOTOS"].sum()
           .rename(columns={"QT_VOTOS": "votos"}))
    tot["partido_num"] = partido_de(tot["NR_VOTAVEL"])
    tot["rank_estado"] = tot["votos"].rank(ascending=False, method="min").astype(int)
    tot["rank_no_partido"] = (tot.groupby("partido_num")["votos"]
                              .rank(ascending=False, method="min").astype(int))
    colegas = tot[tot["partido_num"] == partido].sort_values("votos", ascending=False)
    colegas = colegas.rename(columns={"NR_VOTAVEL": "numero", "NM_VOTAVEL": "nome"})
    colegas["share_partido"] = 100 * colegas["votos"] / colegas["votos"].sum()
    return colegas.reset_index(drop=True)


def lideres_municipio(cand: pd.DataFrame, numero: int) -> pd.DataFrame:
    """Em cada município: quem foi o mais votado, em que posição ficou o candidato e
    qual colega de partido foi mais votado."""
    partido = partido_de(numero)
    c = cand.copy()
    c["pos"] = c.groupby("CD_MUNICIPIO")["QT_VOTOS"].rank(ascending=False, method="min")
    idx = c.groupby("CD_MUNICIPIO")["QT_VOTOS"].idxmax()
    lider = c.loc[idx, ["CD_MUNICIPIO", "NM_VOTAVEL", "QT_VOTOS"]].rename(
        columns={"NM_VOTAVEL": "lider_nome", "QT_VOTOS": "lider_votos"})
    meu = c[c["NR_VOTAVEL"] == numero][["CD_MUNICIPIO", "pos"]].rename(
        columns={"pos": "posicao_no_municipio"})
    col = c[(partido_de(c["NR_VOTAVEL"]) == partido) & (c["NR_VOTAVEL"] != numero)]
    if len(col):
        icol = col.groupby("CD_MUNICIPIO")["QT_VOTOS"].idxmax()
        colega = col.loc[icol, ["CD_MUNICIPIO", "NM_VOTAVEL", "QT_VOTOS"]].rename(
            columns={"NM_VOTAVEL": "colega_nome", "QT_VOTOS": "colega_votos"})
    else:
        colega = pd.DataFrame(columns=["CD_MUNICIPIO", "colega_nome", "colega_votos"])
    out = lider.merge(meu, on="CD_MUNICIPIO", how="left").merge(colega, on="CD_MUNICIPIO",
                                                                 how="left")
    out["lider_e_o_candidato"] = out["lider_nome"].isin(
        c.loc[c["NR_VOTAVEL"] == numero, "NM_VOTAVEL"])
    return out


# --------------------------------------------------------------------------- regiões opcionais
def agregar_regioes(g: pd.DataFrame, regioes_csv, col_regiao: str = "regiao") -> pd.DataFrame | None:
    """Agrega o painel municipal por uma regionalização do usuário (ex.: COREDE, mesorregião).
    O CSV precisa de uma coluna de município (CD_MUNICIPIO do TSE ou NM_MUNICIPIO) e outra
    chamada 'regiao'."""
    r = pd.read_csv(regioes_csv, sep=None, engine="python", dtype=str)
    r.columns = [c.strip() for c in r.columns]
    if col_regiao not in r.columns:
        raise KeyError(f"O CSV de regiões precisa da coluna '{col_regiao}'.")
    if "CD_MUNICIPIO" in r.columns:
        r["CD_MUNICIPIO"] = pd.to_numeric(r["CD_MUNICIPIO"], errors="coerce")
        j = g.merge(r[["CD_MUNICIPIO", col_regiao]], on="CD_MUNICIPIO", how="left")
    else:
        nm = next(c for c in r.columns if "MUNIC" in c.upper())
        r["chave"] = r[nm].map(norm_nome)
        j = g.assign(chave=g["NM_MUNICIPIO"].map(norm_nome)).merge(
            r[["chave", col_regiao]], on="chave", how="left")
    j[col_regiao] = j[col_regiao].fillna("(sem região)")
    out = j.groupby(col_regiao, as_index=False).agg(
        municipios=("CD_MUNICIPIO", "count"), votos=("votos", "sum"), validos=("validos", "sum"),
        eleitores=("eleitores", "sum"))
    out["pct_validos"] = 100 * _div(out["votos"], out["validos"])
    out["votos_por_100_aptos"] = 100 * _div(out["votos"], out["eleitores"])
    out["share_votos_estado"] = 100 * out["votos"] / out["votos"].sum()
    return out.sort_values("votos", ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------- 9. campanha
def resumo_despesas(df: pd.DataFrame | None, votos_total: int) -> dict | None:
    if df is None or df["valor"].notna().sum() == 0:
        return None
    total = float(df["valor"].sum())
    c_cat = next((c for c in ("DS_ORIGEM_DESPESA", "DS_DESPESA") if c in df.columns), None)
    por = (df.groupby(c_cat)["valor"].sum().sort_values(ascending=False).reset_index()
           .rename(columns={c_cat: "categoria"})) if c_cat else None
    return {"total": total, "custo_por_voto": total / votos_total if votos_total else np.nan,
            "por_categoria": por}

# --------------------------------------------------------------------------- comparação entre partidos
SIGLAS = {10: "REPUBLICANOS", 11: "PP", 12: "PDT", 13: "PT", 14: "MISSÃO", 15: "MDB", 16: "PSTU", 18: "REDE",
          20: "PODE", 22: "PL", 23: "CIDADANIA", 30: "NOVO", 35: "DEMOCRATA", 40: "PSB", 43: "PV",
          44: "UNIÃO", 45: "PSDB", 50: "PSOL", 55: "PSD", 65: "PCDOB", 80: "UP"}


def nomes_siglas(cand: pd.DataFrame, candidatos: pd.DataFrame | None = None):
    """Nome por número de candidato, sigla por número de partido e situação por candidato."""
    nomes = (cand.drop_duplicates("NR_VOTAVEL").set_index("NR_VOTAVEL")["NM_VOTAVEL"].astype(str).to_dict())
    sig, sit = dict(SIGLAS), {}
    if candidatos is not None and len(candidatos):
        cc = candidatos.set_index("numero")
        for n, r in cc.iterrows():
            if r["nome"] and r["nome"] != "nan":
                nomes[n] = r["nome"]
            sit[n] = r.get("situacao", "")
        by_party = candidatos.assign(p=partido_de(candidatos["numero"])).groupby("p")["sigla"].first()
        sig.update({int(k): v for k, v in by_party.items() if isinstance(v, str) and v and v != "nan"})
    return nomes, sig, sit


def top_por_municipio(cand: pd.DataFrame, g: pd.DataFrame, candidatos: pd.DataFrame | None = None,
                      k: int = 5) -> pd.DataFrame:
    """Os k candidatos mais votados em cada município: CD_MUNICIPIO, posicao, numero, nome, sigla, votos, pct."""
    nomes, sig, _ = nomes_siglas(cand, candidatos)
    validos = g.drop_duplicates("CD_MUNICIPIO").set_index("CD_MUNICIPIO")["validos"]
    c = cand.groupby(["CD_MUNICIPIO", "NR_VOTAVEL"], as_index=False)["QT_VOTOS"].sum()
    c = c[c["QT_VOTOS"] > 0].sort_values(["CD_MUNICIPIO", "QT_VOTOS", "NR_VOTAVEL"], ascending=[True, False, True])
    c["posicao"] = c.groupby("CD_MUNICIPIO").cumcount() + 1
    c = c[c["posicao"] <= k].copy()
    c["numero"] = c["NR_VOTAVEL"].astype(int)
    c["nome"] = c["NR_VOTAVEL"].map(lambda n: nomes.get(n, str(n)))
    c["sigla"] = c["NR_VOTAVEL"].map(lambda n: sig.get(partido_de(int(n)), f"Partido {partido_de(int(n))}"))
    c["votos"] = c["QT_VOTOS"].astype(int)
    c["pct"] = 100 * c["QT_VOTOS"] / c["CD_MUNICIPIO"].map(validos).replace(0, np.nan)
    return c[["CD_MUNICIPIO", "posicao", "numero", "nome", "sigla", "votos", "pct"]].reset_index(drop=True)


def comparar_partidos(cand: pd.DataFrame, g: pd.DataFrame, numero: int, gm=None,
                      candidatos: pd.DataFrame | None = None, permutacoes: int = 199) -> pd.DataFrame:
    """Compara o candidato-foco com o mais votado de cada partido: volume, abrangência
    (em quantos municípios tem presença relevante) e concentração/vizinhança.

    cand: votos por município e candidato; g: tabela municipal (precisa de CD_MUNICIPIO e validos)."""
    tot = (cand.groupby("NR_VOTAVEL", as_index=False)["QT_VOTOS"].sum().rename(columns={"QT_VOTOS": "votos"}))
    tot["partido_num"] = partido_de(tot["NR_VOTAVEL"])
    nomes, sig, sit = nomes_siglas(cand, candidatos)
    tot["sigla"] = tot["partido_num"].map(lambda p: sig.get(int(p), f"Partido {int(p)}"))
    tops = tot.loc[tot.groupby("partido_num")["votos"].idxmax()]
    sel = set(tops["NR_VOTAVEL"]) | {numero}
    t = tot[tot["NR_VOTAVEL"].isin(sel)].copy()

    muns = g[["CD_MUNICIPIO", "validos"]].drop_duplicates("CD_MUNICIPIO").set_index("CD_MUNICIPIO")
    c = cand[cand["NR_VOTAVEL"].isin(sel)]
    pv = (c.pivot_table(index="CD_MUNICIPIO", columns="NR_VOTAVEL", values="QT_VOTOS", aggfunc="sum")
          .reindex(muns.index).fillna(0))
    pct = pv.div(muns["validos"].replace(0, np.nan), axis=0).fillna(0) * 100
    pos = cand.assign(pos=cand.groupby("CD_MUNICIPIO")["QT_VOTOS"].rank(ascending=False, method="min"))
    top3 = (pos[pos["NR_VOTAVEL"].isin(sel) & (pos["pos"] <= 3) & (pos["QT_VOTOS"] > 0)]
            .groupby("NR_VOTAVEL")["CD_MUNICIPIO"].nunique())

    validos_total = float(muns["validos"].sum())
    linhas = []
    for r in t.itertuples():
        v = pv[r.NR_VOTAVEL].to_numpy(float)
        sh = v / v.sum() if v.sum() else v
        linhas.append({
            "numero": int(r.NR_VOTAVEL), "nome": nomes.get(r.NR_VOTAVEL, str(r.NR_VOTAVEL)),
            "sigla": r.sigla, "situacao": sit.get(r.NR_VOTAVEL, ""), "votos": float(r.votos),
            "pct_estado": 100 * float(r.votos) / validos_total if validos_total else np.nan,
            "n_mun_voto": int((v > 0).sum()),
            "n_mun_05pct": int((pct[r.NR_VOTAVEL] >= 0.5).sum()),
            "n_mun_1pct": int((pct[r.NR_VOTAVEL] >= 1).sum()),
            "n_mun_5pct": int((pct[r.NR_VOTAVEL] >= 5).sum()),
            "n_top3": int(top3.get(r.NR_VOTAVEL, 0)),
            "top1_share": float(100 * sh.max()) if v.sum() else np.nan,
            "gini": gini(v),
            "n_efetivo": float(1 / (sh ** 2).sum()) if v.sum() else np.nan,
            "foco": bool(r.NR_VOTAVEL == numero),
            "top_do_partido": bool(r.NR_VOTAVEL in set(tops["NR_VOTAVEL"])),
        })
    out = pd.DataFrame(linhas)
    out["n_municipios"] = int(len(muns))
    if gm is not None and len(out):
        from . import spatial
        idx = pct.index.get_indexer(gm["CD_MUNICIPIO"].fillna(-1).astype(int))
        series = {}
        for n in out["numero"]:
            col = pct[n].to_numpy(float)
            series[n] = np.where(idx >= 0, col[np.clip(idx, 0, None)], 0.0)
        res = spatial.moran_varios(gm, series, permutacoes)
        out["moran_I"] = out["numero"].map(lambda n: res[n][0])
        out["moran_p"] = out["numero"].map(lambda n: res[n][1])
    return out.sort_values("votos", ascending=False).reset_index(drop=True)
