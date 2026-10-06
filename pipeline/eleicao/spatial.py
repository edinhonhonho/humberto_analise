"""Estatística espacial: Moran/LISA entre municípios; H3 e Getis-Ord Gi* dentro das cidades."""
from __future__ import annotations

import warnings

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
from shapely.geometry import Polygon

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

LISA_LABELS = {"hh": "Alto-Alto", "ll": "Baixo-Baixo", "out": "Outlier espacial",
               "ns": "Não significativo"}


def utm_crs(gdf: gpd.GeoDataFrame):
    return gdf.estimate_utm_crs()


# --------------------------------------------------------------------------- 3. Moran / LISA
_PESOS: dict = {}


def pesos_municipios(gp):
    """Vizinhança Queen (KNN 5 se houver ilhas), linha-padronizada. A construção é lenta e depende só da
    geometria, então os vizinhos ficam em cache; cada chamada recebe um objeto novo."""
    from libpysal import weights
    key = (len(gp), hash(gp.geometry.bounds.round(3).to_numpy().tobytes()))
    if key not in _PESOS:
        w = weights.Queen.from_dataframe(gp, use_index=False)
        if w.islands:
            w = weights.KNN.from_dataframe(gp, k=5)
        _PESOS[key] = {k: list(v) for k, v in w.neighbors.items()}
    w = weights.W({k: list(v) for k, v in _PESOS[key].items()})
    w.transform = "r"
    return w


def lisa_municipal(mun: gpd.GeoDataFrame, col: str, permutacoes: int = 999, seed: int = 42):
    """Moran global e local (LISA) de `col` entre municípios vizinhos (Queen)."""
    from esda import Moran, Moran_Local
    from libpysal import weights

    gp = mun.to_crs(utm_crs(mun)).reset_index(drop=True)
    y = gp[col].astype(float).fillna(0).to_numpy()
    w = pesos_municipios(gp)
    if np.allclose(y, y[0]):
        return (mun.assign(lisa_cluster="Não significativo", lisa_detalhe="", lisa_p=np.nan),
                {"I": np.nan, "p": np.nan})

    mo = Moran(y, w, permutations=permutacoes)
    lo = Moran_Local(y, w, permutations=permutacoes, seed=seed)
    sig = lo.p_sim < 0.05
    cl = np.full(len(y), LISA_LABELS["ns"], dtype=object)
    cl[sig & (lo.q == 1)] = LISA_LABELS["hh"]
    cl[sig & (lo.q == 3)] = LISA_LABELS["ll"]
    cl[sig & np.isin(lo.q, [2, 4])] = LISA_LABELS["out"]
    det = np.full(len(y), "", dtype=object)
    det[sig & (lo.q == 1)] = "Forte e cercado de vizinhos fortes"
    det[sig & (lo.q == 3)] = "Fraco e cercado de vizinhos fracos"
    det[sig & (lo.q == 4)] = "Forte em meio a vizinhos fracos"
    det[sig & (lo.q == 2)] = "Fraco em meio a vizinhos fortes"
    out = mun.reset_index(drop=True).assign(lisa_cluster=cl, lisa_detalhe=det, lisa_I=lo.Is,
                                            lisa_p=lo.p_sim)
    stats = {"I": float(mo.I), "p": float(mo.p_sim), "z": float(mo.z_sim),
             "n_hh": int((cl == LISA_LABELS["hh"]).sum()),
             "n_ll": int((cl == LISA_LABELS["ll"]).sum()),
             "n_out": int((cl == LISA_LABELS["out"]).sum())}
    return out, stats


# --------------------------------------------------------------------------- 4. dentro da cidade
def agregar_locais(mc: pd.DataFrame) -> pd.DataFrame:
    """Seções de um município -> locais de votação (escola, ginásio etc.)."""
    chave = ["NR_ZONA", "NR_LOCAL_VOTACAO", "local_nome"]
    g = mc.groupby(chave, as_index=False).agg(
        bairro=("bairro", "first"), endereco=("endereco", "first"),
        lat=("lat", "median"), lon=("lon", "median"), secoes=("NR_SECAO", "count"),
        votos=("v_cand", "sum"), validos=("v_validos", "sum"),
        eleitores=("eleitores", "sum"), comparecimento=("v_total", "sum"))
    g["pct_validos"] = 100 * g["votos"] / g["validos"].where(g["validos"] > 0)
    g["votos_por_100_aptos"] = 100 * g["votos"] / g["eleitores"].where(g["eleitores"] > 0)
    return g.sort_values("votos", ascending=False).reset_index(drop=True)


def agregar_zonas(mc: pd.DataFrame) -> pd.DataFrame:
    """Votos por zona eleitoral (as zonas não têm polígono público; ficam como tabela)."""
    g = mc.groupby("NR_ZONA", as_index=False).agg(
        locais=("local_nome", "nunique"), secoes=("NR_SECAO", "count"),
        votos=("v_cand", "sum"), validos=("v_validos", "sum"), eleitores=("eleitores", "sum"))
    g["pct_validos"] = 100 * g["votos"] / g["validos"].where(g["validos"] > 0)
    g["votos_por_100_aptos"] = 100 * g["votos"] / g["eleitores"].where(g["eleitores"] > 0)
    g["share_votos_cidade"] = 100 * g["votos"] / g["votos"].sum() if g["votos"].sum() else np.nan
    return g.sort_values("votos", ascending=False).reset_index(drop=True)


def agregar_bairros(mc: pd.DataFrame) -> pd.DataFrame:
    """Votos por bairro do LOCAL DE VOTAÇÃO (não do domicílio do eleitor)."""
    g = mc.groupby("bairro", as_index=False).agg(
        locais=("local_nome", "nunique"), secoes=("NR_SECAO", "count"),
        votos=("v_cand", "sum"), validos=("v_validos", "sum"), eleitores=("eleitores", "sum"))
    g["pct_validos"] = 100 * g["votos"] / g["validos"].where(g["validos"] > 0)
    g["votos_por_100_aptos"] = 100 * g["votos"] / g["eleitores"].where(g["eleitores"] > 0)
    g["share_votos_cidade"] = 100 * g["votos"] / g["votos"].sum() if g["votos"].sum() else np.nan
    return g.sort_values("votos", ascending=False).reset_index(drop=True)


def _h3_cell(lat, lng, res):
    if hasattr(h3, "latlng_to_cell"):
        return h3.latlng_to_cell(lat, lng, res)
    return h3.geo_to_h3(lat, lng, res)  # h3 v3


def _h3_polygon(cell) -> Polygon:
    pts = h3.cell_to_boundary(cell) if hasattr(h3, "cell_to_boundary") \
        else h3.h3_to_geo_boundary(cell)
    return Polygon([(lng, lat) for lat, lng in pts])


def validar_pontos(locais: pd.DataFrame, geom, folga_graus: float = 0.03):
    """Descarta coordenadas que caem fora do município (com folga de ~3 km). Erros de
    geocodificação são comuns nos dados do TSE. Devolve (locais, n_descartados)."""
    from shapely.geometry import Point
    if geom is None or locais["lat"].notna().sum() == 0:
        return locais, 0
    area = geom.buffer(folga_graus)
    out = locais.copy()
    tem = out["lat"].notna() & out["lon"].notna()
    dentro = np.array([area.contains(Point(x, y)) for x, y in zip(out.loc[tem, "lon"],
                                                                    out.loc[tem, "lat"])])
    idx = out.index[tem][~dentro]
    out.loc[idx, ["lat", "lon"]] = np.nan
    return out, int(len(idx))


H3_AREA_KM2 = {5: 252.9, 6: 36.1, 7: 5.16, 8: 0.737, 9: 0.105}


def escolher_res(d: pd.DataFrame, alvo: float = 2.0, minimo: int = 10) -> int:
    """Maior resolução H3 em que, em média, cada hexágono reúne ao menos `alvo` locais de
    votação (e há pelo menos `minimo` hexágonos). Cidades grandes ganham hexágonos menores."""
    for r in (9, 8, 7, 6):
        n = len({_h3_cell(la, lo, r) for la, lo in zip(d["lat"], d["lon"])})
        if n >= minimo and len(d) / n >= alvo:
            return r
    return 6


def celulas_h3(locais: pd.DataFrame, res="auto") -> gpd.GeoDataFrame | None:
    """Agrega os locais com coordenada válida em hexágonos H3."""
    d = locais.dropna(subset=["lat", "lon"]).copy()
    if d.empty:
        return None
    if res in (None, "auto"):
        res = escolher_res(d)
    res = int(res)
    d["h3"] = [_h3_cell(la, lo, res) for la, lo in zip(d["lat"], d["lon"])]
    d = d.sort_values("votos", ascending=False)

    def top(x):
        return "; ".join(f"{n} ({int(v)})" for n, v in zip(x["local_nome"].head(3), x["votos"].head(3)))

    c = d.groupby("h3", as_index=False).agg(
        locais=("local_nome", "count"), votos=("votos", "sum"), validos=("validos", "sum"),
        eleitores=("eleitores", "sum"),
        zonas=("NR_ZONA", lambda z: ", ".join(str(int(v)) for v in sorted(set(z)))))
    c["locais_top"] = c["h3"].map(d.groupby("h3").apply(top, include_groups=False))
    c["pct_validos"] = 100 * c["votos"] / c["validos"].where(c["validos"] > 0)
    c["votos_por_100_aptos"] = 100 * c["votos"] / c["eleitores"].where(c["eleitores"] > 0)
    out = gpd.GeoDataFrame(c, geometry=[_h3_polygon(x) for x in c["h3"]], crs=4326)
    out.attrs["res"] = res
    out.attrs["area_km2"] = H3_AREA_KM2.get(res)
    return out


def gi_star(cells: gpd.GeoDataFrame, col: str = "pct_validos", min_validos: int = 30,
            k: int = 6, permutacoes: int = 999, seed: int = 42) -> gpd.GeoDataFrame:
    """Getis-Ord Gi* sobre os hexágonos (vizinhos = k mais próximos). Hexágonos com poucos
    votos válidos ficam fora da estatística para não gerar ruído."""
    from esda import G_Local
    from libpysal import weights

    attrs = dict(cells.attrs)
    cells = cells.copy()
    cells.attrs.update(attrs)
    cells["gi_classe"] = "Sem dados suficientes"
    cells["gi_z"] = np.nan
    sub = cells[cells["validos"] >= min_validos]
    if len(sub) < 10:
        return cells
    pts = gpd.GeoDataFrame(sub[[col]].copy(), geometry=sub.to_crs(utm_crs(sub)).geometry.centroid,
                           crs=utm_crs(sub))
    w = weights.KNN.from_dataframe(pts, k=min(k, len(pts) - 1))
    y = pts[col].astype(float).fillna(0).to_numpy()
    if np.allclose(y, y[0]):
        return cells
    g = G_Local(y, w, transform="B", star=True, permutations=permutacoes, seed=seed)
    sig = g.p_sim < 0.05
    cl = np.full(len(y), "Não significativo", dtype=object)
    cl[sig & (g.Zs > 0)] = "Ponto quente"
    cl[sig & (g.Zs < 0)] = "Ponto frio"
    cells.loc[sub.index, "gi_classe"] = cl
    cells.loc[sub.index, "gi_z"] = g.Zs
    return cells


# --------------------------------------------------------------------------- Moran de vários candidatos
def moran_varios(mun: gpd.GeoDataFrame, series: dict, permutacoes: int = 199, seed: int = 42) -> dict:
    """Moran global de várias variáveis (uma por candidato) sobre os mesmos vizinhos Queen.
    series: {chave: vetor alinhado às linhas de `mun`}. Devolve {chave: (I, p)}."""
    from esda import Moran
    from libpysal import weights

    gp = mun.to_crs(utm_crs(mun)).reset_index(drop=True)
    w = pesos_municipios(gp)
    out = {}
    for k, y in series.items():
        y = np.asarray(y, dtype=float)
        if not np.isfinite(y).all() or np.allclose(y, y[0]):
            out[k] = (np.nan, np.nan)
            continue
        np.random.seed(seed)
        mo = Moran(y, w, permutations=permutacoes)
        out[k] = (float(mo.I), float(mo.p_sim))
    return out


def moran_bivariado(mun: gpd.GeoDataFrame, x, ys: dict, permutacoes: int = 199, seed: int = 42) -> dict:
    """Moran bivariado: a variável x de cada município contra a média de y nos vizinhos.
    Positivo = onde y é alto na vizinhança, x tende a ser alto. Devolve {chave: (I, p)}."""
    from esda import Moran_BV
    from libpysal import weights

    gp = mun.to_crs(utm_crs(mun)).reset_index(drop=True)
    w = pesos_municipios(gp)
    x = np.asarray(x, dtype=float)
    out = {}
    for k, y in ys.items():
        y = np.asarray(y, dtype=float)
        if x.std() == 0 or y.std() == 0:
            out[k] = (np.nan, np.nan)
            continue
        np.random.seed(seed)
        m = Moran_BV(x, y, w, permutations=permutacoes)
        out[k] = (float(m.I), float(m.p_sim))
    return out
