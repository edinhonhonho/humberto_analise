#!/usr/bin/env python3
"""Monta a pasta do site (index.html, assets, dados das UFs e lista de candidatos) a partir de dados_web/.

    python converter_parquet.py --uf todas          (uma vez: CSV -> Parquet)
    python montar_site_web.py                       (gera ../site)
    python montar_site_web.py --servir              (e abre em http://localhost:8000)
    python montar_site_web.py --so PE,RJ,RS         (só estas UFs)
    python montar_site_web.py --sem-paginas-antigas (remove data/c, as páginas pré-calculadas)

O site não guarda mais uma página por candidato: o navegador lê os Parquet da UF (data/br/<ano>/<UF>/) e calcula a
análise de qualquer candidato ao abrir, em etapas (os blocos aparecem à medida que ficam prontos).
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import re
import shutil
import sys
import webbrowser
from pathlib import Path

BASE = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE))

from eleicao import site  # noqa: E402
from eleicao.report import nome_pt  # noqa: E402


def indice_uf(origem: Path, uf: str, ano: int):
    """[(cargo, [[numero, nome, votos, 1], ...])] de todos os candidatos de cada cargo da UF."""
    import duckdb
    nomes = json.loads((origem / "nomes.json").read_text(encoding="utf-8"))
    meta = json.loads((origem / "meta.json").read_text(encoding="utf-8"))
    con = duckdb.connect()
    out = []
    for cargo in meta["cargos"]:
        if cargo not in site.SLUGS or cargo == 1:
            continue
        legenda = "AND votavel > 99" if cargo in (6, 7, 8) else ""
        rows = con.execute(f"""SELECT votavel, SUM(votos) v FROM '{(origem / 'mc.parquet').as_posix()}'
                               WHERE turno = 1 AND cargo = {cargo} {legenda} GROUP BY votavel HAVING SUM(votos) > 0
                               ORDER BY v DESC""").fetchall()
        nm = nomes.get(str(cargo), {})
        idx = [[int(n), nome_pt(nm[str(n)][0]) if str(n) in nm else f"Candidato {int(n)}", int(v), 1] for n, v in rows]
        out.append((cargo, idx))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(BASE / "config.json"))
    ap.add_argument("--dados-web", default="dados_web")
    ap.add_argument("--site", default=None)
    ap.add_argument("--so", default="")
    ap.add_argument("--servir", action="store_true")
    ap.add_argument("--porta", type=int, default=8000)
    ap.add_argument("--sem-paginas-antigas", action="store_true")
    a = ap.parse_args()

    cfg_path = Path(a.config).resolve()
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    ano = int(cfg["ano"])
    origem_base = (Path(a.dados_web) if Path(a.dados_web).is_absolute() else BASE / a.dados_web) / str(ano)
    raiz = Path(a.site).resolve() if a.site else (BASE / Path(cfg.get("saida", "saida_{ano}").format(ano=ano, uf=""))).resolve().parent / "site"
    raiz.mkdir(parents=True, exist_ok=True)
    only = {u.strip().upper() for u in a.so.split(",") if u.strip()}
    ufs = sorted(p.name for p in origem_base.iterdir() if (p / "meta.json").exists()) if origem_base.exists() else []
    ufs = [u for u in ufs if not only or u in only]
    if not ufs:
        sys.exit(f"Nenhuma UF convertida em {origem_base}. Rode: python converter_parquet.py --uf todas")

    if cfg.get("destaques"):
        site.definir_destaques(raiz, cfg["destaques"], cfg_path.parent, ano)
    for uf in ufs:
        origem = origem_base / uf
        destino = raiz / "data" / "br" / str(ano) / uf
        destino.mkdir(parents=True, exist_ok=True)
        for f in origem.iterdir():
            if f.is_file():
                shutil.copyfile(f, destino / f.name)
        n = 0
        for cargo, idx in indice_uf(origem, uf, ano):
            site._publicar_grupo(raiz, ano, uf, cargo, idx)
            n += len(idx)
        print(f"{uf}: {n:,} candidatos listados; dados em {destino.relative_to(raiz)}", flush=True)
    site._publicar(raiz, site._ler_json(raiz / "data" / "manifest.json", {"grupos": []}), site._assets(raiz), *site._icones())
    if a.sem_paginas_antigas:
        for d in ("c",):
            shutil.rmtree(raiz / "data" / d, ignore_errors=True)
    tot = sum(f.stat().st_size for f in raiz.rglob("*") if f.is_file()) / 1e6
    print(f"\nSite em {raiz} ({tot:.0f} MB)")
    if a.servir:
        servir(raiz, a.porta)
    return 0


class Handler(http.server.SimpleHTTPRequestHandler):
    """Servidor estático com requisições parciais (Range), que o leitor de Parquet usa."""

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def send_head(self):
        p = self.translate_path(self.path)
        r = self.headers.get("Range")
        if not r or not Path(p).is_file():
            return super().send_head()
        m = re.match(r"bytes=(\d*)-(\d*)", r)
        size = Path(p).stat().st_size
        if m.group(1) == "":
            a, b = max(0, size - int(m.group(2))), size - 1
        else:
            a, b = int(m.group(1)), int(m.group(2)) if m.group(2) else size - 1
        b = min(b, size - 1)
        f = open(p, "rb")
        f.seek(a)
        self._resta = b - a + 1
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(p))
        self.send_header("Content-Range", f"bytes {a}-{b}/{size}")
        self.send_header("Content-Length", str(b - a + 1))
        self.end_headers()
        return f

    def copyfile(self, src, dst):
        n, self._resta = getattr(self, "_resta", None), None
        if n is None:
            return super().copyfile(src, dst)
        while n > 0:
            buf = src.read(min(n, 1 << 20))
            if not buf:
                break
            dst.write(buf)
            n -= len(buf)

    def log_message(self, *a):
        pass


def servir(raiz: Path, porta: int):
    h = functools.partial(Handler, directory=str(raiz))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", porta), h)
    url = f"http://localhost:{porta}/"
    print(f"Abrindo {url}  (Ctrl+C encerra)")
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())
