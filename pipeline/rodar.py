#!/usr/bin/env python3
"""Executor por configuração: lê config.json, acha os arquivos na pasta de dados e roda.

Para mudar de eleição, edite só "ano" (e "numero", se for outro candidato) no config.json,
coloque os arquivos do novo ano na pasta de dados e execute:

    python rodar.py

Nomes reconhecidos na pasta de dados (maiúsculas/minúsculas não importam, .zip ou .csv):
    votacao_secao_{ano}_{uf}        votação por seção
    perfil_eleitor_secao_{ano}_{uf} perfil do eleitorado por seção (eleitores aptos)
    eleitorado_local_votacao_{ano}  (opcional) eleitorado por local de votação: coordenadas e bairro
    qualquer .shp/.gpkg/.geojson/.zip com 'munic' no nome   malha municipal
    despesas*{ano}*                 (opcional) prestação de contas
    regioes*.csv                    (opcional) município -> região
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import run_analysis

BASE = Path(__file__).parent


def achar(pasta: Path, *padroes: str, exclui: tuple[str, ...] = ()) -> Path | None:
    arqs = [p for p in pasta.rglob("*") if p.is_file()]
    for pad in padroes:
        pad = pad.lower()
        hits = [p for p in arqs if pad in p.name.lower() and not any(x in p.name.lower() for x in exclui)]
        hits = [p for p in hits if p.suffix.lower() in (".zip", ".csv", ".shp", ".gpkg", ".geojson", ".json")]
        if hits:
            return sorted(hits, key=lambda p: p.stat().st_size, reverse=True)[0]
    return None


def contexto_uf(cfg, cfg_path: Path, uf: str, multi: bool) -> dict:
    """Acha os arquivos de uma UF e devolve votacao, malha etc. e a função que monta os argumentos."""
    ano = cfg["ano"]
    pasta = Path(cfg["pasta_dados"])
    if not pasta.is_absolute():
        pasta = (cfg_path.parent / pasta).resolve()
    if not pasta.exists():
        sys.exit(f"Pasta de dados não existe: {pasta}")
    votacao = achar(pasta, f"votacao_secao_{ano}_{uf}")
    locais = achar(pasta, f"eleitorado_local_votacao_{ano}", f"local_votacao_{ano}", f"locais_votacao_{ano}")
    excl = ("votacao", "eleitorado", "despesa")
    malha = (achar(pasta, f"{uf}_municipios", exclui=excl) if multi else
             achar(pasta, f"{uf}_municipios", "municipios", "municipio", "munic", exclui=excl))
    perfil = achar(pasta, f"perfil_eleitor_secao_{ano}_{uf}", f"perfil_eleitorado_secao_{ano}",
                   f"perfil_eleitor_secao_{ano}")
    faltando = [n for n, v in (("votação por seção", votacao), ("malha municipal", malha)) if v is None]
    if faltando:
        sys.exit(f"[{uf}] faltam arquivos em {pasta}: {', '.join(faltando)}.\n"
                 f"Esperado, por exemplo: votacao_secao_{ano}_{uf}.csv e {uf}_Municipios_2025.shp "
                 f"(o baixar_rs_completo.py --uf {uf} baixa os dois).")
    despesas = achar(pasta, f"despesas_contratadas_candidatos_{ano}", "despesas")
    regioes = achar(pasta, f"regioes_{uf}") or (None if multi else achar(pasta, "regioes"))
    saida = cfg.get("saida", "saida_{ano}").format(ano=ano, uf=uf)
    site_dir = Path(saida).resolve().parent / "site"

    def lista_candidatos(cargo: int):
        esp = achar(pasta, f"candidatos_{ano}_{uf}_c{cargo}")
        if esp or cargo != 7:
            return esp
        return achar(pasta, f"candidatos_{ano}_{uf}", f"consulta_cand_{ano}_{uf}", f"consulta_cand_{ano}",
                     exclui=("_c1.", "_c3.", "_c5.", "_c6."))

    def montar_args(cargo, numero, nome=None, destino=None, perm=None, cidades=None):
        a = ["--ano", str(ano), "--uf", uf, "--cargo", str(cargo),
             "--turno", str(cfg.get("turno", 1)), "--numero", str(numero),
             "--votacao", str(votacao), "--malha", str(malha),
             "--saida", destino or saida,
             "--top-cidades", str(cidades if cidades is not None else cfg.get("top_cidades", 10)),
             "--h3-res", str(cfg.get("h3_res", "auto")),
             "--permutacoes", str(perm or cfg.get("permutacoes", 999)), "--site", str(site_dir)]
        if cfg.get("cidades") and not destino:
            a += ["--cidades", cfg["cidades"]]
        if locais:
            a += ["--locais", str(locais)]
        if perfil:
            a += ["--perfil", str(perfil)]
        if cfg.get("federacao") and not destino:
            a += ["--federacao", str(cfg["federacao"])]
        cand_ = lista_candidatos(cargo)
        if cand_:
            a += ["--candidatos", str(cand_)]
        if nome:
            a += ["--nome", nome]
        if cfg.get("hex"):
            a += ["--hex"]
        if cfg.get("png"):
            a += ["--png"]
        if despesas and despesas.suffix.lower() in (".zip", ".csv") and cargo == cfg.get("cargo", 7) and uf == cfg["uf"].upper():
            a += ["--despesas", str(despesas)]
        if regioes:
            a += ["--regioes", str(regioes)]
        return a

    return {"uf": uf, "votacao": votacao, "malha": malha, "perfil": perfil, "locais": locais,
            "despesas": despesas, "regioes": regioes, "saida": saida, "site_dir": site_dir,
            "lista_candidatos": lista_candidatos, "montar_args": montar_args}


def main():
    argv = sys.argv[1:]
    args_cli = [x for x in argv if not x.startswith("--")]
    cfg_path = Path(args_cli[0]) if args_cli else BASE / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    ano, uf = cfg["ano"], cfg["uf"].upper()
    ufs = [u.upper() for u in cfg.get("ufs", [uf])]
    multi = len(ufs) > 1
    saida = Path(cfg.get("saida", "saida_{ano}").format(ano=ano, uf=uf))
    site_dir = saida.resolve().parent / "site"
    if cfg.get("destaques"):
        from eleicao import site
        site.definir_destaques(site_dir, cfg["destaques"], cfg_path.parent.resolve(), ano)

    if "--relatorio" in argv:  # refaz só o site e os dashboards a partir dos pacotes já calculados (segundos)
        from eleicao import report
        if (saida / "bundle" / "meta.json").exists():
            dash = report.build_from_bundle(saida / "bundle", saida / "dashboard.html", site_dir)
            print(f"Dashboard refeito: {dash}")
        lote = saida.resolve().parent / (saida.name + "_lote")
        for b in sorted(lote.glob("*/bundle")) if lote.exists() else []:
            report.build_from_bundle(b, b.parent / "dashboard.html", site_dir)
            print(f"  refeito: {b.parent.name}")
        return 0

    if "--lote" in argv or "--destaques" in argv:
        return rodar_lote(cfg, ano, ufs, multi, cfg_path, saida, site_dir,
                          so_destaques="--destaques" in argv and "--lote" not in argv,
                          refazer="--refazer" in argv)

    c = contexto_uf(cfg, cfg_path, uf, multi)
    print("Arquivos usados:")
    for k in ("votacao", "perfil", "locais", "malha", "despesas", "regioes"):
        print(f"  {k:9s}: {c[k]}")
    return run_analysis.main(c["montar_args"](cfg.get("cargo", 7), cfg["numero"], cfg.get("nome")))


LOTE_PADRAO = {"1": 99, "3": 99, "5": 99, "6": 40, "7": 40}  # quantos candidatos mais votados por cargo


def rodar_lote(cfg, ano, ufs, multi, cfg_path, saida, site_dir, so_destaques=False, refazer=False):
    """Analisa os candidatos em destaque e os mais votados de cada cargo, em cada UF, e junta tudo em site/.
    A leitura do CSV é feita uma vez por cargo (fica em cache); quem já está no site é pulado."""
    import time
    import traceback

    from eleicao import tse_io
    lote = {str(k): int(v) for k, v in (cfg.get("lote") or LOTE_PADRAO).items()}
    perm = int(cfg.get("permutacoes_lote", 199))
    cidades = int(cfg.get("top_cidades_lote", 3))
    turno = cfg.get("turno", 1)
    base = saida.resolve().parent / (saida.name + "_lote")
    fila = []  # (uf, cargo, numero, nome, é_destaque)
    for uf in ufs:
        c = contexto_uf(cfg, cfg_path, uf, multi)
        for d in cfg.get("destaques", []):
            if d["uf"].upper() == uf:
                fila.append((uf, int(d.get("cargo", 6)), int(d["numero"]), d["nome"], True))
        if so_destaques:
            continue
        for cargo, n in lote.items():
            raw = tse_io._raw_cargo(c["votacao"], int(cargo), turno, uf)
            nums = tse_io.mais_votados(raw, int(cargo), n)
            fila += [(uf, int(cargo), x, None, False) for x in nums]
            print(f"{uf}, cargo {cargo}: {len(nums)} candidatos na fila")
    vistos, feitos, falhas = set(), 0, []
    t0 = time.time()
    ctxs = {}
    for i, (uf, cargo, num, nome, dest) in enumerate(fila, 1):
        if (uf, cargo, num) in vistos:
            continue
        vistos.add((uf, cargo, num))
        pagina = site_dir / str(ano) / uf.lower() / str(cargo) / str(num) / "index.html"
        if pagina.exists() and not refazer:
            continue
        print(f"\n[{i}/{len(fila)}] {uf}, cargo {cargo}, candidato {num}  ({(time.time() - t0) / 60:.0f} min)", flush=True)
        try:
            c = ctxs.setdefault(uf, contexto_uf(cfg, cfg_path, uf, multi))
            run_analysis.main(c["montar_args"](cargo, num, nome=nome, destino=str(base / f"{uf}_c{cargo}_{num}"),
                                                perm=None if dest else perm, cidades=None if dest else cidades))
            feitos += 1
        except Exception as e:  # noqa: BLE001
            falhas.append((uf, cargo, num, str(e).splitlines()[0] if str(e) else type(e).__name__))
            print(f"  FALHOU: {falhas[-1][3]}", flush=True)
            traceback.print_exc(limit=2)
    print(f"\nLote concluído: {feitos} novos, {len(falhas)} falhas. Site em {site_dir}")
    for uf, c_, num, msg in falhas:
        print(f"  {uf} cargo {c_} nº {num}: {msg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
