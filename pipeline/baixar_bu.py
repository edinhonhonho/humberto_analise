#!/usr/bin/env python3
"""Baixa os boletins de urna (BU) do TSE e gera o arquivo votacao_secao_ANO_UF.csv.

Use quando o CSV "votação por seção" ainda não foi publicado no Portal de Dados Abertos.
Não precisa instalar nada além do Python 3.8+.

    python baixar_bu.py --uf RS                      # todo o estado, cargo 7 (dep. estadual)
    python baixar_bu.py --uf RS --limite 30          # teste rápido com 30 seções
    python baixar_bu.py --uf RS --cargos 7,6         # mais de um cargo
    python baixar_bu.py --uf RS --so-candidatos      # só a lista de candidatos (nome, partido, votos)

O download pode ser interrompido (Ctrl+C) e retomado: o que já foi baixado fica em
dados/bu_RS_<pleito>.jsonl. Ao final grava dados/votacao_secao_<ano>_<UF>.csv, que o rodar.py
já encontra sozinho.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from base64 import urlsafe_b64decode
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from bu.decode import BoletimInvalido, decodificar

BASE = "https://resultados.tse.jus.br/oficial"
CARGOS = {1: "Presidente", 3: "Governador", 5: "Senador", 6: "Deputado Federal", 7: "Deputado Estadual"}


def get(url: str, tentativas: int = 4, timeout: int = 40) -> bytes:
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (analise-eleitoral)"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404 or i == tentativas - 1:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if i == tentativas - 1:
                raise
        time.sleep(1.5 * (i + 1))
    raise RuntimeError("inalcançável")


def payload_jws(raw: bytes) -> dict:
    p = raw.decode().strip().split(".")[1]
    return json.loads(urlsafe_b64decode(p + "=" * (-len(p) % 4)))


def baixar_candidatos(base: str, ano: int, uf: str, eleicao: int, cargo: int, pasta: Path) -> Path | None:
    """Lista oficial de candidatos do cargo (nome, partido, situação e votos totais) a partir do
    resultado consolidado do estado. Serve para dar nome e sigla aos números dos boletins e para
    conferir os totais. Grava dados/candidatos_<ano>_<UF>.csv."""
    uf_l = uf.lower()
    url = f"{base}/ele{ano}/{eleicao}/dados/{uf_l}/{uf_l}-c{cargo:04d}-e{eleicao:06d}-u.jws"
    try:
        d = payload_jws(get(url))
    except Exception as e:  # noqa: BLE001
        print(f"  não consegui a lista de candidatos ({e}); a comparação usará só os números.")
        return None
    carg = next((c for c in d.get("carg", []) if str(c.get("cd")) == str(cargo)), None)
    if not carg:
        print("  a lista de candidatos veio sem o cargo pedido.")
        return None
    destino = pasta / f"candidatos_{ano}_{uf}.csv"
    n = 0
    with destino.open("w", encoding="utf-8", newline="") as fo:
        w = csv.writer(fo, delimiter=";", quoting=csv.QUOTE_ALL)
        w.writerow(["NR_CANDIDATO", "NM_URNA_CANDIDATO", "NM_CANDIDATO", "SG_PARTIDO", "FEDERACAO",
                    "DS_SIT_TOT_TURNO", "QT_VOTOS_OFICIAL"])
        for agr in carg.get("agr", []):
            for par in agr.get("par", []):
                for k in par.get("cand", []):
                    w.writerow([k.get("n"), k.get("nmu"), k.get("nm"), par.get("sg"),
                                k.get("fed") or par.get("nfed") or "", k.get("st"), k.get("vap")])
                    n += 1
    print(f"  candidatos: {n} -> {destino}")
    return destino


def listar_secoes(base: str, ano: int, pleito: int, uf: str) -> list[dict]:
    uf_l = uf.lower()
    url = f"{base}/ele{ano}/arquivo-urna/{pleito}/config/{uf_l}/{uf_l}-p{pleito:06d}-cs.json"
    cfg = json.loads(get(url))
    out = []
    for abr in cfg["abr"]:
        for mu in abr["mu"]:
            for zn in mu["zon"]:
                for sc in zn["sec"]:
                    out.append({"mun": mu["cd"], "nm": mu["nm"], "zona": zn["cd"], "secao": sc["ns"]})
    return out


def _dkey(d: str) -> str:
    p = d.split("/")
    return "".join(reversed(p)) if len(p) == 3 else d


def baixar_secao(base, ano, pleito, uf, s) -> dict:
    uf_l = uf.lower()
    pasta = f"{base}/ele{ano}/arquivo-urna/{pleito}/dados/{uf_l}/{s['mun']}/{s['zona']}/{s['secao']}"
    aux = payload_jws(get(f"{pasta}/p{pleito:06d}-{uf_l}-m{s['mun']}-z{s['zona']}-s{s['secao']}-aux.jws"))
    hs = aux.get("hashes") or []
    if not hs:
        raise BoletimInvalido("sem boletim publicado")
    h = max(hs, key=lambda x: (_dkey(x.get("dr", "")), x.get("hr", "")))  # o mais recente
    nome = next(a["nm"] for a in h["arq"] if a["tp"] == "bu")
    dados = get(f"{pasta}/{h['hash']}/{nome}")
    bu = decodificar(dados)
    return {**s, "local": bu["local"], "eleicoes": bu["eleicoes"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--uf", default="RS")
    ap.add_argument("--ano", type=int, default=2026)
    ap.add_argument("--pleito", type=int, default=3220,
                    help="código do pleito no endereço do TSE (arquivo-urna/<pleito>/); 3220 = 1º turno 2026")
    ap.add_argument("--turno", type=int, default=1)
    ap.add_argument("--cargos", default="7", help="códigos separados por vírgula (7 = dep. estadual)")
    ap.add_argument("--pasta", default="dados")
    ap.add_argument("--threads", type=int, default=6)
    ap.add_argument("--limite", type=int, default=0, help="só as N primeiras seções (teste)")
    ap.add_argument("--candidatos", default=None,
                    help="opcional: consulta_cand_ANO_UF.csv do TSE, para preencher o nome dos candidatos")
    ap.add_argument("--eleicao", type=int, default=6259,
                    help="código da eleição no endereço do TSE (ele<ano>/<eleicao>/); 6259 = cargos proporcionais 2026")
    ap.add_argument("--so-candidatos", action="store_true",
                    help="só baixa a lista de candidatos (nome, partido, votos oficiais) e termina")
    ap.add_argument("--base", default=BASE, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)

    cargos = [int(x) for x in a.cargos.split(",") if x.strip()]
    pasta = Path(a.pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    if a.so_candidatos:
        return 0 if baixar_candidatos(a.base, a.ano, a.uf, a.eleicao, cargos[0], pasta) else 1
    cache = pasta / f"bu_{a.uf}_{a.pleito}.jsonl"
    erros_path = pasta / f"bu_{a.uf}_{a.pleito}_erros.txt"

    print(f"Lendo a lista de seções de {a.uf} ...", flush=True)
    secoes = listar_secoes(a.base, a.ano, a.pleito, a.uf)
    if a.limite:
        secoes = secoes[:a.limite]
    nomes_mun = {s["mun"]: s["nm"] for s in secoes}
    print(f"  {len(secoes):,} seções em {len(nomes_mun)} municípios", flush=True)

    feitos = {}
    if cache.exists():
        for linha in cache.read_text(encoding="utf-8").splitlines():
            if linha.strip():
                r = json.loads(linha)
                feitos[(r["mun"], r["zona"], r["secao"])] = r
    pend = [s for s in secoes if (s["mun"], s["zona"], s["secao"]) not in feitos]
    print(f"  já baixadas: {len(feitos):,} · a baixar: {len(pend):,}", flush=True)

    erros = []
    trava = threading.Lock()
    t0 = time.time()
    if pend:
        with cache.open("a", encoding="utf-8") as fh, ThreadPoolExecutor(a.threads) as ex:
            futs = {ex.submit(baixar_secao, a.base, a.ano, a.pleito, a.uf, s): s for s in pend}
            try:
                for i, f in enumerate(as_completed(futs), 1):
                    s = futs[f]
                    try:
                        r = f.result()
                        with trava:
                            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                            fh.flush()
                        feitos[(r["mun"], r["zona"], r["secao"])] = r
                    except Exception as e:  # noqa: BLE001
                        erros.append(f"{s['mun']}/{s['zona']}/{s['secao']}: {e}")
                    if i % 200 == 0 or i == len(pend):
                        v = i / (time.time() - t0)
                        falta = (len(pend) - i) / v if v else 0
                        print(f"  {i:,}/{len(pend):,} ({v:.1f}/s, faltam ~{falta / 60:.0f} min, "
                              f"{len(erros)} erros)", flush=True)
            except KeyboardInterrupt:
                print("\nInterrompido. Rode de novo para continuar de onde parou.")
                for f in futs:
                    f.cancel()
                return 1
    if erros:
        erros_path.write_text("\n".join(erros), encoding="utf-8")
        print(f"  {len(erros)} seção(ões) sem boletim; detalhes em {erros_path}")

    nomes_cand = {}
    if a.candidatos:
        import pandas as pd
        c = pd.read_csv(a.candidatos, sep=";", encoding="latin-1", dtype=str, low_memory=False)
        c.columns = [x.strip().upper() for x in c.columns]
        col_nome = "NM_URNA_CANDIDATO" if "NM_URNA_CANDIDATO" in c.columns else "NM_CANDIDATO"
        for r in c.itertuples():
            d = r._asdict()
            nomes_cand[(str(d.get("CD_CARGO")), str(d.get("NR_CANDIDATO")))] = d[col_nome]

    if not a.candidatos:
        baixar_candidatos(a.base, a.ano, a.uf, a.eleicao, cargos[0], pasta)
    saida = pasta / f"votacao_secao_{a.ano}_{a.uf}.csv"
    cols = ["ANO_ELEICAO", "NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO",
            "CD_CARGO", "DS_CARGO", "NR_VOTAVEL", "NM_VOTAVEL", "QT_VOTOS", "NR_LOCAL_VOTACAO", "QT_APTOS"]
    n, problemas = 0, 0
    with saida.open("w", encoding="utf-8", newline="") as fo:
        w = csv.writer(fo, delimiter=";", quoting=csv.QUOTE_ALL)
        w.writerow(cols)
        for key in sorted(feitos):
            r = feitos[key]
            for el in r["eleicoes"]:
                for cod, c in el["cargos"].items():
                    cod = int(cod)
                    if cod not in cargos:
                        continue
                    esperado = c["comparecimento"] * (2 if cod == 5 else 1)
                    if c["soma"] != esperado:
                        problemas += 1
                    for numero, qtd in c["votos"]:
                        nome = nomes_cand.get((str(cod), str(numero)), "")
                        w.writerow([a.ano, a.turno, a.uf, int(r["mun"]), nomes_mun.get(r["mun"], ""),
                                    int(r["zona"]), int(r["secao"]), cod, CARGOS.get(cod, cod), numero,
                                    nome, qtd, r["local"], el["aptos"]])
                        n += 1
    print(f"\nPronto: {saida}  ({len(feitos):,} seções, {n:,} linhas)")
    if problemas:
        print(f"  ATENÇÃO: {problemas} boletim(ns) com soma de votos diferente do comparecimento.")
    else:
        print("  Conferência: em todas as seções a soma dos votos bate com o comparecimento.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
