"""Monta as páginas do relatório (HTML) a partir do pacote intermediário; site.py grava os arquivos."""
from __future__ import annotations

import html
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import bundle, svgviz
from .conteudo import GUIA, GUIA_HEX, INTRO, NOTAS, PARTES, REFS
from .svgviz import esc, fdyn, fnum

_USADAS: list[str] = []
PEQUENAS = {"de", "da", "do", "das", "dos", "e"}


def nome_pt(s) -> str:
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return "–"
    ws = str(s).lower().split(" ")
    return " ".join(w if (i and w in PEQUENAS) else "-".join(p.capitalize() for p in w.split("-"))
                    for i, w in enumerate(ws))


# Foice e martelo: ícone "hammer-sickle" do Material Design Icons (Pictogrammers), licença Apache 2.0
HS_PATH = "M22 20.59L20.59 22l-3.14-3.14c-.56.37-1.15.7-1.79.92c-1.66.58-3.46.62-5.13.1c-1.03-.3-1.97-.83-2.78-1.51l-3.19 3.19c-.56.59-1.53.59-2.12 0c-.58-.56-.58-1.56 0-2.12l3.38-3.38l2.65-.52a6.1 6.1 0 0 0 2.81 1.96c1.16.35 2.44.34 3.59-.04c.29-.09.57-.2.83-.34L7.6 9l-1.77 1.78L3 7.95L7.95 3l4.24 1.41L9 7.6l8.31 8.29c.19-.18.34-.36.49-.56c1.5-1.97 1.62-4.91.29-7.33C16.78 5.57 14.5 3.55 12 2c1.41.5 2.76 1.17 4 2.04s2.43 1.89 3.33 3.21c.9 1.29 1.54 2.87 1.67 4.54c.1 1.68-.34 3.44-1.3 4.86c-.2.35-.46.63-.7.91z"
HS_VIEWBOX = "0 0 24 24"
ICON = (f'<svg class="hs" viewBox="{HS_VIEWBOX}" fill="currentColor" aria-hidden="true"><path d="{HS_PATH}"/></svg>')
_FAV = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><rect width="24" height="24" rx="6" fill="#c8102e"/>'
        f'<svg x="4" y="4" width="16" height="16" viewBox="{HS_VIEWBOX}" fill="#f6c21c"><path d="{HS_PATH}"/></svg></svg>')
FAVICON = "data:image/svg+xml," + __import__("urllib.parse", fromlist=["quote"]).quote(_FAV, safe="/:=\"' ")




# ------------------------------------------------------------------ pequenos componentes
def tabela(df: pd.DataFrame, colunas, max_linhas=25, uid: str | None = None, search=False) -> str:
    """colunas: (coluna, cabeçalho, tipo) com tipo em t (texto), tw (texto longo), i, d1, d2."""
    d = df.head(max_linhas)
    cab = "".join(f'<th class="{"t" if t in ("t", "tw") else ""}">{esc(h)}</th>' for _, h, t in colunas)
    linhas = []
    for _, r in d.iterrows():
        tds = []
        for c, _, t in colunas:
            v = r[c]
            if t in ("t", "tw"):
                tds.append(f'<td class="t{" wrap" if t == "tw" else ""}">'
                           f'{esc(v) if pd.notna(v) and v != "" else "–"}</td>')
            elif t == "ib":
                mx = float(d[c].max()) or 1.0
                larg = 0 if pd.isna(v) else 100 * float(v) / mx
                raw = "" if pd.isna(v) else f' data-v="{float(v)}"'
                tds.append(f'<td class="num ib"{raw}><i style="width:{larg:.1f}%"></i><span>{fnum(v, 0)}</span></td>')
            else:
                dec = {"i": 0, "d1": 1, "d2": 2}[t]
                raw = "" if pd.isna(v) else f' data-v="{float(v)}"'
                tds.append(f'<td class="num"{raw}>{fnum(v, dec) if pd.notna(v) else "–"}</td>')
        linhas.append("<tr>" + "".join(tds) + "</tr>")
    tid = uid or f"t{abs(hash(str(colunas) + str(len(d)))) % 10**8}"
    busca = (f'<input class="search" type="search" placeholder="Buscar município" data-for="{tid}" '
             f'aria-label="Buscar">') if search else ""
    return (f'{busca}<div class="tw"><table class="sortable" id="{tid}"><thead><tr>{cab}</tr></thead>'
            f'<tbody>{"".join(linhas)}</tbody></table></div>')


def kpi(valor: str, rotulo: str, dica: str = "", hero: bool = False) -> str:
    small = f"<small>{esc(dica)}</small>" if dica else ""
    return f'<div class="kpi{" hero" if hero else ""}"><b>{esc(valor)}</b><span>{esc(rotulo)}</span>{small}</div>'


def _tip(titulo, linhas):
    return [titulo, [[k, v] for k, v in linhas if v not in (None, "")]]





def fp(p, perms: int = 999) -> str:
    """p pseudo por permutação: o menor valor possível é 1/(perms+1), então escreve-se '≤'."""
    if p is None or p != p:
        return "p indefinido"
    piso = 1 / (perms + 1)
    return f"p ≤ {fnum(piso, 3)}" if p <= piso + 1e-9 else f"p = {fnum(p, 3)}"


def _metodo(texto: str, chaves=()) -> str:
    """Caixa de nota metodológica, com as referências da seção."""
    for k in chaves:
        if k not in _USADAS:
            _USADAS.append(k)
    lis = "".join(f"<li>{REFS[k]}</li>" for k in chaves)
    rl = f'<span class="rl">Referências</span><ul class="refs">{lis}</ul>' if lis else ""
    return f'<aside class="metodo"><span class="lab">Nota metodológica</span><p>{texto}</p>{rl}</aside>'



def _estruturar(html: str, nome_rel: str) -> tuple[str, list]:
    """Insere notas metodológicas ao fim de cada seção, divisores de parte e devolve o índice."""
    import re as _re
    pat = _re.compile(r'<h2 id="([a-z]+)"><span class="n">([^<]*)</span>([^<]*)</h2>')
    ms = list(pat.finditer(html))
    if not ms:
        return html, []
    ini = {m.group(1): m for m in ms}
    out, pos, idx = [html[:ms[0].start()]], 0, []
    parte_de = {}
    for L, tit, ids in PARTES:
        for i in ids:
            parte_de[i] = (L, tit)
    vistas = set()
    for k, m in enumerate(ms):
        fim = ms[k + 1].start() if k + 1 < len(ms) else None
        corpo = html[m.end():fim] if fim else html[m.end():]
        sid = m.group(1)
        cab = m.group(0)
        if sid in parte_de and parte_de[sid][0] not in vistas:
            L, tit = parte_de[sid]
            vistas.add(L)
            cab = f'<div class="parte"><span>Parte {L}</span><b>{tit}</b></div>' + cab
        idx.append((sid, m.group(2), m.group(3), parte_de.get(sid, ("", ""))[0]))
        # o rodapé fica fora da última seção
        resto = ""
        if not fim:
            j = corpo.find("<footer>")
            if j >= 0:
                corpo, resto = corpo[:j], corpo[j:]
        if sid in NOTAS and sid != "metodo":
            t, ch = NOTAS[sid]
            if sid == "cidades" and "Ponto quente" in corpo:
                t += (" <b>Hexágonos</b>: os locais de votação são agregados em hexágonos H3 e a estatística Gi* (Getis e Ord) identifica pontos quentes e frios, "
                      "com os 6 vizinhos mais próximos e 999 permutações, só em hexágonos com ao menos 30 votos válidos.")
                ch = list(ch) + ["getis", "ord95"]
            corpo += _metodo(t, ch)
        out.append(cab + corpo + resto)
    return "".join(out), idx


def _toc(idx, drop=False) -> str:
    grupos = ""
    for L, tit, ids in PARTES:
        its = [(a, n, t) for a, n, t, l in idx if l == L]
        if not its:
            continue
        lis = "".join(f'<a href="#{a}"><i>{n}</i>{t}</a>' for a, n, t in its)
        grupos += f'<div><h4><b>{L}</b>{tit}</h4>{lis}</div>'
    return grupos


# ------------------------------------------------------------------ guia de leitura


# ------------------------------------------------------------------ construção
def build_from_bundle(pasta_bundle, destino, site_dir=None) -> Path:
    """Refaz o dashboard único e, se site_dir for dado, adiciona o candidato ao site em pastas."""
    ctx = bundle.carregar(pasta_bundle)
    pag = montar(ctx)
    from . import site
    if site_dir is not None:
        site.adicionar_candidato(pag, site_dir)
    return site.escrever_standalone(pag, destino)


def montar(ctx: dict) -> dict:
    info, conc, mo = ctx["info"], ctx["conc"], ctx["moran"]
    gm, mun = ctx["gm"], ctx["municipal"]
    nome = nome_pt(info["nome"])
    _USADAS.clear()
    partes: list[str] = []
    a = partes.append

    # ---- cabeçalho e KPIs
    a('<header class="hd"><div class="mark">' + ICON + '</div>'
      f'<p class="eyebrow">{esc(ctx["cargo_nome"])} · {esc(ctx["uf"])} · {ctx["ano"]} · {info["turno"]}º turno · '
      f'nº {info["numero"]}</p><h1>{esc(nome)}</h1>'
      f'<p class="sub">Análise espacial da votação por município e nas principais cidades.</p></header>')
    a('<div class="kpis">')
    a(kpi(fnum(info["votos_total"]), "votos nominais",
          f"{fnum(ctx['pct_estado'], 2)}% dos votos válidos do estado", hero=True))
    a(kpi(f"{conc['n_com_voto']} de {conc['n_municipios']}", "municípios com voto",
          f"em {conc['n_municipios'] - conc['n_com_voto']} municípios não teve nenhum voto"))
    a(kpi(str(conc["n_para_50"]), "município(s) para 50% dos votos", f"{conc['n_para_80']} para 80%"))
    a(kpi(fnum(conc["gini"], 2), "concentração (Gini)", "0 = espalhado · 1 = concentrado"))
    mo_i = mo.get("I")
    if mo_i is not None:
        a(kpi(fnum(mo_i, 2), "vizinhança (Moran)",
              f"−1 a 1 · 0 = sem padrão · {fp(mo.get('p'))}"))
    a("</div>")
    tem_hex = any(c.get("cells") is not None for c in ctx["cidades"])
    a(GUIA.replace("</dl></details>", (GUIA_HEX if tem_hex else "") + "</dl></details>"))

    # ---- 1. Panorama
    proj = svgviz.Proj(gm.total_bounds, 760)
    gm = gm.copy()
    gm["nm"] = gm["NM_MUNICIPIO"].map(nome_pt)
    polys, c_v, c_p, c_q = [], None, None, None
    c_v, leg_v = svgviz.classes_quantil(gm["votos"], 6, inteiro=True)
    c_p, leg_p = svgviz.classes_quantil(gm["pct_validos"], 6, unit="%")
    c_q, leg_q = svgviz.classes_ql(gm["quociente_locacional"])
    for i, r in enumerate(gm.itertuples(index=False)):
        tipo = [("Votos", fnum(r.votos)), ("% dos votos válidos", fnum(r.pct_validos, 2) + "%"),
                ("Votos por 100 eleitores aptos", fnum(r.votos_por_100_aptos, 2)),
                ("Quociente locacional", fnum(r.quociente_locacional, 2)),
                ("Posição do candidato aqui", f"{int(r.posicao_no_municipio)}º" if pd.notna(r.posicao_no_municipio) else ""),
                ("Mais votado no município", nome_pt(r.lider_nome) if pd.notna(r.lider_nome) else "")]
        polys.append({"id": int(r.CD_MUNICIPIO), "d": svgviz.geom_path(r.geometry, proj), "cls": [c_v[i], c_p[i], c_q[i]],
                      "tip": _tip(r.nm, tipo)})
    metr = [
        {"key": "votos", "label": "Votos", "legend": leg_v,
         "note": "Quantidade de votos que o candidato teve em cada município. Mostra onde está o volume."},
        {"key": "pct", "label": "% dos válidos", "legend": leg_p,
         "note": "Percentual dos votos válidos do município que foram para o candidato. Mostra a força "
                 "proporcional, sem favorecer cidade grande."},
        {"key": "ql", "label": "Mais forte que a média", "legend": leg_q,
         "note": "Quociente locacional: a % dele no município dividida pela % dele no estado. Acima de 1, "
                 "o município vota nele mais do que a média."},
    ]
    a('<h2 id="panorama"><span class="n">1</span>Panorama estadual</h2>')
    a('<p class="lead">Passe o mouse (ou toque) em um município para ver os números. Os três botões trocam o que o mapa '
      'mostra: volume de votos, força proporcional e onde ele é mais forte que a média do estado.</p>')
    a(svgviz.geo_defs(polys))
    a('<div class="card"><div class="msearch"><input type="search" id="msq" placeholder="Buscar município pelo nome" '
      'autocomplete="off" role="combobox" aria-expanded="false" aria-controls="msl" aria-label="Buscar município pelo nome">'
      '<ul id="msl" role="listbox" hidden></ul></div>'
      '<p class="mhint">Clique em um município, em qualquer mapa, para abrir os detalhes.</p>' + svgviz.map_card("mapa-estado", polys, metr, proj,
                                            aria="Mapa de votos por município") + "</div>")

    top = mun.head(30).copy()
    a("<h3>Municípios com mais votos</h3>")
    ranking = [{"label": nome_pt(r.NM_MUNICIPIO), "value": float(r.votos), "fmt": fnum(r.votos),
                "tip": _tip(nome_pt(r.NM_MUNICIPIO), [("Votos", fnum(r.votos)),
                                                      ("% dos válidos", fnum(r.pct_validos, 2) + "%"),
                                                      ("Eleitores aptos", fnum(r.eleitores))])}
               for r in mun.head(12).itertuples()]
    a('<div class="card"><div class="scroll">' + svgviz.bar_chart(ranking, "Municípios com mais votos") +
      "</div></div>")
    if "lider_nome" in top.columns:
        top["lider_nome"] = top["lider_nome"].map(nome_pt)
    top["NM_MUNICIPIO"] = top["NM_MUNICIPIO"].map(nome_pt)
    a(tabela(top, [("NM_MUNICIPIO", "Município", "t"), ("votos", "Votos", "i"),
                   ("pct_validos", "% válidos", "d2"), ("votos_por_100_aptos", "Votos/100 aptos", "d2"),
                   ("quociente_locacional", "Quociente locacional", "d2"),
                   ("abstencao_pct", "Abstenção %", "d1"),
                   ("posicao_no_municipio", "Posição no município", "i"),
                   ("lider_nome", "Mais votado no município", "t")], 30, uid="tb-top"))
    forte = mun[mun["validos"] >= 2000].sort_values("pct_validos", ascending=False).copy()
    forte["NM_MUNICIPIO"] = forte["NM_MUNICIPIO"].map(nome_pt)
    a("<h3>Maior % de votos válidos (municípios com pelo menos 2.000 votos válidos)</h3>")
    a(tabela(forte, [("NM_MUNICIPIO", "Município", "t"), ("pct_validos", "% válidos", "d2"),
                     ("votos", "Votos", "i"), ("validos", "Votos válidos", "i")], 12, uid="tb-forte"))
    todos = mun.copy()
    todos["NM_MUNICIPIO"] = todos["NM_MUNICIPIO"].map(nome_pt)
    a(f'<details><summary>Tabela completa dos {len(todos)} municípios (com busca)</summary>')
    a(tabela(todos, [("NM_MUNICIPIO", "Município", "t"), ("votos", "Votos", "i"),
                     ("pct_validos", "% válidos", "d2"), ("votos_por_100_aptos", "Votos/100 aptos", "d2"),
                     ("quociente_locacional", "Quociente locacional", "d2"),
                     ("eleitores", "Eleitores aptos", "i"), ("abstencao_pct", "Abstenção %", "d1")],
             10_000, uid="tb-todos", search=True))
    a("</details>")

    # ---- 2. Concentração
    par = ctx["pareto"]
    cum = par["cum_share"].to_numpy()
    nomes = mun["NM_MUNICIPIO"].map(nome_pt).tolist()
    votos = mun["votos"].astype(int).tolist()
    n80 = conc["n_para_80"]
    xmax = int(min(max(conc["n_com_voto"], 2), max(20, 3 * n80)))
    series = [[i + 1, nomes[i], votos[i], round(float(cum[i]), 2)] for i in range(min(len(nomes), xmax))]
    marcos = []
    for n, alvo in ((conc["n_para_50"], 50), (n80, 80)):
        marcos.append({"x": n, "y": float(cum[n - 1]),
                       "rotulo": f"{'O maior município' if n == 1 else 'Os ' + str(n) + ' maiores'} somam {fnum(float(cum[n - 1]), 0)}% dos votos"})
    a('<h2 id="concentracao"><span class="n">2</span>Concentração</h2>')
    a(f'<p class="lead">{conc["n_para_50"]} município(s) concentram 50% dos votos e {n80} concentram 80%. '
      f'O maior município responde por {fnum(conc["top1_share"], 1)}% e os 10 maiores por '
      f'{fnum(conc["top10_share"], 1)}%. Em termos práticos, a base se comporta como se fossem '
      f'{fnum(conc["n_efetivo_municipios"], 1)} municípios de peso igual. Passe o mouse sobre a curva.</p>')
    a('<div class="card"><div class="scroll">' + svgviz.pareto_chart(series, marcos, xmax) + "</div></div>")

    # ---- 3. Vizinhança
    nmap = {"Alto-Alto": "hh", "Baixo-Baixo": "ll", "Outlier espacial": "ou", "Não significativo": "ns"}
    c_l, leg_l = svgviz.classes_categoria(gm["lisa_cluster"].tolist(), nmap,
                                          ["Alto-Alto", "Baixo-Baixo", "Outlier espacial", "Não significativo"])
    polys_l = []
    for i, r in enumerate(gm.itertuples(index=False)):
        det = r.lisa_detalhe if isinstance(r.lisa_detalhe, str) and r.lisa_detalhe else "Sem padrão significativo"
        polys_l.append({"id": polys[i]["id"], "d": polys[i]["d"], "cls": [c_l[i]],
                        "tip": _tip(r.nm, [("Padrão", r.lisa_cluster if r.lisa_cluster != "Não significativo" else "Sem padrão"),
                                           ("Leitura", det), ("% dos votos válidos", fnum(r.pct_validos, 2) + "%"),
                                           ("Votos", fnum(r.votos))])})
    a('<h2 id="vizinhanca"><span class="n">3</span>Autocorrelação espacial: vizinhança</h2>')
    if mo_i is not None:
        forca = "forte" if mo_i >= 0.5 else "moderada" if mo_i >= 0.25 else "fraca" if mo_i >= 0.1 else "praticamente inexistente"
        sig = ("e isso é estatisticamente significativo: a chance de ser acaso é menor que 5%."
               if (mo.get("p") or 1) < 0.05 else "mas não dá para descartar que seja acaso.")
        a(f'<p class="lead">O índice de Moran da % de votos válidos é <b>{fnum(mo_i, 3)}</b> ({fp(mo.get("p"))}): '
          f'a vizinhança importa de forma <b>{forca}</b>, {sig}</p>')
    a('<div class="prose"><p><b>O que é autocorrelação espacial.</b> É a pergunta &quot;o que acontece num lugar se parece com '
      'o que acontece ao lado?&quot;. Aqui, cada lugar é um município e &quot;ao lado&quot; são os municípios que fazem divisa com ele. '
      'Se a votação do candidato estivesse espalhada ao acaso, saber a % dele numa cidade não diria nada sobre a da cidade vizinha. '
      'Quando a autocorrelação é positiva, cidades fortes tendem a ter vizinhas fortes e cidades fracas tendem a ter vizinhas fracas: '
      'o voto forma <em>manchas</em> no mapa. Isso costuma ter causa concreta, como a região onde o candidato fez campanha, a base de '
      'uma liderança local, uma categoria profissional ou um perfil regional de eleitorado.</p>'
      '<p><b>O índice de Moran</b> resume isso num número entre −1 e +1. Perto de 0, não há padrão. Positivo, há manchas. Negativo, '
      'vizinhos tendem a ser opostos. Ele usa a <em>% de votos válidos</em>, e não o total de votos, para que cidade grande não '
      'apareça forte só por ter mais gente.</p></div>')
    a('<div class="card">' + svgviz.map_card(
        "mapa-lisa", polys_l, [{"key": "lisa", "label": "LISA", "legend": leg_l,
                                "note": "Cada município é comparado com os vizinhos que fazem divisa. "
                                        "Só aparecem as diferenças estatisticamente significativas (p < 0,05)."}],
        proj, aria="Clusters espaciais LISA") + "</div>")
    a(f'<p class="lead" style="margin-top:16px">O Moran diz <em>se</em> há manchas; o mapa acima (LISA) diz <em>onde</em> elas estão. '
      f'Foram {mo.get("n_hh", 0)} município(s) em núcleo de força, {mo.get("n_ll", 0)} em vazio e {mo.get("n_out", 0)} em contraste '
      f'(ilha de voto ou lacuna). Só entra o que é estatisticamente significativo; o resto fica cinza.</p>')
    a('<div class="expl">'
      '<div><h4><i style="background:var(--hh)"></i>Núcleo de força</h4><p>Município com % alta, cercado de vizinhos também altos. '
      'É a base consolidada: o candidato é conhecido na região inteira, não só numa cidade. O caminho natural de crescimento é puxar '
      'os vizinhos que ainda estão abaixo.</p></div>'
      '<div><h4><i style="background:var(--ou)"></i>Ilha de voto</h4><p>Município forte cercado de vizinhos fracos. O voto vem de um '
      'motivo local (uma liderança, uma comunidade, um cabo eleitoral) e não transborda para a região. Mostra que há voto ali, mas '
      'também que ele pode depender de uma pessoa só.</p></div>'
      '<div><h4><i style="background:var(--ou);opacity:.45"></i>Lacuna</h4><p>Município fraco cercado de vizinhos fortes. Costuma ser '
      'a oportunidade mais barata: o candidato já é conhecido ao redor, e a cidade ficou para trás.</p></div>'
      '<div><h4><i style="background:var(--ll)"></i>Vazio</h4><p>Município fraco cercado de vizinhos fracos. Sem voto e sem presença. '
      'Quando o candidato tem poucos votos no estado, essa classe domina o mapa e diz pouco; o mais útil é o resto.</p></div></div>')
    gm2 = gm.copy()
    gm2["NM_MUNICIPIO"] = gm2["nm"]
    gm2["lisa_detalhe"] = gm2["lisa_detalhe"].fillna("").astype(str)
    gm2 = gm2.sort_values("votos", ascending=False)
    colunas_l = [("NM_MUNICIPIO", "Município", "t"), ("votos", "Votos", "i"), ("pct_validos", "% válidos", "d2")]
    blocos = [
        ("Núcleos de força", gm2[gm2["lisa_cluster"] == "Alto-Alto"],
         "Municípios fortes cercados de vizinhos fortes. É onde a base está consolidada.", "tb-nucleo"),
        ("Ilhas de voto", gm2[(gm2["lisa_cluster"] == "Outlier espacial") & (gm2["lisa_detalhe"].str.startswith("Forte"))],
         "Municípios fortes em meio a vizinhos fracos. Voto concentrado, que não se espalhou.", "tb-ilha"),
        ("Lacunas (oportunidades)", gm2[(gm2["lisa_cluster"] == "Outlier espacial") & (gm2["lisa_detalhe"].str.startswith("Fraco"))],
         "Municípios fracos em meio a vizinhos fortes. Tendem a ser os alvos mais baratos de crescimento.", "tb-lacuna"),
    ]
    for tit, df_, expl, uid in blocos:
        if len(df_):
            a(f"<h3>{tit}</h3><p class=\"lead\" style=\"margin-bottom:10px\">{expl}</p>")
            a(tabela(df_, colunas_l, 20, uid=uid))

    # ---- 4. Dentro das cidades
    a('<h2 id="cidades"><span class="n">4</span>Cidades</h2>')
    com_nomes = any(not c["locais"]["local_nome"].astype(str).str.startswith("Local ").all() for c in ctx["cidades"])
    if com_nomes:
        a('<div class="callout"><b>Leitura com cuidado:</b> o TSE não publica voto por bairro. A unidade mínima é a seção eleitoral, '
          'que funciona num local de votação. Por isso as cidades são detalhadas por <b>local de votação</b>, bairro e zona '
          'eleitoral, que são dados oficiais. Eles descrevem onde a pessoa <b>vota</b>, que costuma ser perto de onde mora, '
          'mas não é a mesma coisa.</div>')
    if ctx["cidades"]:
        if ctx.get("criterio_cidades") == "manual":
            a(f'<p class="lead">Cidades escolhidas manualmente no <code>config.json</code> ({len(ctx["cidades"])}), '
              f'em ordem decrescente de votos.</p>')
        else:
            a(f'<p class="lead">Aparecem as {len(ctx["cidades"])} cidades em que o candidato teve <b>mais votos</b>, em ordem '
              f'decrescente (o critério é o volume absoluto de votos, não o percentual). Para escolher outras, use '
              f'<code>"cidades"</code> no <code>config.json</code>.</p>')
        a('<div class="tabset"><div class="cscroll">'
          '<button class="arr l" type="button" aria-label="Cidades anteriores" hidden>'
          '<svg viewBox="0 0 24 24"><path d="M15 5l-7 7 7 7"/></svg></button>'
          '<button class="arr r" type="button" aria-label="Próximas cidades" hidden>'
          '<svg viewBox="0 0 24 24"><path d="M9 5l7 7-7 7"/></svg></button>'
          '<div class="ctabs" role="tablist" aria-label="Cidades">')
        for c in ctx["cidades"]:
            a(f'<button class="ctab" type="button" role="tab"><b>{esc(c["nome"])}</b>'
              f'<span>{fnum(c["votos"])} votos · {fnum(c["pct"], 1)}%</span></button>')
        a("</div></div>")
        for ci, c in enumerate(ctx["cidades"]):
            a(_cidade(ci, c))
        a("</div>")

    # ---- 5. Comparação com outros candidatos
    cmp_ = ctx.get("comparacao")
    _sec = [4]

    def nxt():
        _sec[0] += 1
        return _sec[0]
    if cmp_ is not None and len(cmp_) and cmp_["foco"].any():
        a(f'<h2 id="comparacao"><span class="n">{nxt()}</span>Comparação com os mais votados de cada partido</h2>')
        f = cmp_[cmp_["foco"]].iloc[0]
        outros = cmp_[~cmp_["foco"] & cmp_["top_do_partido"]].copy()
        N = int(f["n_municipios"])
        mais_amplos = int((outros["n_mun_1pct"] > f["n_mun_1pct"]).sum())
        mais_votos = int((outros["votos"] > f["votos"]).sum())
        melhor = outros.sort_values("n_mun_1pct", ascending=False).iloc[0] if len(outros) else None
        def _qtd(n_, o_):
            return f"nenhum {o_[0]}" if n_ == 0 else (f"1 {o_[0]}" if n_ == 1 else f"{n_} {o_[1]}")
        txt = (f'<b>{esc(nome)}</b> teve voto em <b>{int(f["n_mun_voto"])} de {N}</b> municípios, pelo menos 0,5% dos votos válidos em '
               f'{int(f["n_mun_05pct"])}, pelo menos 1% em {int(f["n_mun_1pct"])} e pelo menos 5% em {int(f["n_mun_5pct"])}. '
               f'Entre os {len(outros) + 1} candidatos comparados, '
               f'{_qtd(mais_amplos, ("teve", "tiveram"))} presença de 1% em mais municípios do que ele, e '
               f'{_qtd(mais_votos, ("teve", "tiveram"))} mais votos no total.')
        if melhor is not None and melhor["n_mun_1pct"] > f["n_mun_1pct"]:
            txt += (f' A maior abrangência é de {esc(nome_pt(melhor["nome"]))} ({esc(melhor["sigla"])}), com '
                    f'{int(melhor["n_mun_1pct"])} municípios.')
        pl = outros[outros["sigla"] == "PL"]
        if len(pl):
            x = pl.iloc[0]
            cmpv = "mais" if x["n_mun_1pct"] > f["n_mun_1pct"] else "menos" if x["n_mun_1pct"] < f["n_mun_1pct"] else "o mesmo número de"
            txt += (f' O mais votado do PL, {esc(nome_pt(x["nome"]))}, fez {fnum(x["votos"])} votos e chegou a 1% em '
                    f'{int(x["n_mun_1pct"])} municípios, {cmpv} que {esc(nome)}.')
        a(f'<p class="lead">{txt}</p>')
        base = cmp_[cmp_["foco"] | cmp_["top_do_partido"]]
        medidas = [("n_mun_voto", "Qualquer voto", "Em quantos municípios o candidato teve pelo menos um voto"),
                   ("n_mun_05pct", "0,5% ou mais", "Em quantos municípios o candidato teve 0,5% ou mais dos votos válidos"),
                   ("n_mun_1pct", "1% ou mais", "Em quantos municípios o candidato teve 1% ou mais dos votos válidos")]
        a('<div class="tabset"><div class="tablist" role="tablist">'
          + "".join(f'<button type="button" role="tab">{esc(r)}</button>' for _, r, _ in medidas) + "</div>")
        for col_, rot_, tit_ in medidas:
            ordem_ = base.sort_values([col_, "votos"], ascending=False)
            rows = [{"label": f'{nome_pt(r.nome)} ({r.sigla})'[:34], "value": float(getattr(r, col_)),
                     "fmt": str(int(getattr(r, col_))), "hl": bool(r.foco),
                     "tip": _tip(f"{nome_pt(r.nome)} ({r.sigla})",
                                 [("Votos", fnum(r.votos)), ("% dos válidos no estado", fnum(r.pct_estado, 2) + "%"),
                                  ("Municípios com algum voto", f"{int(r.n_mun_voto)} de {int(r.n_municipios)}"),
                                  ("Municípios com 0,5% ou mais", str(int(r.n_mun_05pct))),
                                  ("Municípios com 1% ou mais", str(int(r.n_mun_1pct))),
                                  ("Municípios com 5% ou mais", str(int(r.n_mun_5pct))),
                                  ("Entre os 3 mais votados em", f"{int(r.n_top3)} municípios"),
                                  ("Situação", r.situacao if isinstance(r.situacao, str) else "")])}
                    for r in ordem_.itertuples(index=False)]
            a(f'<div class="pane"><div class="card"><h3>{esc(tit_)}</h3><div class="scroll">'
              + svgviz.bar_chart(rows, tit_) + "</div>"
              '<p style="margin:10px 0 0;font-size:12.5px;color:var(--muted)">O candidato desta análise aparece em dourado. '
              f'Total de municípios: {N}.</p></div></div>')
        a("</div>")
        ordem = base.sort_values("n_mun_1pct", ascending=False)
        tb = ordem.copy()
        tb["candidato"] = [nome_pt(n_) + (" (foco)" if fo else "") for n_, fo in zip(tb["nome"], tb["foco"])]
        cols_c = [("candidato", "Candidato", "t"), ("sigla", "Partido", "t"), ("votos", "Votos", "i"),
                  ("pct_estado", "% válidos no estado", "d2"), ("n_mun_voto", "Municípios com algum voto", "i"),
                  ("n_mun_05pct", "Municípios com 0,5%+", "i"), ("n_mun_1pct", "Municípios com 1%+", "i"),
                  ("n_mun_5pct", "Municípios com 5%+", "i"), ("n_top3", "Entre os 3 mais votados", "i"),
                  ("top1_share", "% dos votos na maior cidade", "d1"), ("gini", "Gini", "d2")]
        if "moran_I" in tb.columns:
            cols_c.append(("moran_I", "Moran", "d2"))
        a(tabela(tb, cols_c, 40, uid="tb-comp"))
        a('<div class="prose" style="margin-top:14px"><p><b>Como ler.</b> Quase todo candidato recebe algum voto em quase todo '
          'município, então contar municípios com pelo menos um voto não distingue ninguém. Por isso o gráfico mostra três '
          'réguas: <em>qualquer voto</em> (o alcance bruto, que quase todos têm), <em>0,5% ou mais</em> e <em>1% ou mais</em> dos '
          'votos válidos do município (presença relevante, cada vez mais exigente). A tabela traz ainda 5%. As outras colunas '
          'ajudam a separar volume de alcance:</p><ul>'
          '<li><b>Entre os 3 mais votados</b>: em quantos municípios ele ficou no pódio. Mede força local, não só presença.</li>'
          '<li><b>% dos votos na maior cidade</b>: quanto do total vem do município onde mais votou. Alto significa dependência '
          'de uma cidade (Porto Alegre, em geral); baixo, votos espalhados.</li>'
          '<li><b>Gini</b> e <b>Moran</b>: os mesmos das seções 2 e 3, calculados para cada candidato. Gini alto = concentrado; '
          'Moran alto = votos formam manchas contínuas no mapa.</li></ul>'
          '<p>Cada partido entra com o seu candidato mais votado, mais o candidato desta análise. O partido é a sigla, não a '
          'federação (o PCdoB, por exemplo, está na Federação Brasil da Esperança com PT e PV). Candidatos de partidos com chapas '
          'enormes e dinheiro de campanha muito diferente não são comparáveis em esforço, só em resultado.</p></div>')

    # ---- Análises complementares
    an = ctx.get("analises")
    if an:
        _analises(a, nxt, ctx, gm, polys, proj, nome)

    # ---- Potencial
    a(f'<h2 id="potencial"><span class="n">{nxt()}</span>Eficiência e potencial</h2>')
    a('<p class="lead">Duas medidas para responder onde vale concentrar esforço: uma diz o quanto o candidato já converte do '
      'eleitorado de cada município, a outra diz quantos votos ainda há para buscar.</p>')
    a('<div class="prose"><ul>'
      '<li><b>Eficiência: votos por 100 eleitores aptos.</b> De cada 100 pessoas que podem votar no município, quantas votaram no '
      'candidato. Compara cidades de tamanhos diferentes na mesma régua e mostra onde ele converte melhor o eleitorado.</li>'
      '<li><b>Potencial: votos até a média.</b> Se o município votasse nele na mesma proporção do estado inteiro, quantos votos '
      'a mais ele teria. A conta é: <em>% dele no estado × votos válidos do município − votos que ele teve</em>. Se der '
      'negativo (o município já está acima da média), vale zero.</li></ul></div>')
    pot = mun.sort_values("votos_ate_media_estadual", ascending=False).copy()
    if len(pot) and float(pot.iloc[0]["votos_ate_media_estadual"]) > 0:
        r0 = pot.iloc[0]
        esp = ctx["pct_estado"] / 100 * float(r0["validos"])
        a('<div class="exemplo"><b>Exemplo com os números dele.</b> '
          f'{esc(nome_pt(r0["NM_MUNICIPIO"]))} teve {fnum(r0["validos"])} votos válidos. Na média do estado ({fnum(ctx["pct_estado"], 2)}%), '
          f'{esc(nome)} receberia cerca de {fnum(esp)} votos ali. Teve {fnum(r0["votos"])} ({fnum(r0["pct_validos"], 2)}%). '
          f'A diferença, <b>{fnum(r0["votos_ate_media_estadual"])} votos</b>, é o potencial do município.</div>')
    a('<div class="callout"><b>Como usar:</b> não é uma projeção nem uma promessa de que dá para chegar à média. Cidades grandes '
      'sobem para o topo simplesmente porque têm muito eleitor, então a lista mostra onde a diferença em votos é maior, não onde é '
      'mais fácil. Para achar a oportunidade realista, cruze com a seção 3: um município de potencial alto que é uma <em>lacuna</em> '
      '(fraco entre vizinhos fortes) tende a custar menos do que um município fraco cercado de municípios fracos.</div>')
    pot["NM_MUNICIPIO"] = pot["NM_MUNICIPIO"].map(nome_pt)
    a(tabela(pot, [("NM_MUNICIPIO", "Município", "t"), ("eleitores", "Eleitores aptos", "i"), ("votos", "Votos", "i"),
                   ("pct_validos", "% válidos", "d2"), ("votos_por_100_aptos", "Votos/100 aptos", "d2"),
                   ("votos_ate_media_estadual", "Votos até a média", "i")], 20, uid="tb-pot"))

    # ---- 6. Contexto
    a(f'<h2 id="contexto"><span class="n">{nxt()}</span>Contexto: partido, abstenção, brancos e nulos</h2>')
    a("<h3>Candidatos do mesmo partido</h3>")
    col = ctx["colegas"].copy()
    col["nome"] = col["nome"].map(nome_pt)
    a(tabela(col, [("nome", "Candidato", "t"), ("numero", "Número", "i"), ("votos", "Votos", "i"),
                   ("rank_estado", "Posição no estado", "i"), ("share_partido", "% dos votos do partido", "d1")],
             15, uid="tb-col"))
    a("<h3>Municípios com maior abstenção</h3>")
    ab = mun[mun["votos"] > 0].sort_values("abstencao_pct", ascending=False).copy()
    ab["NM_MUNICIPIO"] = ab["NM_MUNICIPIO"].map(nome_pt)
    a(tabela(ab, [("NM_MUNICIPIO", "Município", "t"), ("abstencao_pct", "Abstenção %", "d1"),
                  ("brancos_nulos_pct", "Brancos+nulos %", "d1"), ("votos", "Votos", "i"),
                  ("pct_validos", "% válidos", "d2")], 15, uid="tb-abs"))
    if ctx.get("regioes") is not None:
        r = ctx["regioes"]
        a("<h3>Por região</h3>")
        a(tabela(r, [(r.columns[0], "Região", "t"), ("municipios", "Municípios", "i"), ("votos", "Votos", "i"),
                     ("pct_validos", "% válidos", "d2"), ("share_votos_estado", "% dos votos do candidato", "d1")],
                 40, uid="tb-reg"))
    d = ctx.get("despesas")
    if d:
        a(f'<h2 id="contas"><span class="n">{nxt()}</span>Prestação de contas</h2>')
        a('<div class="kpis">' + kpi("R$ " + fnum(d["total"], 2), "despesas declaradas") +
          kpi("R$ " + fnum(d["custo_por_voto"], 2), "custo por voto") + "</div>")
        if d.get("por_categoria"):
            pc = pd.DataFrame(d["por_categoria"]).rename(columns={"valor": "Valor"})
            a(tabela(pc, [("categoria", "Categoria", "t"), ("Valor", "R$", "d2")], 15, uid="tb-desp"))

    a('<h2 id="metodo"><span class="n">M</span>Notas metodológicas</h2>')
    a('<h3>Fontes de dados</h3><div class="prose"><p>Votação por seção (boletins de urna), perfil do eleitorado e eleitorado por local de votação, do '
      'Portal de Dados Abertos do TSE, e malha municipal do IBGE.'
      + (' Coordenadas fora do município (erros de geocodificação do TSE) são descartadas; seções com coordenada válida: '
         f"{fnum(100 * ctx['cob_coord'], 1)}%." if tem_hex else '') + '</p></div>')
    a('<h3>Definições</h3><div class="prose"><ul>'
      '<li><b>% de votos válidos</b>: votos do candidato ÷ (votos nominais + de legenda), sem brancos e nulos.</li>'
      '<li><b>Moran e LISA</b>: vizinhança por divisa, 999 permutações, p &lt; 0,05. O Gini é calculado sobre todos os municípios do estado, incluindo os sem voto.</li>'
      + ('<li><b>Hexágonos H3</b>: a resolução é escolhida por cidade para que cada hexágono reúna, em média, ao menos 2 locais de votação. '
         'Gi*: hexágonos com pelo menos 30 votos válidos e 6 vizinhos mais próximos.</li>' if tem_hex else '') +
      '<li><b>Abstenção</b>: 1 − (votos de todos os candidatos, brancos e nulos ÷ eleitores aptos). É uma aproximação.</li>'
      '</ul></div>')
    a('<h3>Referências consolidadas</h3><div class="metodo" style="margin-top:0"><ul class="refs">@@REFS@@</ul></div>')

    corpo, idx = _estruturar("".join(partes), nome)
    corpo = corpo.replace("@@REFS@@", "".join(f"<li>{REFS[k]}</li>" for k in sorted(_USADAS, key=lambda k: REFS[k])))
    grupos = _toc(idx)
    chev = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>'
    nav = ('<nav class="top"><div class="in"><span class="brand"><i>' + ICON + '</i>Análise eleitoral</span>'
           '<a href="#guia">Como ler</a>'
           f'<button class="idx" id="idxb" type="button" aria-expanded="false" aria-controls="idxp">Índice{chev}</button></div>'
           f'<div class="idxp" id="idxp" hidden>{grupos}</div>'
           '<div class="sec" id="secbar" hidden><span class="n"></span><span class="t"></span></div></nav>')
    toc = f'<section class="toc" id="sumario"><h3>Sumário</h3><div class="tocg">{grupos}</div></section>'
    corpo = corpo.replace('<div class="parte">', toc + '<div class="parte">', 1)
    pagina = {"titulo": f'{nome} · análise espacial {ctx["ano"]}', "nav": nav, "corpo": corpo,
              "det": _detalhes(ctx, gm, tem_an=bool(ctx.get("analises"))), "ano": ctx["ano"], "uf": ctx["uf"], "cargo_cod": int(ctx.get("cargo", 7)),
              "numero": info["numero"], "nome": nome, "cargo": ctx["cargo_nome"],
              "turno": info["turno"], "votos": int(info["votos_total"])}
    return pagina


def build(ctx: dict, destino) -> Path:
    """Dashboard único (offline): CSS, JS e dados embutidos no HTML."""
    from . import site
    return site.escrever_standalone(montar(ctx), destino)


def _detalhes(ctx: dict, gm, tem_an: bool) -> dict:
    """Dados do painel de detalhes: especificação dos campos, valores por município e top 5."""
    mun = ctx["municipal"].set_index("CD_MUNICIPIO")
    g = gm.copy()
    if tem_an:
        g = g.merge(ctx["analises"]["mun"], on="CD_MUNICIPIO", how="left", suffixes=("", "_an"))
    campos = [("Votos", "v", "i", "votos"), ("% dos votos válidos", "pv", "p2", "pct_validos"),
              ("Votos por 100 eleitores aptos", "v100", "d2", "votos_por_100_aptos"),
              ("Quociente locacional", "ql", "d2", "quociente_locacional"),
              ("Posição do candidato aqui", "pos", "pos", "posicao_no_municipio"),
              ("Mais votado no município", "lid", "t", "lider_nome"),
              ("Colega de partido mais votado", "col", "t", "colega_nome"),
              ("Eleitores aptos", "el", "i", "eleitores"),
              ("Abstenção", "ab", "p1", "abstencao_pct"), ("Brancos e nulos", "bn", "p1", "brancos_nulos_pct"),
              ("Votos até a média do estado", "pot", "i", "votos_ate_media_estadual"),
              ("Vizinhança (LISA)", "lisa", "t", "lisa_cluster"), ("Leitura da vizinhança", "lisad", "t", "lisa_detalhe"),
              ("Esperado pela federação (votos)", "esp", "i", "esperado_fed"),
              ("Diferença para o esperado da federação", "dif", "s", "dif_fed"),
              ("% prevista pelo modelo", "prev", "p2", "pct_previsto"),
              ("Resíduo do modelo (desvios)", "z", "d1", "z_residuo"),
              ("Distância ao reduto mais próximo", "dist", "km", "dist_reduto_km"),
              ("Reduto mais próximo", "red", "t", "reduto_proximo")]
    campos = [c for c in campos if c[3] in g.columns or c[3] in mun.columns]
    nomes_cols = {"lider_nome", "colega_nome", "reduto_proximo"}
    out = {}
    for r in g.to_dict("records"):
        cd = r.get("CD_MUNICIPIO")
        if cd is None or pd.isna(cd):
            continue
        cd = int(cd)
        m = {"n": nome_pt(r.get("NM_MUNICIPIO") or r.get("nm_ibge"))}
        for _, k, f, col in campos:
            v = r.get(col)
            if v is None or (not isinstance(v, str) and pd.isna(v)):
                continue
            if col in nomes_cols and isinstance(v, str):
                v = nome_pt(v)
            if col == "lisa_cluster" and v == "Não significativo":
                v = "Sem padrão significativo"
            m[k] = v if isinstance(v, str) else round(float(v), 4)
        if m.get("v") == 0:
            m.pop("pos", None)
        out[cd] = m
    top = {}
    tm = ctx.get("top_mun")
    if tm is not None and len(tm):
        foco = int(ctx["info"]["numero"])
        for r in tm.itertuples(index=False):
            top.setdefault(int(r.CD_MUNICIPIO), []).append(
                [int(r.posicao), nome_pt(r.nome), str(r.sigla), int(r.votos),
                 round(float(r.pct), 2) if pd.notna(r.pct) else 0, int(r.numero) == foco])
    return {"fields": [[c[0], c[1], c[2]] for c in campos], "mun": out, "top": top}


def _cidade(ci: int, c: dict) -> str:
    """Painel de uma cidade: números-chave e tabelas por zona (e por bairro/local, quando há nomes)."""
    out = []
    a = out.append
    a('<section class="pane cpanel">')
    a(f'<h3 class="cn">{esc(c["nome"])}</h3>')
    locais = c["locais"]
    loc = locais.sort_values("votos", ascending=False)
    nomes_reais = not loc["local_nome"].astype(str).str.startswith("Local ").all()
    zonas = c["zonas"]
    mini = (f'<span><b>{fnum(c["votos"])}</b>votos</span><span><b>{fnum(c["pct"], 2)}%</b>dos votos válidos</span>'
            f'<span><b>{len(zonas)}</b>zona(s) eleitoral(is)</span>')
    if nomes_reais:
        mini += f'<span><b>{c["n_locais"]}</b>locais de votação</span>'
    mini += f'<span><b>{fnum(c["eleitores"])}</b>eleitores aptos</span>'
    a(f'<div class="mini">{mini}</div>')

    abas = []  # (rótulo, html)
    if len(zonas):
        cz = [("NR_ZONA", "Zona", "i")]
        if nomes_reais:
            cz.append(("locais", "Locais", "i"))
        cz += [("votos", "Votos", "ib"), ("pct_validos", "% válidos", "d2"), ("eleitores", "Eleitores aptos", "i"),
               ("share_votos_cidade", "% dos votos da cidade", "d1")]
        abas.append(("Zonas eleitorais", tabela(zonas, cz, 30, uid=f"tb-z{ci}")))
    bai = c["bairros"]
    if (bai["bairro"] != "(sem bairro)").any():
        abas.append(("Bairros", tabela(bai, [("bairro", "Bairro", "t"), ("locais", "Locais", "i"), ("votos", "Votos", "i"),
                                             ("pct_validos", "% válidos", "d2"),
                                             ("share_votos_cidade", "% dos votos da cidade", "d1")], 60, uid=f"tb-b{ci}")))
    if nomes_reais:
        cols = [("local_nome", "Local de votação", "t")]
        if (loc["bairro"] != "(sem bairro)").any():
            cols.append(("bairro", "Bairro", "t"))
        cols += [("NR_ZONA", "Zona", "i"), ("votos", "Votos", "i"), ("pct_validos", "% válidos", "d2"),
                 ("eleitores", "Eleitores", "i"), ("votos_por_100_aptos", "Votos/100 aptos", "d2")]
        abas.append(("Locais de votação", tabela(loc, cols, 60, uid=f"tb-l{ci}")))
    hx = _mapa_hex(ci, c)
    if hx:
        abas.append(("Mapa por hexágono", hx))
    if len(abas) == 1:
        a(abas[0][1])
    else:
        a('<div class="tabset"><div class="tablist" role="tablist">'
          + "".join(f'<button type="button" role="tab">{esc(r)}</button>' for r, _ in abas) + "</div>")
        for _, h in abas:
            a(f'<div class="pane">{h}</div>')
        a("</div>")
    a("</section>")
    return "".join(out)


def _mapa_hex(ci: int, c: dict) -> str:
    """Mapa opcional por hexágono (só existe se o pipeline rodou com --hex)."""
    cells = c.get("cells")
    if cells is None or not len(cells):
        return ""
    locais = c["locais"]
    out = ['<div class="callout"><b>Atenção:</b> o hexágono agrupa locais de votação, que são só uma aproximação de onde '
           "as pessoas moram. Com poucos votos por célula, os padrões podem ser ruído.</div>"]
    cells = cells.copy()
    bnds = cells.total_bounds
    dx, dy = (bnds[2] - bnds[0]) * 0.06 + 1e-4, (bnds[3] - bnds[1]) * 0.06 + 1e-4
    proj = svgviz.Proj((bnds[0] - dx, bnds[1] - dy, bnds[2] + dx, bnds[3] + dy), 760)
    c_v, leg_v = svgviz.classes_quantil(cells["votos"], 5, inteiro=True)
    c_p, leg_p = svgviz.classes_quantil(cells["pct_validos"], 5, unit="%")
    gmap = {"Ponto quente": "hot", "Ponto frio": "cold", "Não significativo": "ns", "Sem dados suficientes": "nd"}
    c_g, leg_g = svgviz.classes_categoria(cells["gi_classe"].tolist(), gmap,
                                          ["Ponto quente", "Ponto frio", "Não significativo", "Sem dados suficientes"])
    polys = []
    for i, r in enumerate(cells.itertuples(index=False)):
        polys.append({"d": svgviz.geom_path(r.geometry, proj), "cls": [c_v[i], c_p[i], c_g[i]],
                      "tip": _tip("Hexágono", [("Votos", fnum(r.votos)), ("% dos votos válidos", fnum(r.pct_validos, 2) + "%"),
                                               ("Eleitores aptos", fnum(r.eleitores)),
                                               ("Locais de votação", str(int(r.locais))),
                                               ("Zona(s) eleitoral(is)", str(r.zonas)),
                                               ("Principais locais", str(r.locais_top)),
                                               ("Padrão (Gi*)", r.gi_classe if r.gi_classe != "Não significativo" else "Sem padrão")])})
    pts = []
    pl = locais.dropna(subset=["lat", "lon"])
    vmax = max(float(pl["votos"].max()), 1.0) if len(pl) else 1.0
    for r in pl.itertuples(index=False):
        x, y = proj.xy(r.lon, r.lat)
        if -5 <= x <= proj.W + 5 and -5 <= y <= proj.H + 5:
            pts.append({"x": x, "y": y, "r": 2.5 + 6.5 * (float(r.votos) / vmax) ** 0.5,
                        "tip": _tip(str(r.local_nome), [("Bairro", r.bairro if r.bairro != "(sem bairro)" else ""),
                                                        ("Zona", str(int(r.NR_ZONA))), ("Votos", fnum(r.votos)),
                                                        ("% dos válidos", fnum(r.pct_validos, 2) + "%"),
                                                        ("Eleitores aptos", fnum(r.eleitores)), ("Seções", str(int(r.secoes)))])})
    bg = svgviz.geom_path(c["geom"], proj) if c.get("geom") is not None else ""
    area = f"{fnum(c['area_km2'], 1)} km²" if c.get("area_km2") else ""
    metr = [
        {"key": "votos", "label": "Votos", "legend": leg_v,
         "note": f"Votos nos locais de votação dentro de cada hexágono (≈ {area} cada)."},
        {"key": "pct", "label": "% dos válidos", "legend": leg_p,
         "note": "Percentual dos votos válidos do hexágono que foram para o candidato."},
        {"key": "gi", "label": "Pontos quentes e frios", "legend": leg_g,
         "note": "Getis-Ord Gi*: hexágonos cuja vizinhança tem % acima (quente) ou abaixo (frio) do esperado, "
                 "com significância estatística."},
    ]
    out.append('<div class="card">' + svgviz.map_card(f"mapa-cidade-{ci}", polys, metr, proj, points=pts,
                                                     aria=f"Mapa de hexágonos de {c['nome']}", bg=bg) + "</div>")
    if c.get("html_map"):
        out.append("<details><summary>Ver sobre mapa de ruas (precisa de internet)</summary>"
                   f'<iframe class="ruas" loading="lazy" srcdoc="{html.escape(c["html_map"], quote=True)}"></iframe></details>')
    return "".join(out)


# ------------------------------------------------------------------ análises complementares
def _mapa_extra(uid, polys, gmx, metricas, tip_fn, proj, aria):
    """metricas: [(chave, rótulo, nota, classes, legenda)]; polys vem do mapa do panorama (mesma ordem de gmx)."""
    ps = []
    for i, r in enumerate(gmx.itertuples(index=False)):
        ps.append({"id": polys[i]["id"], "d": polys[i]["d"], "cls": [m[3][i] for m in metricas], "tip": tip_fn(r)})
    mm = [{"key": m[0], "label": m[1], "note": m[2], "legend": m[4]} for m in metricas]
    return '<div class="card">' + svgviz.map_card(uid, ps, mm, proj, aria=aria) + "</div>"


def _analises(a, nxt, ctx, gm, polys, proj, nome):
    import numpy as np

    an = ctx["analises"]
    meta = an["meta"]
    mun = ctx["municipal"]
    gmx = gm.merge(an["mun"], on="CD_MUNICIPIO", how="left")
    for c in ("fed_votos", "fed_pct", "part_fed", "dif_fed", "esperado_fed", "z_residuo", "residuo_pp", "dif_modelo",
              "votos_esperados", "pct_previsto", "dist_reduto_km"):
        if c in gmx.columns:
            gmx[c] = gmx[c].fillna(0)
    gmx["reduto_proximo"] = gmx["reduto_proximo"].fillna("") if "reduto_proximo" in gmx.columns else ""
    nm_mun = dict(zip(mun["CD_MUNICIPIO"], mun["NM_MUNICIPIO"].map(nome_pt)))

    def _sem_votos(leg, novo):
        return [(c, novo if r == "sem votos" else r) for c, r in leg]

    # ---------------- Sobreposição
    sob = an["sobreposicao"].copy()
    base = float(100 * np.minimum(mun["votos"] / mun["votos"].sum(), mun["validos"] / mun["validos"].sum()).sum())
    a(f'<h2 id="sobreposicao"><span class="n">{nxt()}</span>Sobreposição com outros candidatos</h2>')
    if len(sob):
        alto = sob.sort_values("sobreposicao", ascending=False).iloc[0]
        baixo = sob.sort_values("sobreposicao").iloc[0]
        comp_ = sob[sob["correlacao"].notna()].sort_values("correlacao")
        txt = (f'A distribuição dos votos de <b>{esc(nome)}</b> pelos municípios coincide mais com a de '
               f'<b>{esc(nome_pt(alto["nome"]))}</b> ({esc(alto["sigla"])}), com {fnum(alto["sobreposicao"], 0)}% de sobreposição, e menos '
               f'com a de {esc(nome_pt(baixo["nome"]))} ({esc(baixo["sigla"])}), com {fnum(baixo["sobreposicao"], 0)}%. '
               f'Como referência, só pelo tamanho do eleitorado de cada município a sobreposição esperada seria de {fnum(base, 0)}%.')
        if len(comp_):
            c0 = comp_.iloc[0]
            txt += (f' A relação mais &quot;complementar&quot; é com {esc(nome_pt(c0["nome"]))} ({esc(c0["sigla"])}), '
                    f'com correlação de {fnum(c0["correlacao"], 2)}.')
        acima = int((sob["sobreposicao"] > base + 2).sum())
        txt += (f' {acima} de {len(sob)} ficam acima da referência por mais de 2 pontos.' if acima else
                ' Nenhum passa da referência por mais de 2 pontos: a sobreposição se explica, em grande parte, só pelo tamanho dos municípios.')
        a(f'<p class="lead">{txt}</p>')
    a(f'<div class="prose"><p>Esta seção responde se {esc(nome)} disputa o mesmo eleitor de outros candidatos ou abriu território próprio. '
      'Cada candidato é comparado com ele de três formas:</p><ul>'
      '<li><b>Sobreposição de base</b>: distribui os votos de cada candidato pelos municípios (cada município com a sua fatia do total) e '
      'soma a parte que coincide. 100% é a mesma distribuição; 0% é nenhum município em comum. Quem ganha votos em Porto Alegre '
      'naturalmente se sobrepõe a todos, porque lá há muito eleitor; por isso a referência acima mostra o que o tamanho do eleitorado '
      'sozinho produziria. Só vale destacar o que passa dela.</li>'
      '<li><b>Correlação</b>: entre as % de votos válidos dos dois, município a município. Positiva, onde um vai bem o outro também; '
      'negativa, os dois se complementam e um é forte onde o outro é fraco.</li>'
      '<li><b>Moran bivariado</b>: compara a % dele num município com a % do outro nos municípios vizinhos. Positivo, os dois formam manchas '
      'nas mesmas regiões. Negativo, onde ele é forte a vizinhança do outro é fraca: territórios diferentes.</li></ul>'
      '<p>&quot;Resto da federação&quot; soma os votos dos demais candidatos dos partidos da federação dele.</p></div>')
    if len(sob):
        rows = [{"label": (nome_pt(r.nome) + f" ({r.sigla})")[:34], "value": float(r.sobreposicao), "fmt": fnum(r.sobreposicao, 0),
                 "tip": _tip(f"{nome_pt(r.nome)} ({r.sigla})", [("Sobreposição de base", fnum(r.sobreposicao, 1) + "%"),
                                                                ("Correlação", fnum(r.correlacao, 2)),
                                                                ("Moran bivariado", fnum(r.moran_bv, 2)),
                                                                ("Votos", fnum(r.votos))])}
                for r in sob.itertuples()]
        a('<div class="card"><h3>Sobreposição de base (%)</h3><div class="scroll">' + svgviz.bar_chart(rows, "Sobreposição") +
          f'</div><p style="margin:10px 0 0;font-size:12.5px;color:var(--muted)">Referência pelo tamanho do eleitorado: {fnum(base, 0)}%.</p></div>')
        t = sob.copy()
        t["candidato"] = [nome_pt(n_) + (" (federação)" if m_ else "") for n_, m_ in zip(t["nome"], t["mesma_federacao"])]
        t["vs_ref"] = t["sobreposicao"] - base
        a(tabela(t, [("candidato", "Candidato", "t"), ("sigla", "Partido", "t"), ("votos", "Votos", "i"),
                     ("sobreposicao", "Sobreposição %", "d1"), ("vs_ref", "Contra a referência (p.p.)", "d1"), ("correlacao", "Correlação", "d2"),
                     ("moran_bv", "Moran bivariado", "d2"), ("moran_bv_p", "p do Moran", "d2")], 30, uid="tb-sobre"))

    tem_fed = not meta["federacao"].get("sem_colegas")
    if tem_fed:
        # ---------------- Federação
        f = meta["federacao"]
        a(f'<h2 id="federacao"><span class="n">{nxt()}</span>Participação na federação</h2>')
        a(f'<p class="lead">A federação {esc(f.get("nome", ""))} teve {fnum(f["fed_votos"])} votos nominais no estado '
          f'({fnum(f["fed_pct_estado"], 1)}% dos votos válidos). <b>{esc(nome)}</b> ficou com <b>{fnum(f["part_fed_estado"], 1)}%</b> deles. '
          f'Em {f["n_abaixo"]} municípios ele recebeu menos do que essa participação média indicaria e em {f["n_acima"]} recebeu mais.</p>')
        a(f'<div class="prose"><p>{esc(nome)} divide o eleitor da federação com os colegas de chapa. A pergunta aqui é: dado quanto a federação '
          'votou em cada município, ele ficou com mais ou menos do que a sua participação média? <b>Participação</b> é a parcela dos votos '
          'da federação que foi para ele. <b>Esperado</b> é o que ele teria se tivesse a participação média do estado '
          f'({fnum(f["part_fed_estado"], 1)}%) em cada município. <b>Diferença</b> é esperado menos o que teve: positiva quando ele '
          'ficou abaixo.</p><p>Soma da diferença nos municípios em que ele ficou abaixo: '
          f'<b>{fnum(f["votos_a_mais"])} votos</b>. Não é uma projeção: esses votos sairiam de colegas de federação, não de adversários. '
          'Serve para apontar onde o eleitor do campo existe e a campanha dele não chegou.</p></div>')
        cq1, l1 = svgviz.classes_quantil(gmx["part_fed"].where(gmx["fed_votos"] > 0, 0), 6, unit="%")
        cq2, l2 = svgviz.classes_quantil(gmx["fed_pct"], 6, unit="%")
        cq3, l3 = svgviz.classes_quantil(gmx["dif_fed"].clip(lower=0), 6, inteiro=True)
        l1 = _sem_votos(l1, "sem votos da federação")
        l3 = _sem_votos(l3, "sem diferença")

        def tip_f(r):
            return _tip(nome_pt(r.NM_MUNICIPIO), [("Votos dele", fnum(r.votos)), ("Votos da federação", fnum(r.fed_votos)),
                                                  ("Participação dele", fnum(r.part_fed, 1) + "%"),
                                                  ("Esperado pela participação média", fnum(r.esperado_fed)),
                                                  ("Diferença", fnum(r.dif_fed))])
        a(_mapa_extra("mapa-fed", polys, gmx, [
            ("part", "Participação dele", "Parcela dos votos da federação no município que foi para ele.", cq1, l1),
            ("fed", "% válidos da federação", "Força da federação no município, sem contar a participação dele.", cq2, l2),
            ("dif", "Votos abaixo do esperado", "Quantos votos a mais ele teria se tivesse a participação média da federação.", cq3, l3),
        ], tip_f, proj, "Participação na federação"))
        top_f = gmx[gmx["dif_fed"] > 0].sort_values("dif_fed", ascending=False).copy()
        top_f["NM"] = top_f["NM_MUNICIPIO"].map(nome_pt)
        a("<h3>Onde ele ficou mais abaixo do esperado pela federação</h3>")
        a(tabela(top_f, [("NM", "Município", "t"), ("votos", "Votos dele", "i"), ("fed_votos", "Votos da federação", "i"),
                         ("part_fed", "Participação %", "d1"), ("esperado_fed", "Esperado", "i"), ("dif_fed", "Diferença", "i")],
                 20, uid="tb-fed"))

        # ---------------- Modelo
        m = meta["modelo"]
        coef = an["modelo"]
        a(f'<h2 id="modelo"><span class="n">{nxt()}</span>Modelo: acima e abaixo do esperado</h2>')
        mo_txt = ("ainda há um padrão geográfico que o modelo não explica (resíduos com autocorrelação), o que costuma indicar efeitos regionais"
                  if m["moran_res_p"] < 0.05 else "os resíduos não formam manchas, então o modelo capturou o essencial da geografia")
        a(f'<p class="lead">Um modelo simples explica {fnum(100 * m["r2"], 0)}% da variação (R² ponderado pelo tamanho dos municípios) da % de votos válidos do {esc(nome)} entre os '
          f'{m["n"]} municípios. Os resíduos mostram onde ele vota bem acima ou abaixo do que o modelo prevê: {m["n_acima"]} municípios acima e '
          f'{m["n_abaixo"]} abaixo. Sobre os resíduos, {mo_txt}.</p>')
        a('<div class="prose"><p><b>O que o modelo faz.</b> Prevê a % de votos válidos dele em cada município a partir de quatro coisas que '
          'não dependem da campanha dele: o tamanho do eleitorado, a abstenção, a votação do resto da federação no município e a votação do '
          'resto da federação nos vizinhos. Municípios maiores pesam mais na estimativa (ponderação pelos votos válidos). A diferença entre o '
          'que ele teve e o que o modelo previu é o <b>resíduo</b>: positivo, ele foi melhor do que o contexto indica; negativo, pior.</p>'
          '<p><b>Como usar.</b> Resíduo muito positivo sugere liderança local, campanha forte ou voto de nicho: vale entender e replicar. '
          'Resíduo muito negativo, em município onde a federação vai bem, é o lugar onde mais falta: o contexto favorece e o voto não veio. '
          'É um retrato do que aconteceu, não uma explicação causal. Variáveis que não entraram (renda, escolaridade, religião, '
          'visitas de campanha) ficam nos resíduos.</p></div>')
        ct = coef[coef["variavel"] != "const"].copy()
        fr = []
        for r in ct.itertuples():
            if r.p < 0.05:
                sinal = "mais" if r.efeito_1dp > 0 else "menos"
                fr.append(f'{r.rotulo.lower()}: 1 desvio-padrão acima da média está associado a {fnum(abs(r.efeito_1dp), 2)} ponto(s) '
                          f'percentual(is) {sinal} de votos válidos')
        if fr:
            a('<div class="callout"><b>Efeitos estatisticamente significativos (p &lt; 0,05):</b> ' + "; ".join(fr) + ".</div>")
        else:
            a('<div class="callout">Nenhuma das variáveis tem efeito estatisticamente significativo isolado.</div>')
        fed_p = ct.loc[ct["variavel"].isin(["fed_outros_pct", "fed_viz_pct"]), "p"]
        if len(fed_p) and (fed_p >= 0.05).all():
            a('<div class="callout">A votação do resto da federação, no município e nos vizinhos, não acrescenta poder de explicação depois de '
              'considerado o tamanho do município. Ou seja, o voto dele não acompanha a força da federação: ele vai bem e mal em lugares '
              'diferentes dos colegas de chapa.</div>')
        a('<div style="margin-bottom:16px">' + tabela(ct, [("rotulo", "Variável", "t"), ("efeito_1dp", "Efeito de +1 desvio-padrão (p.p.)", "d2"),
                      ("t", "t (erro robusto)", "d2"), ("p", "p", "d2")], 10, uid="tb-modelo") + "</div>")
        z = gmx["z_residuo"].to_numpy(float)
        cat = np.where(z > 2, "Acima do esperado", np.where(z < -2, "Abaixo do esperado", "Dentro do esperado"))
        ccat, lcat = svgviz.classes_categoria(list(cat), {"Acima do esperado": "hh", "Abaixo do esperado": "ll", "Dentro do esperado": "ns"},
                                              ["Acima do esperado", "Abaixo do esperado", "Dentro do esperado"])
        cq4, l4 = svgviz.classes_quantil(gmx["pct_previsto"].clip(lower=0), 6, unit="%")

        def tip_m(r):
            return _tip(nome_pt(r.NM_MUNICIPIO), [("% válidos dele", fnum(r.pct_validos, 2) + "%"),
                                                  ("% previsto pelo modelo", fnum(r.pct_previsto, 2) + "%"),
                                                  ("Votos dele", fnum(r.votos)), ("Votos esperados", fnum(r.votos_esperados)),
                                                  ("Diferença em votos", fnum(r.dif_modelo))])
        a(_mapa_extra("mapa-modelo", polys, gmx, [
            ("res", "Resíduo", "Vermelho: ele vai melhor que o previsto. Azul: pior. Só destaca desvios acima de 2 desvios-padrão.", ccat, lcat),
            ("prev", "% previsto", "O que o modelo previu para cada município.", cq4, l4),
        ], tip_m, proj, "Resíduos do modelo"))
        g2 = gmx.copy()
        g2["NM"] = g2["NM_MUNICIPIO"].map(nome_pt)
        pos = g2[g2["z_residuo"] > 0].sort_values("dif_modelo", ascending=False)
        neg = g2[g2["z_residuo"] < 0].sort_values("dif_modelo")
        cols_m = [("NM", "Município", "t"), ("votos", "Votos", "i"), ("votos_esperados", "Votos esperados", "i"),
                  ("dif_modelo", "Diferença", "i"), ("z_residuo", "Resíduo padronizado", "d2")]
        a("<h3>Onde foi mais acima do esperado (em votos)</h3>")
        a(tabela(pos, cols_m, 15, uid="tb-mod-pos"))
        a("<h3>Onde ficou mais abaixo do esperado (em votos)</h3>")
        a(tabela(neg, cols_m, 15, uid="tb-mod-neg"))

    # ---------------- Distância
    dm = meta["distancia"]
    ba = an["bandas"].copy()
    a(f'<h2 id="distancia"><span class="n">{nxt()}</span>Distância dos redutos</h2>')
    sinal = ("cai" if dm["spearman"] < -0.1 else "sobe" if dm["spearman"] > 0.1 else "quase não muda")
    sig = ""
    a(f'<p class="lead">{fnum(dm["votos_ate_100"], 0)}% dos votos dele vêm de municípios a até 100 km do reduto mais próximo e '
      f'{fnum(dm["votos_ate_200"], 0)}% a até 200 km. Fora dos redutos, a % de votos válidos {sinal} com a distância '
      f'(correlação de Spearman {fnum(dm["spearman"], 2)}, descritiva){sig}.</p>')
    a('<div class="prose"><p><b>Como foi calculado.</b> Os redutos são os ' + str(dm["k"]) + ' municípios onde ele mais votou: ' +
      esc(", ".join(nome_pt(x) for x in dm["redutos"])) + '. Para cada município mede-se a distância em linha reta, entre os centros dos '
      'municípios, até o reduto mais próximo. Os municípios são agrupados em faixas de distância e, em cada faixa, calcula-se a % de votos '
      'válidos que ele teve (votos dele ÷ votos válidos de todos os municípios da faixa).</p>'
      '<p><b>Como ler.</b> Se a % cai de forma regular com a distância, o voto &quot;irradia&quot; dos redutos e a campanha pode crescer pelas '
      'bordas. Se ela se mantém ou aparece em manchas longe dos redutos, o voto vem de redes próprias (lideranças, categorias) que não '
      'dependem da proximidade e exigem outra estratégia. A distância em linha reta não considera estradas nem a rede urbana.</p></div>')
    ba = ba[ba["municipios"] > 0].copy()
    ba["rotulo"] = ba["faixa"].astype(str)
    rows = [{"label": r.rotulo, "value": float(r.pct_validos) if pd.notna(r.pct_validos) else 0.0,
             "fmt": fnum(r.pct_validos, 2) + "%" if pd.notna(r.pct_validos) else "–",
             "tip": _tip(r.rotulo, [("Municípios", fnum(r.municipios)), ("Votos dele", fnum(r.votos)),
                                    ("% dos votos dele", fnum(r.share_votos, 1) + "%"),
                                    ("% dos votos válidos", fnum(r.pct_validos, 2) + "%" if pd.notna(r.pct_validos) else "")])}
            for r in ba.itertuples()]
    a('<div class="card"><h3>% dos votos válidos por distância do reduto mais próximo</h3><div class="scroll">'
      + svgviz.bar_chart(rows, "Votação por faixa de distância") + "</div></div>")
    a(tabela(ba, [("rotulo", "Faixa de distância", "t"), ("municipios", "Municípios", "i"), ("votos", "Votos", "i"),
                  ("share_votos", "% dos votos dele", "d1"), ("pct_validos", "% válidos", "d2")], 10, uid="tb-dist"))
    cd, ld = svgviz.classes_quantil(gmx["dist_reduto_km"], 6, unit=" km")
    ld = _sem_votos(ld, "reduto")

    def tip_d(r):
        return _tip(nome_pt(r.NM_MUNICIPIO), [("Distância ao reduto mais próximo", fnum(r.dist_reduto_km, 0) + " km"),
                                              ("Reduto mais próximo", nome_pt(r.reduto_proximo) if r.reduto_proximo else ""),
                                              ("% válidos dele", fnum(r.pct_validos, 2) + "%"), ("Votos", fnum(r.votos))])
    a(_mapa_extra("mapa-dist", polys, gmx, [("dist", "Distância", "Distância em linha reta ao reduto mais próximo.", cd, ld)],
                  tip_d, proj, "Distância dos redutos"))

