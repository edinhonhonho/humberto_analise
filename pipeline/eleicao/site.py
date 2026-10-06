"""Escreve o relatório como site estático em pastas, ou como um único HTML offline.

site/
  index.html                         entrada: escolha de ano, UF, cargo e busca de candidato
  assets/app.<hash>.css|js           estilo e comportamento compartilhados (cache longo)
  assets/landing.<hash>.js
  data/manifest.json|js              grupos (ano, UF, cargo) existentes
  data/idx/<ano>_<UF>_<cargo>.json|js  candidatos de cada grupo: [número, nome, votos]
  <ano>/<uf>/<cargo>/<número>/index.html + data.js   um relatório por candidato

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
def _assets(raiz: Path) -> dict:
    ad = raiz / "assets"
    ad.mkdir(parents=True, exist_ok=True)
    out = {}
    for nome in ("app.css", "app.js", "landing.js", "switcher.js"):
        txt = _ler(nome)
        stem, ext = nome.rsplit(".", 1)
        novo = f"{stem}.{_hash(txt)}.{ext}"
        for velho in ad.glob(f"{stem}.*.{ext}"):
            if velho.name != novo:
                try:
                    velho.unlink()
                except OSError:  # pasta protegida contra exclusão: o arquivo antigo só fica sem uso
                    pass
        (ad / novo).write_text(txt, encoding="utf-8")
        out[nome] = novo
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


def adicionar_candidato(p: dict, raiz) -> Path:
    """Escreve a página do candidato e atualiza o índice do grupo e o manifesto."""
    raiz = Path(raiz)
    a = _assets(raiz)
    icon, fav = _icones()
    pasta = raiz / str(p["ano"]) / p["uf"].lower() / str(p["cargo_cod"]) / str(p["numero"])
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "data.js").write_text(f'window.__DET={_js(p["det"])};', encoding="utf-8")
    up = "../../../../"
    css = f'<link rel="stylesheet" href="{up}assets/{a["app.css"]}">'
    doc = (_head(p["titulo"], css, fav) +
           f'<body data-root="{up}" data-cur=\'{json.dumps({"ano": p["ano"], "uf": p["uf"], "cargo": p["cargo_cod"], "numero": int(p["numero"])})}\'>'
           f'{_NOSCRIPT}{_corpo(p, icon)}<script src="data.js"></script>'
           f'<script src="{up}assets/{a["app.js"]}"></script><script src="{up}assets/{a["switcher.js"]}"></script></body></html>')
    (pasta / "index.html").write_text(doc, encoding="utf-8")

    chave = f'{p["ano"]}_{p["uf"]}_{p["cargo_cod"]}'
    idx_path = raiz / "data" / "idx" / f"{chave}.json"
    idx = [r for r in _ler_json(idx_path, []) if str(r[0]) != str(p["numero"])]
    idx.append([int(p["numero"]), p["nome"], int(p["votos"])])
    idx.sort(key=lambda r: -r[2])
    _gravar_dados(raiz, f"idx/{chave}", "__IDX", chave, idx)

    man_path = raiz / "data" / "manifest.json"
    man = _ler_json(man_path, {"grupos": []})
    gs = [g for g in man["grupos"] if (g["ano"], g["uf"], g["cargo"]) != (p["ano"], p["uf"], p["cargo_cod"])]
    gs.append({"ano": p["ano"], "uf": p["uf"], "cargo": p["cargo_cod"], "cargo_nome": p["cargo"], "n": len(idx)})
    gs.sort(key=lambda g: (-g["ano"], g["uf"], g["cargo"]))
    man["grupos"] = gs
    _publicar(raiz, man, a, icon, fav)
    return pasta / "index.html"


CARGOS = {1: "Presidente", 3: "Governador", 5: "Senador", 6: "Deputado Federal", 7: "Deputado Estadual"}


def definir_destaques(raiz, lista: list[dict], base_dir, ano_padrao: int) -> None:
    """Candidatos em destaque (cards com foto no topo do site). Cada item: nome, uf, numero, cargo, foto, partido."""
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
                    "cargo": int(d.get("cargo", 6)), "numero": int(d["numero"]), "partido": d.get("partido", ""),
                    "foto": foto})
    (raiz / "data").mkdir(parents=True, exist_ok=True)
    (raiz / "data" / "destaques.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    a = _assets(raiz)
    icon, fav = _icones()
    _publicar(raiz, _ler_json(raiz / "data" / "manifest.json", {"grupos": []}), a, icon, fav)


def _destaques(raiz: Path) -> list[dict]:
    out = []
    for d in _ler_json(raiz / "data" / "destaques.json", []):
        pg = raiz / str(d["ano"]) / d["uf"].lower() / str(d["cargo"]) / str(d["numero"]) / "index.html"
        out.append(d | {"cargo_nome": CARGOS.get(d["cargo"], f'Cargo {d["cargo"]}'), "ok": pg.exists()})
    return out


def _publicar(raiz: Path, man: dict, a: dict, icon: str, fav: str) -> None:
    man["destaques"] = _destaques(raiz)
    _gravar_dados(raiz, "manifest", "__MAN", None, man)
    _landing(raiz, man, a, icon, fav)


def cards_html(destaques: list[dict], prefixo: str = "") -> str:
    """Cards quadrados com foto: cada um leva à análise do candidato."""
    if not destaques:
        return ""
    itens = []
    for d in destaques:
        img = (f'<img src="{prefixo}assets/{html.escape(d["foto"])}" alt="{html.escape(d["nome"])}" loading="lazy">'
               if d.get("foto") else "")
        sub = f'{html.escape(d["cargo_nome"])} · {html.escape(d["uf"])} · nº {d["numero"]}'
        txt = f'<span class="tx"><b>{html.escape(d["nome"])}</b><small>{sub}</small></span>'
        if d["ok"]:
            href = f'{prefixo}{d["ano"]}/{d["uf"].lower()}/{d["cargo"]}/{d["numero"]}/'
            itens.append(f'<a class="dcard" href="{href}" data-href="{href}"><span class="ph">{img}</span>{txt}</a>')
        else:
            itens.append(f'<span class="dcard off"><span class="ph">{img}</span>{txt}</span>')
    return f'<section class="dest" aria-label="Candidatos em destaque">{"".join(itens)}</section>'


def _landing(raiz: Path, man: dict, a: dict, icon: str, fav: str) -> None:
    gs = man["grupos"]
    padrao = next((d for d in man.get("destaques", []) if d["ok"]), None)
    if padrao:  # a entrada do site é a análise do primeiro candidato em destaque; o resto fica no topo da página
        alvo = f'{padrao["ano"]}/{padrao["uf"].lower()}/{padrao["cargo"]}/{padrao["numero"]}/index.html'
        (raiz / "index.html").write_text(
            '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            f'<meta http-equiv="refresh" content="0;url={alvo}"><title>Análise eleitoral</title>'
            '</head><body><p><a href="{alvo}">Abrir a análise de '
            f'{html.escape(padrao["nome"])}</a></p><script>location.replace({json.dumps(alvo)})</script></body></html>',
            encoding="utf-8")
        return
    if len(gs) == 1 and gs[0]["n"] == 1 and not man.get("destaques"):
        ph = [r for r in [_ler_json(raiz / "data" / "idx" / f'{gs[0]["ano"]}_{gs[0]["uf"]}_{gs[0]["cargo"]}.json', [])]][0]
        alvo = f'{gs[0]["ano"]}/{gs[0]["uf"].lower()}/{gs[0]["cargo"]}/{ph[0][0]}/'
        redir = f'<meta http-equiv="refresh" content="0;url={alvo}">'
    else:
        redir = ""
    doc = (_head("Análise eleitoral", f'<link rel="stylesheet" href="assets/{a["app.css"]}">{redir}', fav) +
           f'<body>{_NOSCRIPT}<main class="land"><header class="hd"><div class="mark">{icon}</div>'
           '<p class="eyebrow">Análise espacial das eleições</p><h1>Escolha um candidato</h1>'
           '<p class="sub">Filtre por ano, estado e cargo, ou busque pelo nome ou número.</p></header>'
           + cards_html(man.get("destaques", [])) +
           '<div class="filtros"><label>Ano<select id="fa"></select></label><label>UF<select id="fu"></select></label>'
           '<label>Cargo<select id="fc"></select></label><label class="busca">Candidato'
           '<input id="fn" type="search" placeholder="Nome ou número" autocomplete="off"></label></div>'
           '<p class="mhint" id="linfo"></p><ul class="lista" id="lista"></ul></main>'
           f'<script src="data/manifest.js"></script><script src="assets/{a["landing.js"]}"></script></body></html>')
    (raiz / "index.html").write_text(doc, encoding="utf-8")
