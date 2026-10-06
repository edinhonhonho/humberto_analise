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


class FaltaArquivo(Exception):
    pass


NOMES_CARGO = {1: "Presidente", 3: "Governador", 5: "Senador", 6: "Deputado Federal", 7: "Deputado Estadual"}


def cargo_de(txt) -> int:
    """Aceita o código (7) ou o nome (deputado-estadual, senador, governador...)."""
    t = str(txt).strip().lower().replace("_", "-").replace(" ", "-")
    if t.isdigit():
        return int(t)
    from eleicao import site
    return site.COD_DO_SLUG[t]


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
        raise FaltaArquivo(f"[{uf}] faltam arquivos em {pasta}: {', '.join(faltando)}. "
                           f"Esperado, por exemplo: votacao_secao_{ano}_{uf}.csv e {uf}_Municipios_2025.shp "
                           f"(python baixar_rs_completo.py --uf {uf} baixa os dois).")
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
    multi = len(ufs) > 1   # a malha/arquivos seguem o conjunto completo de UFs
    so = [x.split("=", 1)[1] for x in argv if x.startswith("--so=")]
    if so:   # --so=RJ,PE : processa só estas UFs (permite rodar vários terminais em paralelo)
        ufs_filtro = [u.strip().upper() for u in so[0].split(",") if u.strip()]
        ufs = [u for u in ufs if u in ufs_filtro]
    cg = [x.split("=", 1)[1] for x in argv if x.startswith("--cargos=")]
    if cg:   # --cargos=6,7 : processa só estes cargos no lote
        cfg["lote"] = {k: v for k, v in (cfg.get("lote") or LOTE_PADRAO).items() if k in cg[0].split(",")}
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

    if "--indice" in argv:
        indexar(cfg, cfg_path, ano, ufs, multi, site_dir)
        return 0
    if "--um" in argv:  # uma análise sob demanda: --um UF CARGO NUMERO (usado pelo servir.py)
        i = argv.index("--um")
        uf1, cargo1, num1 = argv[i + 1].upper(), cargo_de(argv[i + 2]), int(argv[i + 3])
        return executar_fila([(uf1, cargo1, num1, None, False)], cfg, ano, multi, cfg_path, saida, site_dir, refazer=True)
    if "--lote" in argv or "--destaques" in argv:
        return rodar_lote(cfg, ano, ufs, multi, cfg_path, saida, site_dir,
                          so_destaques="--destaques" in argv and "--lote" not in argv,
                          refazer="--refazer" in argv)

    try:
        c = contexto_uf(cfg, cfg_path, uf, multi)
    except FaltaArquivo as e:
        sys.exit(str(e))
    print("Arquivos usados:")
    for k in ("votacao", "perfil", "locais", "malha", "despesas", "regioes"):
        print(f"  {k:9s}: {c[k]}")
    return run_analysis.main(c["montar_args"](cfg.get("cargo", 7), cfg["numero"], cfg.get("nome")))


LOTE_PADRAO = {"3": 99999, "5": 99999, "6": 99999, "7": 99999}  # quantos candidatos mais votados por cargo (todos)


def indexar(cfg, cfg_path, ano, ufs, multi, site_dir):
    """Lista TODOS os candidatos de cada UF e cargo no site (nome e votos), com a marca de quem já tem análise.
    É o que permite escolher qualquer candidato no botão "Trocar candidato" e gerar a análise na hora."""
    from eleicao import site, tse_io
    from eleicao.report import nome_pt
    lote = [int(k) for k in (cfg.get("lote") or LOTE_PADRAO)]
    turno = cfg.get("turno", 1)
    for uf in ufs:
        try:
            c = contexto_uf(cfg, cfg_path, uf, multi)
        except FaltaArquivo as e:
            print(f"AVISO: {e} {uf} ficou de fora.")
            continue
        for cargo in lote:
            raw = tse_io._raw_cargo(c["votacao"], cargo, turno, uf)
            tot = tse_io.totais_votaveis(raw, cargo)
            nomes = {}
            lc = c["lista_candidatos"](cargo)
            if lc:
                try:
                    df = tse_io.load_candidatos(lc, cargo)
                    if df is not None:
                        nomes = dict(zip(df["numero"].astype(int), df["nome"].astype(str)))
                except Exception:  # noqa: BLE001
                    pass
            entradas = [[int(n), nome_pt(nomes[int(n)]) if nomes.get(int(n), "").strip() not in ("", "nan") else f"Candidato {int(n)}",
                         int(v)] for n, v in tot.items()]
            site.registrar_indice(site_dir, ano, uf, cargo, entradas)
            print(f"  {uf}, {NOMES_CARGO.get(cargo, cargo)}: {len(entradas)} candidatos listados")


def rodar_lote(cfg, ano, ufs, multi, cfg_path, saida, site_dir, so_destaques=False, refazer=False):
    """Analisa os candidatos em destaque e os mais votados de cada cargo, em cada UF, e junta tudo em site/.
    A leitura do CSV é feita uma vez por cargo (fica em cache); quem já está no site é pulado."""
    from eleicao import tse_io
    lote = {str(k): int(v) for k, v in (cfg.get("lote") or LOTE_PADRAO).items()}
    turno = cfg.get("turno", 1)
    ufs_ok = []
    for uf in ufs:
        try:
            contexto_uf(cfg, cfg_path, uf, multi)
            ufs_ok.append(uf)
        except FaltaArquivo as e:
            print(f"AVISO: {e} {uf} será pulado.")
    if not ufs_ok:
        sys.exit("Nenhuma UF com arquivos completos.")
    if "--sem-indice" not in sys.argv:   # o índice já existe: poupa reler os CSVs a cada retomada
        indexar(cfg, cfg_path, ano, ufs_ok, multi, site_dir)
    fila = []  # (uf, cargo, numero, nome, é_destaque)
    for uf in ufs_ok:
        c = contexto_uf(cfg, cfg_path, uf, multi)
        for d in cfg.get("destaques", []):
            if d["uf"].upper() == uf:
                fila.append((uf, int(d.get("cargo", 6)), int(d["numero"]), d["nome"], True))
        if so_destaques:
            continue
        for cargo, n in lote.items():
            raw = tse_io._raw_cargo(c["votacao"], int(cargo), turno, uf)
            mv = (cfg.get("votos_minimos") or {}).get(str(cargo), 0)
            nums = tse_io.mais_votados(raw, int(cargo), n, min_votos=mv)
            esp = cfg.get("espectros")
            if esp:   # só os partidos dos espectros pedidos (ver espectro.json)
                from eleicao.partidos import espectro_de
                antes = len(nums)
                nums = [x for x in nums if espectro_de(x) in esp]
                print(f"  filtro de espectro {esp}: {antes} -> {len(nums)}")
            fila += [(uf, int(cargo), x, None, False) for x in nums]
            print(f"{uf}, {NOMES_CARGO.get(int(cargo), cargo)}: {len(nums)} candidatos na fila")
    return executar_fila(fila, cfg, ano, multi, cfg_path, saida, site_dir, refazer=refazer)


def executar_fila(fila, cfg, ano, multi, cfg_path, saida, site_dir, refazer=False):
    import time
    import traceback

    from eleicao import site
    perm = int(cfg.get("permutacoes_lote", 199))
    cidades = int(cfg.get("top_cidades_lote", 3))
    base = saida.resolve().parent / (saida.name + "_lote")
    vistos, feitos, falhas = set(), 0, []
    t0 = time.time()
    ctxs = {}
    for i, (uf, cargo, num, nome, dest) in enumerate(fila, 1):
        if (uf, cargo, num) in vistos:
            continue
        vistos.add((uf, cargo, num))
        if (site_dir / site.caminho_pagina(ano, uf, cargo, num)).exists() and not refazer:
            continue
        print(f"\n[{i}/{len(fila)}] {uf}, {NOMES_CARGO.get(cargo, cargo)}, candidato {num}  "
              f"({(time.time() - t0) / 60:.0f} min)", flush=True)
        try:
            c = ctxs.setdefault(uf, contexto_uf(cfg, cfg_path, uf, multi))
            run_analysis.main(c["montar_args"](cargo, num, nome=nome, destino=str(base / f"{uf}_{site.slug_cargo(cargo)}_{num}"),
                                                perm=None if dest else perm, cidades=None if dest else cidades))
            feitos += 1
        except Exception as e:  # noqa: BLE001
            falhas.append((uf, cargo, num, str(e).splitlines()[0] if str(e) else type(e).__name__))
            print(f"  FALHOU: {falhas[-1][3]}", flush=True)
            traceback.print_exc(limit=2)
    print(f"\nConcluído: {feitos} novos, {len(falhas)} falhas. Site em {site_dir}")
    for uf, c_, num, msg in falhas:
        print(f"  {uf}, {NOMES_CARGO.get(c_, c_)} nº {num}: {msg}")
    return 1 if falhas and len(fila) == 1 else 0


if __name__ == "__main__":
    sys.exit(main())
