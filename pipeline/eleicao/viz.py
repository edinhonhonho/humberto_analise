"""Mapas e gráficos (PNG via matplotlib; mapa interativo via folium).

Paleta: rampa sequencial azul (uma matiz, claro -> escuro), divergente azul <-> vermelho com
meio cinza, e as três primeiras posições categóricas (azul, laranja, aqua), que são as que
validam em comparação par a par (mapas). Superfícies e tintas seguem o conjunto de referência.
"""
from __future__ import annotations

import json

import folium
import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

SURFACE, INK, INK2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, BASE, NEUTRAL, NODATA = "#e1e0d9", "#c3c2b7", "#f0efec", "#d9d8d1"
BLUE_RAMP = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5",
             "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]
SEQ = LinearSegmentedColormap.from_list("seq_blue", BLUE_RAMP)
C_BLUE, C_ORANGE, C_AQUA = "#2a78d6", "#eb6834", "#1baf7a"
DIV5 = ["#c23b3b", "#ec9b9a", NEUTRAL, "#86b6ef", "#1c5cab"]  # vermelho < neutro < azul
FONT = ["Segoe UI", "DejaVu Sans", "Arial"]

plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": FONT,
                     "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
                     "savefig.facecolor": SURFACE, "text.color": INK,
                     "axes.edgecolor": BASE, "axes.labelcolor": INK2,
                     "xtick.color": MUTED, "ytick.color": MUTED})


def fmt_num(x: float, dec: int | None = None) -> str:
    if pd.isna(x):
        return "–"
    if dec is None:
        dec = 0 if abs(x) >= 100 else 1
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_lim(x: float) -> str:
    """Limite de classe: mais casas decimais para valores pequenos."""
    if pd.isna(x):
        return "–"
    return fmt_num(x, 0 if abs(x) >= 100 else 1 if abs(x) >= 10 else 2)


def _title(ax, titulo, sub=None):
    ax.text(0, 1.045, titulo, transform=ax.transAxes, fontsize=13, fontweight="bold",
            color=INK, ha="left", va="bottom")
    if sub:
        ax.text(0, 1.005, sub, transform=ax.transAxes, fontsize=9, color=INK2, ha="left",
                va="bottom")


def _seq_colors(k: int):
    return [to_hex(SEQ(x)) for x in np.linspace(0.12, 1.0, k)]


def _quantile_edges(values, k=6, zero_class=False):
    v = np.asarray(values, float)
    v = v[np.isfinite(v)]
    if zero_class:
        v = v[v > 0]
    if v.size == 0:
        return np.array([0.0, 1.0])
    e = np.unique(np.quantile(v, np.linspace(0, 1, k + 1)))
    return e if e.size > 1 else np.array([e[0], e[0] + 1])


def _classify(values, edges, zero_class):
    v = np.asarray(values, float)
    idx = np.digitize(v, edges[1:-1], right=True)
    idx = np.where(np.isfinite(v), idx, -1)
    if zero_class:
        idx = np.where(v == 0, -2, idx)
    return idx


def _save(fig, path):
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return path


# --------------------------------------------------------------------------- mapas estaduais
def choropleth(gdf, col, titulo, path, sub=None, k=6, zero_class=False, unidade="", inteiro=False):
    """Coroplético sequencial por quantis (classes só entre valores > 0 se zero_class)."""
    edges = _quantile_edges(gdf[col], k, zero_class)
    n = len(edges) - 1
    cores = _seq_colors(n)
    idx = _classify(gdf[col], edges, zero_class)
    fc = [NODATA if i == -1 else (NEUTRAL if i == -2 else cores[min(i, n - 1)]) for i in idx]

    fig, ax = plt.subplots(figsize=(7.2, 7.4))
    gdf.plot(ax=ax, color=fc, edgecolor=SURFACE, linewidth=0.3)
    ax.set_axis_off()
    _title(ax, titulo, sub)
    handles = []
    if zero_class:
        handles.append(Patch(facecolor=NEUTRAL, edgecolor=BASE, label="sem votos"))
    for i in range(n):
        lo, hi = edges[i], edges[i + 1]
        f = (lambda x: fmt_num(x, 0)) if inteiro else fmt_lim
        handles.append(Patch(facecolor=cores[i], label=f"{f(lo)} – {f(hi)}{unidade}"))
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.02, 1.0), borderaxespad=0, frameon=False,
              fontsize=8.5, labelcolor=INK2, handlelength=1.2, handleheight=1.0)
    return _save(fig, path)


def choropleth_lq(gdf, titulo, path, sub=None):
    """Quociente locacional com classes divergentes em torno de 1."""
    cortes = [0.5, 0.8, 1.25, 2.0]
    rot = ["< 0,5 (muito abaixo da média)", "0,5 – 0,8", "0,8 – 1,25 (próximo da média)",
           "1,25 – 2,0", "> 2,0 (muito acima da média)"]
    v = gdf["quociente_locacional"].to_numpy(float)
    idx = np.digitize(v, cortes)
    fc = [NODATA if not np.isfinite(x) else DIV5[i] for x, i in zip(v, idx)]
    fig, ax = plt.subplots(figsize=(7.2, 7.4))
    gdf.plot(ax=ax, color=fc, edgecolor=SURFACE, linewidth=0.3)
    ax.set_axis_off()
    _title(ax, titulo, sub)
    ax.legend(handles=[Patch(facecolor=c, edgecolor=BASE, label=r) for c, r in zip(DIV5, rot)],
              loc="upper left", bbox_to_anchor=(1.02, 1.0), borderaxespad=0, frameon=False,
              fontsize=8.5, labelcolor=INK2)
    return _save(fig, path)


def lisa_map(gdf, titulo, path, sub=None):
    cores = {"Alto-Alto": C_BLUE, "Baixo-Baixo": C_ORANGE, "Outlier espacial": C_AQUA,
             "Não significativo": GRID}
    fig, ax = plt.subplots(figsize=(7.2, 7.4))
    gdf.plot(ax=ax, color=[cores[c] for c in gdf["lisa_cluster"]], edgecolor=SURFACE,
             linewidth=0.3)
    ax.set_axis_off()
    _title(ax, titulo, sub)
    cont = gdf["lisa_cluster"].value_counts()
    ax.legend(handles=[Patch(facecolor=c, edgecolor=BASE, label=f"{k} ({cont.get(k, 0)})")
                       for k, c in cores.items()],
              loc="upper left", bbox_to_anchor=(1.02, 1.0), borderaxespad=0, frameon=False,
              fontsize=8.5, labelcolor=INK2)
    return _save(fig, path)


# --------------------------------------------------------------------------- gráficos
def pareto_chart(par: pd.DataFrame, res: dict, titulo, path):
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.plot(par["n_municipios"], par["cum_share"], color=C_BLUE, lw=2)
    ax.set_xlim(0, min(len(par), max(60, res["n_para_80"] * 3)))
    ax.set_ylim(0, 102)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for n, alvo in ((res["n_para_50"], 50), (res["n_para_80"], 80)):
        ax.plot([n], [alvo], "o", ms=8, color=C_BLUE, mec=SURFACE, mew=2, zorder=5)
        ax.annotate(f"{n} município(s) somam {alvo}%", (n, alvo), xytext=(10, -14),
                    textcoords="offset points", fontsize=9, color=INK)
    ax.set_xlabel("Municípios, do mais votado ao menos votado", fontsize=9)
    ax.set_ylabel("% acumulado dos votos do candidato", fontsize=9)
    _title(ax, titulo)
    return _save(fig, path)


def barh_top(g, col, titulo, path, n=15, unidade="", sub=None):
    d = g.nlargest(n, col).iloc[::-1]
    fig, ax = plt.subplots(figsize=(7.2, 0.34 * n + 1.2))
    ax.barh(d["NM_MUNICIPIO"].str.title(), d[col], color=C_BLUE, height=0.62)
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.tick_params(axis="y", length=0, labelcolor=INK2, labelsize=9)
    ax.set_xlabel(unidade, fontsize=9)
    _title(ax, titulo, sub)
    return _save(fig, path)


# --------------------------------------------------------------------------- mapas de cidade
def _city_frame(ax, muni_geom, cells):
    if muni_geom is not None:
        gpd.GeoSeries([muni_geom], crs=4326).plot(ax=ax, color=NEUTRAL, edgecolor=BASE, lw=0.8)
    minx, miny, maxx, maxy = cells.total_bounds
    dx, dy = (maxx - minx) * 0.08 + 1e-3, (maxy - miny) * 0.08 + 1e-3
    ax.set_xlim(minx - dx, maxx + dx)
    ax.set_ylim(miny - dy, maxy + dy)
    ax.set_aspect(1 / np.cos(np.radians((miny + maxy) / 2)))
    ax.set_axis_off()


def city_cells_map(nome, muni_geom, cells, path, col="pct_validos", k=5):
    d = cells.dropna(subset=[col])
    edges = _quantile_edges(d[col], k)
    n = len(edges) - 1
    cores = _seq_colors(n)
    idx = _classify(cells[col], edges, False)
    fc = [NODATA if i < 0 else cores[min(i, n - 1)] for i in idx]
    fig, ax = plt.subplots(figsize=(7.2, 6.4))
    _city_frame(ax, muni_geom, cells)
    cells.plot(ax=ax, color=fc, edgecolor=SURFACE, linewidth=0.5)
    _title(ax, f"{nome}: % de votos válidos por hexágono", "Locais de votação agregados em H3")
    ax.legend(handles=[Patch(facecolor=cores[i], label=f"{fmt_lim(edges[i])} – "
                             f"{fmt_lim(edges[i + 1])}%") for i in range(n)],
              loc="upper left", bbox_to_anchor=(1.02, 1.0), borderaxespad=0, frameon=False,
              fontsize=8.5, labelcolor=INK2)
    return _save(fig, path)


def city_gi_map(nome, muni_geom, cells, path):
    cores = {"Ponto quente": C_BLUE, "Ponto frio": C_ORANGE, "Não significativo": GRID,
             "Sem dados suficientes": NODATA}
    fig, ax = plt.subplots(figsize=(7.2, 6.4))
    _city_frame(ax, muni_geom, cells)
    cells.plot(ax=ax, color=[cores[c] for c in cells["gi_classe"]], edgecolor=SURFACE,
               linewidth=0.5)
    _title(ax, f"{nome}: pontos quentes e frios (Getis-Ord Gi*)",
           "Concentração espacial da % de votos válidos, p < 0,05")
    cont = cells["gi_classe"].value_counts()
    ax.legend(handles=[Patch(facecolor=c, edgecolor=BASE, label=f"{k} ({cont.get(k, 0)})")
                       for k, c in cores.items()],
              loc="upper left", bbox_to_anchor=(1.02, 1.0), borderaxespad=0, frameon=False,
              fontsize=8.5, labelcolor=INK2)
    return _save(fig, path)


def mapa_interativo(nome, muni_geom, locais, cells) -> str | None:
    """Mapa Leaflet (folium) com locais de votação e hexágonos. Devolve o HTML completo."""
    pts = locais.dropna(subset=["lat", "lon"])
    if pts.empty:
        return None
    m = folium.Map(location=[pts["lat"].mean(), pts["lon"].mean()], zoom_start=12,
                   tiles="CartoDB positron", control_scale=True)
    if muni_geom is not None:
        folium.GeoJson(json.loads(gpd.GeoSeries([muni_geom], crs=4326).to_json()),
                       style_function=lambda _: {"fillOpacity": 0, "color": "#52514e",
                                                 "weight": 1.2},
                       name="Limite municipal").add_to(m)
    if cells is not None and len(cells):
        cmap = {"Ponto quente": C_BLUE, "Ponto frio": C_ORANGE, "Não significativo": GRID,
                "Sem dados suficientes": NODATA}
        c = cells[["geometry", "pct_validos", "votos", "validos", "gi_classe"]].copy()
        c["pct_validos"] = c["pct_validos"].round(2).fillna(0)
        folium.GeoJson(
            json.loads(c.to_json()), name="Hexágonos (Gi*)",
            style_function=lambda f: {"fillColor": cmap.get(f["properties"]["gi_classe"], GRID),
                                      "color": SURFACE, "weight": 0.6, "fillOpacity": 0.55},
            tooltip=folium.GeoJsonTooltip(
                fields=["gi_classe", "votos", "validos", "pct_validos"],
                aliases=["Classe", "Votos", "Votos válidos", "% válidos"])).add_to(m)
    edges = _quantile_edges(pts["pct_validos"], 5)
    cores = _seq_colors(len(edges) - 1)
    fg = folium.FeatureGroup(name="Locais de votação", show=True)
    vmax = max(pts["votos"].max(), 1)
    for r in pts.itertuples():
        i = 0 if pd.isna(r.pct_validos) else int(np.digitize(r.pct_validos, edges[1:-1],
                                                            right=True))
        folium.CircleMarker(
            [r.lat, r.lon], radius=3 + 11 * np.sqrt(r.votos / vmax), weight=1.5, color=SURFACE,
            fill=True, fill_color=to_hex(cores[min(i, len(cores) - 1)]), fill_opacity=0.9,
            tooltip=folium.Tooltip(
                f"<b>{r.local_nome}</b><br>{r.bairro}<br>{int(r.votos)} votos · "
                f"{fmt_num(r.pct_validos, 1)}% dos válidos<br>{int(r.eleitores) if pd.notna(r.eleitores) else '–'}"
                f" eleitores · {int(r.secoes)} seções")).add_to(fg)
    fg.add_to(m)
    folium.LayerControl(collapsed=True).add_to(m)
    return m.get_root().render()


def to_hex(rgba) -> str:
    if isinstance(rgba, str):
        return rgba
    return "#%02x%02x%02x" % tuple(int(round(255 * c)) for c in rgba[:3])
