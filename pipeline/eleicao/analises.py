"""Análises espaciais complementares sobre a votação municipal de um candidato.

1. sobreposição geográfica com outros candidatos (correlação, sobreposição de base, Moran bivariado);
2. participação do candidato na votação da sua federação, município a município;
3. modelo (mínimos quadrados ponderados) com resíduos espaciais: onde ele vota acima ou abaixo do esperado;
4. distância dos redutos: como a votação decai com o afastamento dos maiores municípios dele.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import metrics, spatial
from .partidos import partido_de

# Federações partidárias de 2026 (número do partido -> números dos partidos da federação).
# Pode ser sobrescrito por --federacao "13,65,43".
FEDERACOES_2026 = {
    13: (13, 43, 65), 43: (13, 43, 65), 65: (13, 43, 65),   # Brasil da Esperança (PT, PV, PCdoB)
    23: (23, 45), 45: (23, 45),                              # PSDB Cidadania
    18: (18, 50), 50: (18, 50),                              # PSOL Rede
    11: (11, 44), 44: (11, 44),                              # União Progressista (PP, União)
    25: (25, 77), 77: (25, 77),                              # Renovação Solidária (PRD, Solidariedade)
}  # conferido com tse.jus.br/partidos/federacoes-registradas-no-tse em 05/10/2026


def partidos_federacao(numero: int, texto: str | None = None) -> tuple[int, ...]:
    """Números dos partidos da federação do candidato (ou só o do próprio partido)."""
    if texto:
        return tuple(int(x) for x in str(texto).replace(";", ",").split(",") if x.strip())
    p = partido_de(numero)
    return FEDERACOES_2026.get(p, (p,))


def _votos_por_municipio(cand: pd.DataFrame, g: pd.DataFrame, filtro) -> np.ndarray:
    c = cand[filtro(cand)]
    s = c.groupby("CD_MUNICIPIO")["QT_VOTOS"].sum()
    return s.reindex(g["CD_MUNICIPIO"]).fillna(0).to_numpy(float)


def _alinhar(gm, g: pd.DataFrame, vetor: np.ndarray) -> np.ndarray:
    """Leva um vetor alinhado a g para a ordem das linhas de gm (municípios sem dado = 0)."""
    idx = pd.Index(g["CD_MUNICIPIO"]).get_indexer(gm["CD_MUNICIPIO"].fillna(-1).astype(int))
    return np.where(idx >= 0, vetor[np.clip(idx, 0, None)], 0.0)


def _pct(v: np.ndarray, validos: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(validos > 0, 100 * v / validos, 0.0)


# --------------------------------------------------------------------------- 2. federação
def federacao(cand: pd.DataFrame, g: pd.DataFrame, numero: int, partidos: tuple[int, ...]) -> tuple[pd.DataFrame, dict]:
    validos = g["validos"].to_numpy(float)
    h = g["votos"].to_numpy(float)
    fed = _votos_por_municipio(cand, g, lambda c: partido_de(c["NR_VOTAVEL"]).isin(partidos))
    fed = np.maximum(fed, h)
    H, F = h.sum(), fed.sum()
    s = H / F if F else np.nan
    esperado = fed * s
    out = pd.DataFrame({
        "CD_MUNICIPIO": g["CD_MUNICIPIO"].to_numpy(), "fed_votos": fed,
        "fed_pct": _pct(fed, validos), "fed_outros_pct": _pct(fed - h, validos),
        "part_fed": np.where(fed > 0, 100 * h / np.where(fed > 0, fed, 1), np.nan),
        "esperado_fed": esperado, "dif_fed": esperado - h,
    })
    meta = {
        "fed_partidos": list(partidos), "fed_votos": float(F), "fed_pct_estado": float(100 * F / validos.sum()),
        "part_fed_estado": float(100 * s), "n_acima": int((h > esperado + 0.5).sum()),
        "n_abaixo": int(((h < esperado - 0.5) & (esperado >= 1)).sum()),
        "votos_a_mais": float(np.maximum(esperado - h, 0).sum()),
        "sem_colegas": bool(np.allclose(fed, h)),  # candidato é o único da federação (majoritários)
    }
    return out, meta


# --------------------------------------------------------------------------- 1. sobreposição
def sobreposicao(cand: pd.DataFrame, g: pd.DataFrame, gm, numero: int, comp: pd.DataFrame,
                 partidos: tuple[int, ...], permutacoes: int = 199) -> pd.DataFrame:
    """Compara a geografia do voto do candidato com a de cada outro candidato (o mais votado de cada partido)
    e com o resto da federação."""
    validos = g["validos"].to_numpy(float)
    h = g["votos"].to_numpy(float)
    h_pct, h_sh = _pct(h, validos), h / h.sum()
    alvos = []
    for r in comp[(~comp["foco"]) & comp["top_do_partido"] & (comp["votos"] >= 1000)].itertuples():
        v = _votos_por_municipio(cand, g, lambda c, n=r.numero: c["NR_VOTAVEL"] == n)
        alvos.append((r.nome, r.sigla, v, partido_de(int(r.numero)) in partidos, float(r.votos)))
    if True:
        fed = _votos_por_municipio(cand, g, lambda c: partido_de(c["NR_VOTAVEL"]).isin(partidos))
        resto = np.maximum(fed - h, 0)
        if resto.sum() > 0:
            rot = "/".join(metrics.SIGLAS.get(p, str(p)) for p in partidos)
            alvos.append(("Resto da federação" if len(partidos) > 1 else "Resto do partido", rot, resto, True,
                          float(resto.sum())))
    series_h = {"h": _alinhar(gm, g, h_pct)}
    bv = spatial.moran_bivariado(gm, series_h["h"], {i: _alinhar(gm, g, _pct(a[2], validos))
                                                      for i, a in enumerate(alvos)}, permutacoes)
    linhas = []
    for i, (nome, sigla, v, mesma, tot) in enumerate(alvos):
        p = _pct(v, validos)
        sh = v / v.sum() if v.sum() else v
        r = float(np.corrcoef(h_pct, p)[0, 1]) if p.std() > 0 and h_pct.std() > 0 else np.nan
        linhas.append({"nome": nome, "sigla": sigla, "votos": tot, "mesma_federacao": bool(mesma),
                       "correlacao": r, "sobreposicao": float(100 * np.minimum(h_sh, sh).sum()),
                       "moran_bv": bv[i][0], "moran_bv_p": bv[i][1]})
    return pd.DataFrame(linhas).sort_values("sobreposicao", ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------- 3. modelo
def modelo(g: pd.DataFrame, gm, fed: pd.DataFrame, permutacoes: int = 199) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Mínimos quadrados ponderados pelos votos válidos:
    % válidos ~ ln(eleitores) + abstenção + % do resto da federação + % do resto da federação nos vizinhos."""
    from esda import Moran
    from libpysal import weights

    d = g[["CD_MUNICIPIO", "votos", "validos", "eleitores", "abstencao_pct", "pct_validos"]].merge(
        fed[["CD_MUNICIPIO", "fed_outros_pct"]], on="CD_MUNICIPIO")
    gp = gm.to_crs(spatial.utm_crs(gm)).reset_index(drop=True)
    w = spatial.pesos_municipios(gp)
    ord_ = _alinhar(gm, d, d["fed_outros_pct"].to_numpy(float))
    viz_gm = weights.lag_spatial(w, ord_)
    viz = pd.Series(viz_gm, index=gm["CD_MUNICIPIO"].fillna(-1).astype(int).to_numpy())
    viz = viz[~viz.index.duplicated()]
    d["fed_viz_pct"] = d["CD_MUNICIPIO"].map(viz).fillna(0.0)
    d["ln_eleitores"] = np.log(d["eleitores"].clip(lower=1))
    d["abstencao_pct"] = d["abstencao_pct"].fillna(d["abstencao_pct"].median())
    cols = [c for c in ["ln_eleitores", "abstencao_pct", "fed_outros_pct", "fed_viz_pct"]
            if float(np.nanstd(d[c].to_numpy(float))) > 1e-9]  # coluna constante deixa a matriz singular
    rot = {"const": "Constante", "ln_eleitores": "Tamanho do eleitorado (logaritmo)", "abstencao_pct": "Abstenção (%)",
           "fed_outros_pct": "Votos do resto da federação no município (%)",
           "fed_viz_pct": "Votos do resto da federação nos vizinhos (%)"}
    y = d["pct_validos"].to_numpy(float)
    X = np.column_stack([np.ones(len(d))] + [d[c].to_numpy(float) for c in cols])
    wt = d["validos"].to_numpy(float).clip(min=1)
    sw = np.sqrt(wt)
    beta, *_ = np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)
    pred = X @ beta
    res = y - pred
    n, k = X.shape
    s2 = float((wt * res ** 2).sum() / (n - k))
    bread = np.linalg.inv((X * wt[:, None]).T @ X)
    se_cl = np.sqrt(np.diag(s2 * bread))
    # erro-padrão robusto a heterocedasticidade (HC1: White 1980; MacKinnon e White 1985)
    meat = (X * (wt * res)[:, None]).T @ (X * (wt * res)[:, None])
    se = np.sqrt(np.diag(bread @ meat @ bread * n / (n - k)))
    from scipy import stats
    t = beta / se
    pv = 2 * (1 - stats.t.cdf(np.abs(t), n - k))
    ybar = float((wt * y).sum() / wt.sum())
    r2 = 1 - float((wt * res ** 2).sum()) / float((wt * (y - ybar) ** 2).sum())
    # resíduo padronizado pela dispersão típica de municípios do mesmo porte (variância multiplicativa, Harvey 1976):
    # sem isso, o resíduo dos municípios grandes é sistematicamente maior e eles dominam a lista de destaques
    Zv = np.column_stack([np.ones(n), np.log(wt)])
    gam, *_ = np.linalg.lstsq(Zv, np.log(res ** 2 + 1e-10), rcond=None)
    z = res / np.sqrt(np.exp(Zv @ gam + 1.2704))
    coef = pd.DataFrame({"variavel": ["const"] + cols, "rotulo": [rot[c] for c in ["const"] + cols],
                         "coef": beta, "erro_padrao": se, "erro_padrao_classico": se_cl, "t": t, "p": pv})
    # padroniza o efeito: variação em pontos percentuais por desvio-padrão da variável
    sds = [np.nan] + [float(d[c].std()) for c in cols]
    coef["efeito_1dp"] = coef["coef"] * np.array(sds)
    mun = pd.DataFrame({"CD_MUNICIPIO": d["CD_MUNICIPIO"], "pct_previsto": pred, "residuo_pp": res, "z_residuo": z,
                        "votos_esperados": pred / 100 * d["validos"].to_numpy(float),
                        "dif_modelo": d["votos"].to_numpy(float) - pred / 100 * d["validos"].to_numpy(float)})
    z_gm = _alinhar(gm, mun, z)
    mo = Moran(z_gm, w, permutations=permutacoes)
    meta = {"r2": r2, "n": int(n), "moran_res": float(mo.I), "moran_res_p": float(mo.p_sim),
            "n_acima": int((z > 2).sum()), "n_abaixo": int((z < -2).sum())}
    return coef, mun, meta


# --------------------------------------------------------------------------- 4. distância
def distancia(g: pd.DataFrame, gm, k: int = 5) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Distância (km, em linha reta entre centroides) de cada município ao reduto mais próximo
    (os k municípios com mais votos) e queda da votação com o afastamento."""
    from scipy import stats

    gp = gm.to_crs(spatial.utm_crs(gm)).reset_index(drop=True)
    cen = gp.geometry.centroid
    xy = pd.DataFrame({"CD_MUNICIPIO": gm["CD_MUNICIPIO"].to_numpy(), "x": cen.x.to_numpy(), "y": cen.y.to_numpy()})
    xy = xy.dropna(subset=["CD_MUNICIPIO"]).copy()
    xy["CD_MUNICIPIO"] = xy["CD_MUNICIPIO"].astype(int)
    d = g[["CD_MUNICIPIO", "NM_MUNICIPIO", "votos", "validos", "pct_validos"]].merge(xy, on="CD_MUNICIPIO")
    top = d.sort_values("votos", ascending=False).head(k)
    P = d[["x", "y"]].to_numpy()
    T = top[["x", "y"]].to_numpy()
    D = np.sqrt(((P[:, None, :] - T[None, :, :]) ** 2).sum(axis=2)) / 1000.0
    d["dist_reduto_km"] = D.min(axis=1)
    d["reduto_proximo"] = top["NM_MUNICIPIO"].to_numpy()[D.argmin(axis=1)]
    d["dist_principal_km"] = D[:, 0]
    cortes = [-0.001, 0.001, 50, 100, 150, 200, 300, 1e9]
    rot = ["Reduto", "até 50 km", "50 a 100 km", "100 a 150 km", "150 a 200 km", "200 a 300 km", "mais de 300 km"]
    d["faixa"] = pd.cut(d["dist_reduto_km"], cortes, labels=rot)
    f = d.groupby("faixa", observed=False).agg(municipios=("CD_MUNICIPIO", "count"), votos=("votos", "sum"),
                                              validos=("validos", "sum")).reset_index()
    f["pct_validos"] = 100 * f["votos"] / f["validos"].replace(0, np.nan)
    f["share_votos"] = 100 * f["votos"] / f["votos"].sum()
    fora = d[d["dist_reduto_km"] > 0.001]
    rho, p = stats.spearmanr(fora["dist_reduto_km"], fora["pct_validos"])
    tot = d["votos"].sum()
    meta = {"k": int(k), "redutos": top["NM_MUNICIPIO"].tolist(),
            "spearman": float(rho), "spearman_p": float(p),
            "votos_ate_50": float(100 * d.loc[d["dist_reduto_km"] <= 50, "votos"].sum() / tot),
            "votos_ate_100": float(100 * d.loc[d["dist_reduto_km"] <= 100, "votos"].sum() / tot),
            "votos_ate_200": float(100 * d.loc[d["dist_reduto_km"] <= 200, "votos"].sum() / tot),
            "mun_voto_ate_100": int((d.loc[d["dist_reduto_km"] <= 100, "votos"] > 0).sum()),
            "n_mun": int(len(d))}
    return d[["CD_MUNICIPIO", "dist_reduto_km", "reduto_proximo", "dist_principal_km"]], f, meta


# --------------------------------------------------------------------------- orquestração
def rodar_todas(cand, g, gm, numero, comp, partidos, permutacoes=199) -> dict:
    fed, fed_meta = federacao(cand, g, numero, partidos)
    sob = sobreposicao(cand, g, gm, numero, comp, partidos, permutacoes)
    if fed_meta["sem_colegas"]:  # sem outros candidatos da federação, federação e modelo não se aplicam
        coef, mod_meta = None, {}
        mod_mun = pd.DataFrame({"CD_MUNICIPIO": g["CD_MUNICIPIO"].to_numpy()})
    else:
        try:
            coef, mod_mun, mod_meta = modelo(g, gm, fed, permutacoes)
        except np.linalg.LinAlgError:  # candidato com votos em poucos municípios: o modelo não se estima
            fed_meta["sem_colegas"] = True
            coef, mod_meta = None, {}
            mod_mun = pd.DataFrame({"CD_MUNICIPIO": g["CD_MUNICIPIO"].to_numpy()})
    dist_mun, bandas, dist_meta = distancia(g, gm)
    mun = fed.merge(mod_mun, on="CD_MUNICIPIO", how="left").merge(dist_mun, on="CD_MUNICIPIO", how="left")
    return {"mun": mun, "sobreposicao": sob, "modelo": coef, "bandas": bandas,
            "meta": {"federacao": fed_meta, "modelo": mod_meta, "distancia": dist_meta}}
