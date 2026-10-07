"""Escreve o relatório como site estático (uma página só + um arquivo de dados por candidato) ou como HTML offline.

publico/
  index.html                          a página (casca): barra, cards em destaque, seletor e a área do relatório
  gerar.html                          pede ao servir.py que gere uma análise ainda não feita
  assets/app.css|js, switcher.js      estilo e comportamento (a versão vai na URL: ?v=<hash>)
  assets/static.js                    trechos de texto que se repetem em todos os relatórios (guia, notas)
  assets/geo/<UF>_<hash>.js           traçados dos municípios de cada UF (um arquivo por UF)
  data/manifest.json|js               grupos (ano, UF, cargo), destaques e siglas dos partidos
  data/idx/<ano>_<UF>_<cargo>.json|js candidatos do grupo: [número, nome, votos, análise pronta (1/0)]
  data/c/<ano>/<uf>/<cargo>/<número>.js   os dados de um candidato (texto, tabelas, mapas, detalhes)

A página é aberta como index.html?c=<ano>/<uf>/<cargo>/<número>. Trocar de candidato só busca o arquivo de
dados dele e redesenha a área do relatório, sem recarregar a página. Cada candidato novo escreve o seu arquivo
e atualiza o índice do seu grupo e o manifesto. Os dados são arquivos .js (window.__X = ...), que funcionam
também abrindo o index.html direto do disco.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
from pathlib import Path

WEB = Path(__file__).parent / "web"


def _js(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/").replace(" ", "\\u2028")


def _ler(nome: str) -> str:
    return (WEB / nome).read_text(encoding="utf-8")


def _hash(txt: str) -> str:
    return hashlib.sha1(txt.encode("utf-8")).hexdigest()[:10]


def _icones():
    from . import report
    return report.ICON, report.FAVICON


def _head(titulo: str, css: str, favicon: str) -> str:
    return ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(titulo)}</title><link rel="icon" type="image/svg+xml" href="{favicon}">{css}</head>')


_NOSCRIPT = ('<noscript><p style="margin:16px 20px;font-size:13px;color:#5c5551">Sem JavaScript os mapas e tabelas '
             'aparecem, mas a busca por município, o painel de detalhes e a ordenação das tabelas ficam desativados.</p></noscript>')


def _compactar(blocos: list, det: dict) -> list:
    """Dicas dos mapas: os rótulos (iguais em todos os municípios) vão numa tabela por mapa e o título que
    coincide com o nome do município deixa de ser repetido (0 = usar o nome em det.mun)."""
    mun = (det or {}).get("mun") or {}
    out = []
    for b in blocos or []:
        if b.get("t") != "map" or "tl" in b:
            out.append(b)
            continue
        tl: list = []
        tp = {}
        for cd, (tit, linhas) in b["tp"].items():
            rs = []
            for k, v in linhas:
                if k not in tl:
                    tl.append(k)
                rs.append([tl.index(k), v])
            nome = (mun.get(cd) or {}).get("n")
            tp[cd] = [0 if tit == nome else tit, rs]
        out.append(b | {"tp": tp, "tl": tl})
    return out


def _rodape(icon: str) -> str:
    return f'<footer>{icon}<span>Gerado a partir de dados abertos do TSE e do IBGE.</span></footer>'


# ------------------------------------------------------------------ HTML único
def escrever_standalone(p: dict, destino) -> Path:
    """Arquivo único e offline: CSS, JS, dados e traçados embutidos."""
    from . import report
    icon, fav = _icones()
    P = {"t": p["titulo"], "h": p["corpo"], "b": _compactar(p.get("blocos"), p["det"]), "d": p["det"], "gs": p.get("geo") or ""}
    doc = (_head(p["titulo"], f"<style>{_ler('app.css')}</style>", fav) +
           f'<body>{_NOSCRIPT}{report.NAV}<main id="app"></main><template id="foot">{_rodape(icon)}</template>'
           f'<script>window.__P0={_js(P)}</script><script>{_ler("app.js")}</script></body></html>')
    destino = Path(destino)
    destino.write_text(doc, encoding="utf-8")
    return destino


# ------------------------------------------------------------------ site em pastas
CARGOS = {1: "Presidente", 3: "Governador", 5: "Senador", 6: "Deputado Federal", 7: "Deputado Estadual", 8: "Deputado Distrital"}
SLUGS = {1: "presidente", 3: "governador", 5: "senador", 6: "deputado-federal", 7: "deputado-estadual", 8: "deputado-distrital"}
COD_DO_SLUG = {v: k for k, v in SLUGS.items()}


def slug_cargo(cargo: int) -> str:
    return SLUGS.get(int(cargo), f"cargo-{int(cargo)}")


def chave_pagina(ano, uf, cargo, numero) -> str:
    """Chave de um candidato na URL: index.html?c=<chave>."""
    return f"{int(ano)}/{str(uf).lower()}/{slug_cargo(cargo)}/{int(numero)}"


def caminho_pagina(ano, uf, cargo, numero) -> str:
    """Caminho relativo (dentro do site) do arquivo de dados de um candidato."""
    return f"data/c/{chave_pagina(ano, uf, cargo, numero)}.js"


def _assets(raiz: Path) -> dict:
    """Copia CSS e JS com nome fixo; a versão vai na URL (?v=hash), então páginas antigas nunca ficam sem arquivo."""
    ad = raiz / "assets"
    ad.mkdir(parents=True, exist_ok=True)
    out = {}
    for nome in ("app.css", "app.js", "switcher.js", "gerar.js", "motor.js"):
        txt = _ler(nome)
        (ad / nome).write_text(txt, encoding="utf-8")
        out[nome] = f"{nome}?v={_hash(txt)}"
    return out


def _ler_json(path: Path, padrao):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return padrao


def _gravar_dados(raiz: Path, rel: str, var: str, chave: str | None, obj) -> None:
    d = raiz / "data" / Path(rel).parent
    d.mkdir(parents=True, exist_ok=True)
    base = raiz / "data" / rel
    base.with_suffix(".json").write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if chave:
        txt = f'(window.{var}=window.{var}||{{}})[{json.dumps(chave)}]={_js(obj)};'
    else:
        txt = f"window.{var}={_js(obj)};"
    base.with_suffix(".js").write_text(txt, encoding="utf-8")


def _grupo_chave(ano, uf, cargo) -> str:
    return f"{int(ano)}_{str(uf).upper()}_{slug_cargo(cargo)}"


def _ler_idx(raiz: Path, ano, uf, cargo) -> list:
    return _ler_json(raiz / "data" / "idx" / f"{_grupo_chave(ano, uf, cargo)}.json", [])


def registrar_indice(raiz, ano: int, uf: str, cargo: int, entradas: list) -> None:
    """Grava a lista de candidatos de um grupo ([número, nome, votos]) e marca quais já têm análise pronta."""
    raiz = Path(raiz)
    prontos = {int(r[0]) for r in _ler_idx(raiz, ano, uf, cargo) if len(r) > 3 and r[3]}
    idx = []
    for e in entradas:
        num = int(e[0])
        pronto = int((raiz / caminho_pagina(ano, uf, cargo, num)).exists() or num in prontos)
        idx.append([num, e[1], int(e[2]), pronto])
    idx.sort(key=lambda r: -r[2])
    _publicar_grupo(raiz, ano, uf, cargo, idx)


def _publicar_grupo(raiz: Path, ano, uf, cargo, idx: list) -> None:
    chave = _grupo_chave(ano, uf, cargo)
    _gravar_dados(raiz, f"idx/{chave}", "__IDX", chave, idx)
    man = _ler_json(raiz / "data" / "manifest.json", {"grupos": []})
    gs = [g for g in man["grupos"] if (g["ano"], g["uf"], g["cargo"]) != (int(ano), str(uf).upper(), int(cargo))]
    gs.append({"ano": int(ano), "uf": str(uf).upper(), "cargo": int(cargo), "cargo_slug": slug_cargo(cargo),
               "cargo_nome": CARGOS.get(int(cargo), f"Cargo {cargo}"), "n": len(idx)})
    gs.sort(key=lambda g: (-g["ano"], g["uf"], g["cargo"]))
    man["grupos"] = gs
    a = _assets(raiz)
    icon, fav = _icones()
    _publicar(raiz, man, a, icon, fav)


import contextlib
import os
import time as _time


@contextlib.contextmanager
def _trava(raiz: Path):
    """Exclusão mútua entre processos (vários terminais gerando páginas no mesmo site).
    Usa trava de arquivo do sistema (fcntl/msvcrt): nada precisa ser apagado depois."""
    raiz.mkdir(parents=True, exist_ok=True)
    f = open(raiz / ".trava", "a+b")
    travado = False
    try:
        try:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX)
            travado = True
        except ImportError:
            try:
                import msvcrt
                f.seek(0)
                for _ in range(600):
                    try:
                        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                        travado = True
                        break
                    except OSError:
                        _time.sleep(0.2)
            except ImportError:
                pass
        yield
    finally:
        try:
            if travado:
                try:
                    import fcntl
                    fcntl.flock(f, fcntl.LOCK_UN)
                except ImportError:
                    import msvcrt
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        except Exception:  # noqa: BLE001
            pass
        f.close()


_RE_ESTATICO = re.compile(r'<details class="guide" id="guia">.*?</details>|<aside class="metodo">.*?</aside>', re.S)


def _estaticos(corpo: str, raiz: Path) -> str:
    """Trechos idênticos em todos os relatórios (guia de leitura, notas metodológicas) ficam num arquivo
    só (assets/static.js); a página guarda apenas um marcador <!--S:hash-->."""
    novos: dict = {}

    def troca(m):
        h = _hash(m.group(0))
        novos[h] = m.group(0)
        return f"<!--S:{h}-->"

    corpo = _RE_ESTATICO.sub(troca, corpo)
    arq = raiz / "assets" / "static.js"
    with _trava(raiz):
        atual: dict = {}
        if arq.exists():
            try:
                atual = json.loads(arq.read_text(encoding="utf-8").split("=", 1)[1].rstrip(";\n "))
            except Exception:  # noqa: BLE001
                atual = {}
        if any(k not in atual for k in novos):
            atual.update(novos)
            arq.parent.mkdir(parents=True, exist_ok=True)
            arq.write_text("window.__S=" + _js(atual) + ";", encoding="utf-8")
    return corpo


def _geo(svg: str | None, uf: str, raiz: Path) -> str | None:
    """Traçados dos municípios: um arquivo por UF (e por versão da malha)."""
    if not svg:
        return None
    h = _hash(svg)
    nome = f"{str(uf).upper()}_{h}"
    arq = raiz / "assets" / "geo" / f"{nome}.js"
    if not arq.exists():
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_text(f'(window.__GEO=window.__GEO||{{}})[{json.dumps(nome)}]={_js(svg)};', encoding="utf-8")
    return nome


def adicionar_candidato(p: dict, raiz) -> Path:
    """Escreve o arquivo de dados do candidato e atualiza o índice do grupo e o manifesto."""
    raiz = Path(raiz)
    _assets(raiz)
    rel = caminho_pagina(p["ano"], p["uf"], p["cargo_cod"], p["numero"])
    arq = raiz / rel
    arq.parent.mkdir(parents=True, exist_ok=True)
    corpo = _estaticos(p["corpo"], raiz)
    P = {"t": p["titulo"], "h": corpo, "b": _compactar(p.get("blocos"), p["det"]), "d": p["det"], "g": _geo(p.get("geo"), p["uf"], raiz),
         "m": {"ano": int(p["ano"]), "uf": p["uf"], "cargo": p["cargo_cod"], "numero": int(p["numero"]),
               "nome": p["nome"], "cargo_nome": p["cargo"], "votos": int(p["votos"])}}
    chave = chave_pagina(p["ano"], p["uf"], p["cargo_cod"], p["numero"])
    arq.write_text(f'(window.__P=window.__P||{{}})[{json.dumps(chave)}]={_js(P)};', encoding="utf-8")
    with _trava(raiz):
        idx = [r for r in _ler_idx(raiz, p["ano"], p["uf"], p["cargo_cod"]) if int(r[0]) != int(p["numero"])]
        idx.append([int(p["numero"]), p["nome"], int(p["votos"]), 1])
        idx.sort(key=lambda r: -r[2])
        _publicar_grupo(raiz, p["ano"], p["uf"], p["cargo_cod"], idx)
    return arq


def definir_destaques(raiz, lista: list[dict], base_dir, ano_padrao: int) -> None:
    """Candidatos em destaque (cards com foto no topo do site). Cada item: nome, uf, numero, cargo, foto."""
    raiz, base_dir = Path(raiz), Path(base_dir)
    fd = raiz / "assets" / "fotos"
    fd.mkdir(parents=True, exist_ok=True)
    out = []
    for d in lista:
        slug = d.get("slug") or re.sub(r"[^a-z0-9]+", "-", str(d["nome"]).lower()).strip("-")
        foto = None
        if d.get("foto"):
            src = Path(d["foto"])
            src = src if src.is_absolute() else base_dir / src
            if src.exists():
                destino = fd / f"{slug}.webp"
                try:
                    if src.suffix.lower() == ".webp":
                        shutil.copyfile(src, destino)
                    else:
                        from PIL import Image
                        Image.open(src).convert("RGBA").save(destino, quality=88, method=6)
                    foto = f"fotos/{slug}.webp"
                except Exception:  # noqa: BLE001
                    destino = fd / f"{slug}{src.suffix.lower()}"
                    shutil.copyfile(src, destino)
                    foto = f"fotos/{destino.name}"
        out.append({"slug": slug, "nome": d["nome"], "ano": int(d.get("ano", ano_padrao)), "uf": d["uf"].upper(),
                    "cargo": int(d.get("cargo", 6)), "numero": int(d["numero"]), "foto": foto})
    (raiz / "data").mkdir(parents=True, exist_ok=True)
    (raiz / "data" / "destaques.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    a = _assets(raiz)
    icon, fav = _icones()
    _publicar(raiz, _ler_json(raiz / "data" / "manifest.json", {"grupos": []}), a, icon, fav)


def _destaques(raiz: Path) -> list[dict]:
    out = []
    for d in _ler_json(raiz / "data" / "destaques.json", []):
        out.append(d | {"cargo_nome": CARGOS.get(d["cargo"], f'Cargo {d["cargo"]}'), "cargo_slug": slug_cargo(d["cargo"]),
                        "ok": ((raiz / caminho_pagina(d["ano"], d["uf"], d["cargo"], d["numero"])).exists()
                               or (raiz / "data" / "br" / str(d["ano"]) / d["uf"] / "meta.json").exists())})
    return out


def _publicar(raiz: Path, man: dict, a: dict, icon: str, fav: str) -> None:
    man["destaques"] = _destaques(raiz)
    man["prontos"] = sum(1 for g in man.get("grupos", []) for r in _ler_idx(raiz, g["ano"], g["uf"], g["cargo"]) if len(r) > 3 and r[3])
    try:
        from . import partidos as _p
        man["partidos"] = {str(k): v["sigla"] for k, v in _p._espectros().items()}
        man["espectro"] = {str(k): v["espectro"] for k, v in _p._espectros().items()}
    except Exception:  # noqa: BLE001
        pass
    _gravar_dados(raiz, "manifest", "__MAN", None, man)
    _entrada(raiz, man, a, icon, fav)


def _entrada(raiz: Path, man: dict, a: dict, icon: str, fav: str) -> None:
    """index.html é a casca do site (a página única); gerar.html pede a análise de quem ainda não tem."""
    from . import report
    padrao = next((d for d in man.get("destaques", []) if d["ok"]), None)
    pad = json.dumps(chave_pagina(padrao["ano"], padrao["uf"], padrao["cargo"], padrao["numero"])) if padrao else "null"
    css = f'<link rel="stylesheet" href="assets/{a["app.css"]}">'
    css += ('<script>window.va=window.va||function(){(window.vaq=window.vaq||[]).push(arguments)};</script>'
            '<script defer src="/_vercel/insights/script.js" data-disable-auto-track="1"></script>')
    (raiz / "index.html").write_text(
        _head("Eleições", css, fav) +
        f'<body data-shell="1" data-root="" data-padrao=\'{pad}\'>{_NOSCRIPT}{report.NAV}'
        f'<div id="dest-slot"></div><main id="app"><p class="carregando">Carregando a análise…</p></main>'
        f'<template id="foot">{_rodape(icon)}</template>'
        f'<script src="data/manifest.js"></script>'
        f'<script src="assets/{a["app.js"]}"></script><script src="assets/{a["switcher.js"]}"></script></body></html>',
        encoding="utf-8")
    (raiz / "gerar.html").write_text(
        _head("Gerando análise", f'<link rel="stylesheet" href="assets/{a["app.css"]}">', fav) +
        f'<body><main class="land"><header class="hd"><div class="mark">{icon}</div>'
        '<p class="eyebrow">Análise sob demanda</p><h1 id="gt">Gerando a análise…</h1>'
        '<p class="sub" id="gs">Isso leva cerca de 10 a 20 segundos.</p></header></main>'
        f'<script src="assets/{a["gerar.js"]}"></script></body></html>', encoding="utf-8")
