#!/usr/bin/env python3
"""Baixa os boletins de urna (BU) de TODAS as UFs do país, todos os cargos, e grava um CSV por UF.

É o baixar_rs_completo.py repetido para as 27 UFs, com retomada e relatório no fim:
  - cada UF grava dados/bu_<UF>_<pleito>.jsonl enquanto baixa; se parar (Ctrl+C, queda de rede, PC
    dormindo), é só rodar de novo: continua de onde parou e pula as UFs já concluídas;
  - uma UF que falhar não interrompe as outras; o relatório final lista o que faltou.

    python baixar_brasil.py                       # todas as UFs (leva horas; veja a estimativa abaixo)
    python baixar_brasil.py --uf SP,MG            # só algumas
    python baixar_brasil.py --ordem menor         # começa pelas UFs menores (padrão)
    python baixar_brasil.py --plano               # só mostra o plano e o tamanho, sem baixar
    python baixar_brasil.py --so-malhas           # só as malhas municipais do IBGE de todas as UFs
    python baixar_brasil.py --refazer             # baixa de novo as UFs que já têm CSV
    python baixar_brasil.py --exterior            # inclui ZZ (voto no exterior; só presidente)

Ordem de grandeza (muda com a velocidade da sua conexão): cerca de 470 mil seções no país. Com ~10 a 15
seções por segundo (uma UF por vez) são de 9 a 13 horas; com UFs em paralelo deve cair bastante; o cache .jsonl ocupa ~1 a 2 GB e os CSVs finais alguns GB.
Vários estados são baixados ao mesmo tempo no mesmo terminal (--paralelas, padrão 4; cada um com --threads
conexões). Se a conexão ou o TSE reclamar (muitos erros), diminua: --paralelas 2 --threads 4.
Mantenha o computador ligado e sem suspender. Os nomes dos candidatos podem ser completados depois com
python baixar_nomes.py --consulta ... (arquivo consulta_cand_2026.zip do TSE).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import baixar_rs_completo as rs

UFS = ["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR",
       "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO"]
# seções aproximadas (eleitorado de 2022; só para ordenar e estimar o tempo)
SECOES = {"AC": 2400, "AL": 7000, "AM": 8700, "AP": 1900, "BA": 36000, "CE": 20500, "DF": 7600, "ES": 10500,
          "GO": 16000, "MA": 17500, "MG": 52000, "MS": 6600, "MT": 8800, "PA": 19000, "PB": 9500, "PE": 23000,
          "PI": 8000, "PR": 25500, "RJ": 41000, "RN": 7600, "RO": 3800, "RR": 1500, "RS": 25500, "SC": 14000,
          "SE": 5000, "SP": 111000, "TO": 3900, "ZZ": 900}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--uf", default="", help="UFs separadas por vírgula (padrão: todas)")
    ap.add_argument("--ano", type=int, default=2026)
    ap.add_argument("--pasta", default="dados")
    ap.add_argument("--threads", type=int, default=6, help="conexões simultâneas por UF")
    ap.add_argument("--paralelas", type=int, default=4, help="quantas UFs ao mesmo tempo")
    ap.add_argument("--pleito", type=int, default=3220)
    ap.add_argument("--ordem", choices=["menor", "alfabetica", "maior"], default=None,
                    help="padrão: maior primeiro quando há UFs em paralelo (balanceia melhor), senão menor")
    ap.add_argument("--plano", action="store_true", help="só mostra o plano")
    ap.add_argument("--so-malhas", action="store_true")
    ap.add_argument("--sem-malhas", action="store_true", help="não baixa as malhas do IBGE")
    ap.add_argument("--refazer", action="store_true")
    ap.add_argument("--exterior", action="store_true")
    ap.add_argument("--limite", type=int, default=0, help="teste: só N seções por UF")
    a = ap.parse_args()

    pasta = Path(a.pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    ufs = [u.strip().upper() for u in a.uf.split(",") if u.strip()] or list(UFS)
    if a.exterior and "ZZ" not in ufs:
        ufs.append("ZZ")
    ordem = a.ordem or ("maior" if a.paralelas > 1 else "menor")
    chave = {"menor": lambda u: SECOES.get(u, 0), "maior": lambda u: -SECOES.get(u, 0),
             "alfabetica": lambda u: u}[ordem]
    ufs.sort(key=chave)

    def pronto(uf):
        return (pasta / f"votacao_secao_{a.ano}_{uf}.csv").exists()

    pend = [u for u in ufs if a.refazer or not pronto(u)]
    total = sum(SECOES.get(u, 5000) for u in pend)
    print(f"{len(ufs)} UF(s); {len(ufs) - len(pend)} já concluída(s); a baixar: {', '.join(pend) or 'nenhuma'}")
    print(f"~{total:,} seções a baixar; a 10-15 seções/s: {total / 15 / 3600:.1f} a {total / 10 / 3600:.1f} horas.")
    if a.plano:
        for u in pend:
            print(f"  {u}: ~{SECOES.get(u, 5000):,} seções")
        return 0

    if not a.sem_malhas:
        print("\nMalhas municipais do IBGE ...")
        for u in ufs:
            if u != "ZZ":
                rs.baixar_malha(u, pasta)
    if a.so_malhas:
        return 0

    ok, falhas = [], []
    t0 = time.time()
    saida = threading.Lock()
    procs: list = []

    def rodar(uf):
        cmd = [sys.executable, str(Path(__file__).with_name("baixar_rs_completo.py")), "--uf", uf, "--ano", str(a.ano),
               "--pasta", a.pasta, "--threads", str(a.threads), "--pleito", str(a.pleito)]
        if a.limite:
            cmd += ["--limite", str(a.limite)]
        with saida:
            print(f"[{uf}] começando", flush=True)
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                             errors="replace")
        procs.append(p)
        for linha in p.stdout:
            linha = linha.rstrip()
            if linha.strip():
                with saida:
                    print(f"[{uf}] {linha}", flush=True)
        rc = p.wait()
        with saida:
            print(f"[{uf}] {'concluída' if rc == 0 else 'NÃO terminou (rode de novo para continuar)'}"
                  f" · decorrido {(time.time() - t0) / 3600:.1f} h", flush=True)
        return uf, rc

    try:
        with ThreadPoolExecutor(max(1, a.paralelas)) as ex:
            for uf, rc in ex.map(rodar, pend):
                (ok if rc == 0 else falhas).append(uf)
    except KeyboardInterrupt:
        print("\nInterrompido. Rode de novo para continuar de onde parou.")
        for p in procs:
            try:
                p.terminate()
            except Exception:  # noqa: BLE001
                pass
        return 1

    print("\n================ RESUMO ================")
    print("Concluídas:", ", ".join(ok) or "nenhuma")
    if falhas:
        print("Faltam (rode de novo o mesmo comando):", ", ".join(falhas))
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
