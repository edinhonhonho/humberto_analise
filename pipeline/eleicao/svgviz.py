"""Gráficos SVG interativos (sem dependências externas, claro/escuro).

Cada gráfico é um trecho de HTML autocontido; as cores vêm de variáveis CSS definidas em
report.CSS, então trocam sozinhas entre os temas. Rótulos entram no DOM por textContent.
"""
from __future__ import annotations

import html
import json
import math

import numpy as np

SEQ_STEPS = ["s1", "s2", "s3", "s4", "s5", "s6"]


# ------------------------------------------------------------------ formatação pt-BR
def fnum(x, dec: int = 0) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "–"
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fdyn(x: float) -> str:
    """Número com casas conforme a magnitude (limites de classe)."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    a = abs(x)
    return fnum(x, 0 if a >= 100 else 1 if a >= 10 else 2 if a >= 0.1 else 3)


def esc(s) -> str:
    return html.escape(str(s), quote=True)


# ------------------------------------------------------------------ projeção e caminhos
class Proj:
    """Projeção plana simples (equiretangular corrigida pelo cosseno da latitude média)."""

    def __init__(self, bounds, width: float = 760, pad: float = 6):
        minx, miny, maxx, maxy = bounds
        self.k = math.cos(math.radians((miny + maxy) / 2))
        self.minx, self.maxy, self.pad = minx, maxy, pad
        wu = max((maxx - minx) * self.k, 1e-9)
        hu = max(maxy - miny, 1e-9)
        self.s = (width - 2 * pad) / wu
        self.W = width
        self.H = hu * self.s + 2 * pad

    def xy(self, lon, lat):
        return (self.pad + (lon - self.minx) * self.k * self.s, self.pad + (self.maxy - lat) * self.s)


def _ring(coords, proj: Proj) -> str:
    pts, last = [], None
    for lon, lat in coords:
        x, y = proj.xy(lon, lat)
        p = (round(x, 1), round(y, 1))
        if p != last:
            pts.append(p)
            last = p
    if len(pts) < 3:
        return ""
    return "M" + "L".join(f"{x:g} {y:g}" for x, y in pts) + "Z"


def geom_path(geom, proj: Proj) -> str:
    if geom is None or geom.is_empty:
        return ""
    polys = []
    if geom.geom_type == "Polygon":
        polys = [geom]
    elif geom.geom_type in ("MultiPolygon", "GeometryCollection"):
        polys = [g for g in geom.geoms if g.geom_type == "Polygon"]
    parts = []
    for p in polys:
        parts.append(_ring(p.exterior.coords, proj))
        parts += [_ring(r.coords, proj) for r in p.interiors]
    return "".join(x for x in parts if x)


# ------------------------------------------------------------------ classificação
def classes_quantil(values, k: int = 6, unit: str = "", inteiro: bool = False):
    """Classes por quantil entre os valores > 0. Zero -> 'z'; ausente -> 'nd'.
    Devolve (lista de classes por valor, legenda [(classe, rótulo)])."""
    v = np.asarray(values, float)
    pos = v[np.isfinite(v) & (v > 0)]
    f = (lambda x: fnum(x, 0)) if inteiro else fdyn
    if pos.size == 0:
        cls = ["nd" if not np.isfinite(x) else "z" for x in v]
        return cls, [("z", "sem votos")]
    edges = np.unique(np.quantile(pos, np.linspace(0, 1, k + 1)))
    if edges.size < 2:
        edges = np.array([edges[0], edges[0] + 1e-9])
    n = len(edges) - 1
    steps = [SEQ_STEPS[int(round(i))] for i in np.linspace(0, len(SEQ_STEPS) - 1, n)] \
        if n > 1 else [SEQ_STEPS[3]]
    idx = np.digitize(v, edges[1:-1], right=True)
    cls = []
    for x, i in zip(v, idx):
        cls.append("nd" if not np.isfinite(x) else "z" if x <= 0 else steps[min(int(i), n - 1)])
    legend = [("z", "sem votos")] if (v == 0).any() else []
    for i in range(n):
        lo, hi = edges[i], edges[i + 1]
        legend.append((steps[i], f"{f(lo)} – {f(hi)}{unit}"))
    if (~np.isfinite(v)).any():
        legend.append(("nd", "sem dado"))
    return cls, legend


def classes_ql(values):
    """Quociente locacional ancorado em 1 (= igual à média do estado)."""
    cortes = [(1, "s1", "abaixo da média (< 1)"), (2, "s3", "1 a 2 vezes a média"),
              (5, "s4", "2 a 5 vezes"), (10, "s5", "5 a 10 vezes"), (float("inf"), "s6", "mais de 10 vezes")]
    cls = []
    for x in np.asarray(values, float):
        if not np.isfinite(x):
            cls.append("nd")
        elif x <= 0:
            cls.append("z")
        else:
            cls.append(next(c for lim, c, _ in cortes if x < lim))
    legend = [("z", "sem votos")] + [(c, r) for _, c, r in cortes]
    return cls, legend


def classes_categoria(values, mapa: dict, ordem: list):
    """Classes categóricas: mapa {valor: classe css}; legenda na ordem dada, com contagem."""
    cls = [mapa.get(v, "nd") for v in values]
    cont = {}
    for v in values:
        cont[v] = cont.get(v, 0) + 1
    legend = [(mapa[o], f"{o} ({cont.get(o, 0)})") for o in ordem if o in mapa]
    return cls, legend


# ------------------------------------------------------------------ geometria compartilhada
def geo_defs(polys: list[dict]) -> str:
    """Traçados dos municípios, definidos uma vez por página; os mapas os reutilizam com <use>."""
    ps = "".join(f'<path id="g{p["id"]}" d="{p["d"]}" vector-effect="non-scaling-stroke"/>'
                 for p in polys if p.get("id") is not None and p["d"])
    return f'<svg class="defs" width="0" height="0" aria-hidden="true" focusable="false"><defs>{ps}</defs></svg>'


# ------------------------------------------------------------------ mapa interativo
def map_card(uid: str, polys: list[dict], metrics: list[dict], proj: Proj, points=None,
             aria: str = "Mapa", pts_label: str = "Mostrar locais de votação", bg: str = "") -> str:
    """polys: [{d, tip: [titulo, [[rotulo, valor], ...]], cls: [classe por métrica]}]
    metrics: [{key, label, note, legend: [(classe, rótulo)]}]
    points: [{x, y, r, tip}] (opcional)"""
    paths = []
    for p in polys:
        tip = esc(json.dumps(p["tip"], ensure_ascii=False))
        if p.get("id") is not None:   # geometria compartilhada: o traçado fica em <defs> (geo_defs)
            paths.append(f'<use href="#g{p["id"]}" class="p k-{p["cls"][0]}" data-id="{p["id"]}" '
                         f'data-k="{" ".join(p["cls"])}" data-tip="{tip}"/>')
        else:
            paths.append(f'<path class="p k-{p["cls"][0]}" d="{p["d"]}" data-k="{" ".join(p["cls"])}" data-tip="{tip}"/>')
    pts = ""
    if points:
        pts = '<g class="pts" hidden>' + "".join(
            f'<circle class="pt" cx="{q["x"]:.1f}" cy="{q["y"]:.1f}" r="{q["r"]:.1f}" '
            f'data-tip="{esc(json.dumps(q["tip"], ensure_ascii=False))}"/>' for q in points) + "</g>"
    leg0 = "".join(f'<li><i class="sw k-{c}"></i>{esc(l)}</li>' for c, l in metrics[0]["legend"])
    bgs = f'<path class="bg" d="{bg}"/>' if bg else ""
    cfg = {"metrics": [{"key": m["key"], "label": m["label"], "note": m.get("note", ""),
                        "legend": m["legend"]} for m in metrics]}
    seg = "".join(f'<button type="button" role="radio" aria-checked="{"true" if i == 0 else "false"}" '
                  f'data-m="{i}">{esc(m["label"])}</button>' for i, m in enumerate(metrics))
    chk = (f'<label class="chk"><input type="checkbox" class="showpts"> {esc(pts_label)}</label>'
           if points else "")
    return (f'<div class="mapcard" id="{uid}"><div class="mapmain">'
            f'<svg class="map" viewBox="0 0 {proj.W:g} {proj.H:.0f}" role="img" aria-label="{esc(aria)}">'
            f'{bgs}<g class="polys">{"".join(paths)}</g>{pts}</svg></div>'
            f'<aside class="mapside"><div class="seg" role="radiogroup" aria-label="Métrica do mapa">{seg}</div>'
            f'<p class="note mnote">{esc(metrics[0].get("note", ""))}</p><ul class="legend">{leg0}</ul>{chk}</aside>'
            f'<script type="application/json" class="mcfg">{json.dumps(cfg, ensure_ascii=False)}</script></div>')


# ------------------------------------------------------------------ barras horizontais
def bar_chart(rows: list[dict], aria: str, unit: str = "", width: float = 760) -> str:
    """rows: [{label, value, tip: [titulo, [[rotulo, valor]...]], fmt}] já ordenadas."""
    if not rows:
        return ""
    lab_w = min(230, max(80, 7.2 * max(len(r["label"]) for r in rows) + 18))
    right = 70
    bh, gap = 22, 10
    top = 4
    H = top + len(rows) * (bh + gap)
    vmax = max(r["value"] for r in rows) or 1
    plot_w = width - lab_w - right
    out = [f'<svg class="bars" viewBox="0 0 {width:g} {H}" role="img" aria-label="{esc(aria)}">']
    for i, r in enumerate(rows):
        y = top + i * (bh + gap)
        w = max(2.0, plot_w * r["value"] / vmax)
        x0 = lab_w
        rr = min(4, w / 2)
        d = (f"M{x0} {y}H{x0 + w - rr}Q{x0 + w} {y} {x0 + w} {y + rr}V{y + bh - rr}"
             f"Q{x0 + w} {y + bh} {x0 + w - rr} {y + bh}H{x0}Z")
        out.append(f'<g class="row{" hl" if r.get("hl") else ""}" data-tip="{esc(json.dumps(r["tip"], ensure_ascii=False))}">'
                   f'<rect class="hit" x="0" y="{y - gap / 2}" width="{width:g}" height="{bh + gap}"/>'
                   f'<text class="lab" x="{lab_w - 8}" y="{y + bh / 2 + 4}" text-anchor="end">{esc(r["label"])}</text>'
                   f'<path class="bar" d="{d}"/>'
                   f'<text class="val" x="{x0 + w + 6}" y="{y + bh / 2 + 4}">{esc(r["fmt"])}{esc(unit)}</text></g>')
    out.append("</svg>")
    return "".join(out)


# ------------------------------------------------------------------ Pareto (linha com crosshair)
def pareto_chart(series: list[list], marcos: list[dict], xmax: int, width: float = 760,
                 height: float = 300) -> str:
    """series: [[rank, nome, votos, acumulado%], ...]; marcos: [{x, y, rotulo}]."""
    ml, mr, mt, mb = 44, 22, 12, 34
    pw, ph = width - ml - mr, height - mt - mb
    sx = lambda x: ml + pw * (x - 1) / max(xmax - 1, 1)  # noqa: E731
    sy = lambda y: mt + ph * (1 - y / 100)  # noqa: E731
    pts = [(sx(r[0]), sy(r[3])) for r in series if r[0] <= xmax]
    line = "M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
    area = line + f"L{pts[-1][0]:.1f} {sy(0):.1f}L{pts[0][0]:.1f} {sy(0):.1f}Z"
    g = []
    for v in (0, 25, 50, 75, 100):
        g.append(f'<line class="grid" x1="{ml}" x2="{width - mr}" y1="{sy(v):.1f}" y2="{sy(v):.1f}"/>'
                 f'<text class="tick" x="{ml - 8}" y="{sy(v) + 4:.1f}" text-anchor="end">{v}%</text>')
    step = 1 if xmax <= 12 else 5 if xmax <= 60 else 10 if xmax <= 150 else 50
    xt = [1] + [x for x in range(step, xmax + 1, step) if x != 1]
    for x in xt:
        g.append(f'<text class="tick" x="{sx(x):.1f}" y="{height - 12}" text-anchor="middle">{x}</text>')
    mk = []
    for m in marcos:
        if m["x"] > xmax:
            continue
        cx, cy = sx(m["x"]), sy(m["y"])
        anchor = "start" if cx < width * 0.65 else "end"
        dx = 12 if anchor == "start" else -12
        mk.append(f'<circle class="dot" cx="{cx:.1f}" cy="{cy:.1f}" r="5"/>'
                  f'<text class="dl" x="{cx + dx:.1f}" y="{cy + 18:.1f}" text-anchor="{anchor}">{esc(m["rotulo"])}</text>')
    data = json.dumps({"s": [r for r in series if r[0] <= xmax], "ml": ml, "pw": pw, "mt": mt, "ph": ph,
                       "xmax": xmax, "w": width, "h": height}, ensure_ascii=False)
    return (f'<div class="pareto"><svg viewBox="0 0 {width:g} {height:g}" role="img" '
            f'aria-label="Curva de concentração: percentual acumulado dos votos por município">'
            f'{"".join(g)}<path class="area" d="{area}"/><path class="ln" d="{line}"/>{"".join(mk)}'
            f'<g class="xh" hidden><line class="xl" y1="{mt}" y2="{mt + ph}"/><circle class="dot" r="5"/></g>'
            f'<rect class="cap" x="{ml}" y="{mt}" width="{pw}" height="{ph}" fill="transparent"/></svg>'
            f'<div class="axcap">Municípios, do mais votado ao menos votado</div>'
            f'<script type="application/json" class="pdat">{data}</script></div>')
