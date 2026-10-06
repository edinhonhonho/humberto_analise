"""Escreve o relatório como site estático em pastas, ou como um único HTML offline.

site/
  index.html                         redireciona para o primeiro candidato em destaque
  gerar.html                         pede ao servir.py que gere uma análise ainda não feita
  assets/app.css|js, switcher.js     estilo e comportamento (a versão vai na URL: ?v=<hash>)
  data/manifest.json|js              grupos (ano, UF, cargo) e destaques
  data/idx/<ano>_<UF>_<cargo>.json|js  candidatos do grupo: [número, nome, votos, análise pronta (1/0)]
  <ano>/<uf>/<cargo>/<número>/index.html + data.js   um relatório por candidato (cargo pelo nome: senador,
                                     governador, deputado-federal, deputado-estadual)

Cada candidato novo só escreve a sua pasta e atualiza o índice do seu grupo e o manifesto, então o
site cresce candidato a candidato sem refazer o resto. Os dados são arquivos .js (window.__X = ...),
que funcionam também abrindo o index.html direto do disco.
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
            f'<title>{html.escape(titulo)}</title><link rel="icon" href="{favicon}">{css}</head>')


_NOSCRIPT = ('<noscript><p style="margin:16px 20px;font-size:13px;color:#5c5551">Sem JavaScript os mapas e tabelas '
             'aparecem, mas a busca por município, o painel de detalhes e a ordenação das tabelas ficam desativados.</p></noscript>')


def _corpo(p: dict, icon: str) -> str:
    return (f'{p["nav"]}<main>{p["corpo"]}<footer>{icon}<span>Gerado a partir de dados abertos do TSE e do IBGE.</span></footer></main>')


# ------------------------------------------------------------------ HTML único
def escrever_standalone(p: dict, destino) -> Path:
    icon, fav = _icones()
    doc = (_head(p["titulo"], f"<style>{_ler('app.css')}</style>", fav) +
           f'<body>{_NOSCRIPT}{_corpo(p, icon)}<script>window.__DET={_js(p["det"])}</script>'
           f'<script>{_ler("app.js")}</script></body></html>')
    destino = Path(destino)
    destino.write_text(doc, encoding="utf-8")
    return destino


# ------------------------------------------------------------------ site em pastas
CARGOS = {1: "Presidente", 3: "Governador", 5: "Senador", 6: "Deputado Federal", 7: "Deputado Estadual"}
SLUGS = {1: "presidente", 3: "governador", 5: "senador", 6: "deputado-federal", 7: "deputado-estadual"}
COD_DO_SLUG = {v: k for k, v in SLUGS.items()}


def slug_cargo(cargo: int) -> str:
    return SLUGS.get(int(cargo), f"cargo-{int(cargo)}")


def caminho_pagina(ano, uf, cargo, numero) -> str:
    """Caminho relativo da página de um candidato (termina em /index.html)."""
    return f"{int(ano)}/{str(uf).lower()}/{slug_cargo(cargo)}/{int(numero)}/index.html"


def _assets(raiz: Path) -> dict:
    """Copia CSS e JS com nome fixo; a versão vai na URL (?v=hash), então páginas antigas nunca ficam sem arquivo."""
    ad = raiz / "assets"
    ad.mkdir(parents=True, exist_ok=True)
    out = {}
    for nome in ("app.css", "app.js", "switcher.js", "gerar.js"):
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


_RE_DEFS = re.compile(r'<svg class="defs"[^>]*>.*?</svg>', re.S)
_RE_USE = re.compile(r'<use [^>]*?data-tip="([^"]*)"[^>]*?/>')


def _enxugar(corpo: str, uf: str, raiz: Path):
    """Tira da página o que se repete entre candidatos: traçados dos municípios (arquivo por UF)
    e textos de tooltip dos mapas (vão para data.js). Devolve (corpo, geo_src, tips)."""
    import hashlib
    import html as _h
    m = _RE_DEFS.search(corpo)
    geo = None
    if m:
        svg = m.group(0)
        h = hashlib.sha1(svg.encode("utf-8")).hexdigest()[:10]
        geo = f"geo/{str(uf).upper()}_{h}.js"
        arq = raiz / "assets" / geo
        if not arq.exists():
            arq.parent.mkdir(parents=True, exist_ok=True)
            arq.write_text("document.body.insertAdjacentHTML('afterbegin'," + json.dumps(svg) + ");", encoding="utf-8")
        corpo = corpo.replace(svg, "", 1)
    marcas = [(x.start(), x.group(1)) for x in re.finditer(r'<div class="mapcard" id="([^"]+)"', corpo)]
    tips: dict = {}

    def troca(mm):
        pos = mm.start()
        mid = None
        for ini, nome in marcas:
            if ini <= pos:
                mid = nome
            else:
                break
        tag = mm.group(0)
        did = re.search(r'data-id="(\d+)"', tag)
        if not mid or not did:
            return tag
        try:
            tips.setdefault(mid, {})[did.group(1)] = json.loads(_h.unescape(mm.group(1)))
        except Exception:  # noqa: BLE001
            return tag
        return tag.replace(f' data-tip="{mm.group(1)}"', "")

    corpo = _RE_USE.sub(troca, corpo)
    return corpo, geo, tips


def adicionar_candidato(p: dict, raiz) -> Path:
    """Escreve a página do candidato e atualiza o índice do grupo e o manifesto."""
    raiz = Path(raiz)
    a = _assets(raiz)
    icon, fav = _icones()
    rel = caminho_pagina(p["ano"], p["uf"], p["cargo_cod"], p["numero"])
    pagina = raiz / rel
    pasta = pagina.parent
    pasta.mkdir(parents=True, exist_ok=True)
    up = "../../../../"
    corpo_html, geo, tips = _enxugar(_corpo(p, icon), p["uf"], raiz)
    det = dict(p["det"])
    det["tips"] = tips
    (pasta / "data.js").write_text(f'window.__DET={_js(det)};', encoding="utf-8")
    geo_tag = f'<script src="{up}assets/{geo}"></script>' if geo else ""
    css = f'<link rel="stylesheet" href="{up}assets/{a["app.css"]}">'
    cur = json.dumps({"ano": p["ano"], "uf": p["uf"], "cargo": p["cargo_cod"], "numero": int(p["numero"])})
    doc = (_head(p["titulo"], css, fav) +
           f"<body data-root=\"{up}\" data-cur='{cur}'>"
           f'{_NOSCRIPT}{corpo_html}{geo_tag}<script src="data.js"></script>'
           f'<script src="{up}assets/{a["app.js"]}"></script><script src="{up}assets/{a["switcher.js"]}"></script></body></html>')
    pagina.write_text(doc, encoding="utf-8")
    with _trava(raiz):
        idx = [r for r in _ler_idx(raiz, p["ano"], p["uf"], p["cargo_cod"]) if int(r[0]) != int(p["numero"])]
        idx.append([int(p["numero"]), p["nome"], int(p["votos"]), 1])
        idx.sort(key=lambda r: -r[2])
        _publicar_grupo(raiz, p["ano"], p["uf"], p["cargo_cod"], idx)
    return pagina


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
                        "ok": (raiz / caminho_pagina(d["ano"], d["uf"], d["cargo"], d["numero"])).exists()})
    return out


def _publicar(raiz: Path, man: dict, a: dict, icon: str, fav: str) -> None:
    man["destaques"] = _destaques(raiz)
    try:
        from . import partidos as _p
        man["partidos"] = {str(k): v["sigla"] for k, v in _p._espectros().items()}
        man["espectro"] = {str(k): v["espectro"] for k, v in _p._espectros().items()}
    except Exception:  # noqa: BLE001
        pass
    _gravar_dados(raiz, "manifest", "__MAN", None, man)
    _entrada(raiz, man, a, icon, fav)


def _entrada(raiz: Path, man: dict, a: dict, icon: str, fav: str) -> None:
    """index.html abre direto no primeiro candidato em destaque; gerar.html pede a análise de quem ainda não tem."""
    padrao = next((d for d in man.get("destaques", []) if d["ok"]), None)
    if padrao:
        alvo = caminho_pagina(padrao["ano"], padrao["uf"], padrao["cargo"], padrao["numero"])
        (raiz / "index.html").write_text(
            '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            f'<meta http-equiv="refresh" content="0;url={alvo}"><title>Análise eleitoral</title>'
            f'</head><body><p><a href="{alvo}">Abrir a análise de {html.escape(padrao["nome"])}</a></p>'
            f'<script>location.replace({json.dumps(alvo)})</script></body></html>', encoding="utf-8")
    (raiz / "gerar.html").write_text(
        _head("Gerando análise", f'<link rel="stylesheet" href="assets/{a["app.css"]}">', fav) +
        f'<body><main class="land"><header class="hd"><div class="mark">{icon}</div>'
        '<p class="eyebrow">Análise sob demanda</p><h1 id="gt">Gerando a análise…</h1>'
        '<p class="sub" id="gs">Isso leva cerca de 10 a 20 segundos.</p></header></main>'
        f'<script src="assets/{a["gerar.js"]}"></script></body></html>', encoding="utf-8")
