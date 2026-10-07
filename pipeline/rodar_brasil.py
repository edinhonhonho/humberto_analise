"""Analisa os candidatos de partidos de esquerda de TODAS as UFs, em paralelo e podendo ser interrompido.

    python rodar_brasil.py --plano                 só conta quantos candidatos entram, por UF e cargo, e estima o tempo
    python rodar_brasil.py                         roda tudo (4 processos por padrão)
    python rodar_brasil.py --paralelas 6           mais processos (cada um usa ~1 a 2 GB nas UFs grandes)
    python rodar_brasil.py --so=SP,MG --cargos=6   só estas UFs / cargos
    python rodar_brasil.py --espectros esquerda,centro

Como funciona:
  1. Cria config_brasil.json (as 27 UFs, mesmos filtros do config.json) sem mexer no config.json.
  2. Gera as listas de nomes (candidatos_2026_<UF>_c<cargo>.csv) das UFs que ainda não têm, a partir do
     consulta_cand_2026.zip que está na pasta dados.
  3. Divide o trabalho em tarefas (UF x grupo de cargos) e as distribui entre processos independentes,
     das maiores para as menores. Cada tarefa é o próprio `rodar.py --lote --so=UF --cargos=...`.
  4. Quem já está no site é pulado; se uma tarefa cair (memória, queda de energia), ela é refeita uma vez e,
     se você interromper com Ctrl+C e rodar de novo, continua de onde parou.
  5. Ao fim, atualiza índices e totais do site (rodar.py --indice) e imprime o resumo.
Logs de cada tarefa em logs_brasil/.
"""
import argparse
import csv
import io
import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path

BASE = Path(__file__).parent.resolve()
UFS = "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split()
CARGO_SLUG = {3: "governador", 5: "senador", 6: "deputado-federal", 7: "deputado-estadual"}
SEG_POR_ANALISE = 15          # medido nos lotes de RS, RJ e PE (disco lento pesa mais que a CPU)

ap = argparse.ArgumentParser()
ap.add_argument("--config", default=str(BASE / "config.json"))
ap.add_argument("--plano", action="store_true")
ap.add_argument("--paralelas", type=int, default=max(2, min(4, (os.cpu_count() or 2))))
ap.add_argument("--so", default="")
ap.add_argument("--cargos", default="3,5,6,7")
ap.add_argument("--espectros", default="")
ap.add_argument("--refazer", action="store_true")
ap.add_argument("--sem-nomes", action="store_true")
a = ap.parse_args()

cfg0 = json.loads(Path(a.config).read_text(encoding="utf-8"))
ano = cfg0["ano"]
ufs = [u for u in (a.so.upper().replace(" ", "").split(",") if a.so else UFS) if u in UFS]
cargos = [int(c) for c in a.cargos.split(",") if c]
esp = [e for e in a.espectros.split(",") if e] or cfg0.get("espectros") or ["esquerda"]
pasta = Path(cfg0.get("pasta_dados", "dados"))
pasta = pasta if pasta.is_absolute() else (Path(a.config).resolve().parent / pasta)
site_dir = Path(cfg0.get("saida", "saida_{ano}").format(ano=ano, uf="")).resolve().parent / "site"
cfg_brasil = Path(a.config).resolve().with_name("config_brasil.json")
minimos = cfg0.get("votos_minimos") or {}


def escrever_config():
    c = dict(cfg0)
    c["ufs"] = UFS
    c["espectros"] = esp
    cfg_brasil.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")


def contagem_do_zip():
    """{(uf, cargo): n} candidatos do espectro pedido, pelo registro de candidaturas (limite superior:
    o corte de votos mínimos tira alguns depois)."""
    sys.path.insert(0, str(BASE))
    from eleicao.partidos import espectro_de
    zp = pasta / f"consulta_cand_{ano}.zip"
    if not zp.exists():
        return None
    n = {}
    with zipfile.ZipFile(zp) as z:
        for nome in z.namelist():
            up = nome.upper()
            if not up.endswith(".CSV") or "BRASIL" in up or "_BR." in up:
                continue
            uf = up.rsplit("_", 1)[-1][:-4]
            if uf not in UFS:
                continue
            with z.open(nome) as f:
                for r in csv.DictReader(io.TextIOWrapper(f, encoding="latin-1"), delimiter=";"):
                    try:
                        cg, num = int(r["CD_CARGO"]), int(r["NR_CANDIDATO"])
                    except (KeyError, ValueError):
                        continue
                    if cg in CARGO_SLUG and espectro_de(num) in esp:
                        n[(uf, cg)] = n.get((uf, cg), 0) + 1
    return n


def fmt_h(seg):
    return f"{seg / 3600:.1f} h" if seg >= 3600 else f"{seg / 60:.0f} min"


def plano():
    n = contagem_do_zip()
    if n is None:
        print(f"Sem {pasta / f'consulta_cand_{ano}.zip'}: não dá para estimar. Rode mesmo assim.")
        return None
    tot = {c: sum(v for (u, cg), v in n.items() if cg == c and u in ufs) for c in cargos}
    print(f"Candidatos do espectro {esp} (antes do corte de votos mínimos):")
    for c in cargos:
        print(f"  {CARGO_SLUG[c]:18s} {tot[c]:6d}")
    t = sum(tot.values())
    print(f"  {'total':18s} {t:6d}  ->  cerca de {fmt_h(t * SEG_POR_ANALISE)} em 1 processo, "
          f"{fmt_h(t * SEG_POR_ANALISE / a.paralelas)} com {a.paralelas}")
    mb = t * 0.45
    print(f"Espaço no site: aproximadamente {mb / 1000:.1f} GB (cada página tem uns 0,45 MB; ~25% disso comprimido).")
    return n


def faltam_nomes():
    return [u for u in ufs if any(not (pasta / f"candidatos_{ano}_{u}_c{c}.csv").exists() for c in (3, 5, 6, 7))]


def gerar_nomes():
    falta = faltam_nomes()
    if not falta:
        return
    zp = pasta / f"consulta_cand_{ano}.zip"
    if not zp.exists():
        print(f"AVISO: sem {zp}; as UFs {','.join(falta)} ficarão com candidatos sem nome (só o número). "
              f"Baixe o consulta_cand_{ano}.zip e rode de novo.")
        return
    print(f"Gerando listas de nomes de {len(falta)} UFs...", flush=True)
    subprocess.run([sys.executable, str(BASE / "baixar_nomes.py"), "--consulta", str(zp),
                    "--uf", ",".join(falta), "--pasta", str(pasta)], cwd=BASE, check=False)


def tamanho_uf(u):
    p = list(pasta.rglob(f"votacao_secao_{ano}_{u}*"))
    return max((x.stat().st_size for x in p), default=0)


def tarefas(n):
    """[(peso, uf, 'cargos')]. Governador+senador (rápidos) formam uma tarefa; federal e estadual, uma cada."""
    grupos = [g for g in ([c for c in (3, 5) if c in cargos], [6] if 6 in cargos else [], [7] if 7 in cargos else []) if g]
    t = []
    for u in ufs:
        if not tamanho_uf(u):
            print(f"AVISO: {u} sem votacao_secao_{ano}_{u}; ficou de fora.")
            continue
        for g in grupos:
            q = sum((n or {}).get((u, c), 0) for c in g) if n else tamanho_uf(u) / 1e6
            t.append((q, u, ",".join(map(str, g))))
    # as grandes primeiro (menos tempo de cauda); governador/senador de todas as UFs antes por serem rápidos
    t.sort(key=lambda x: (x[2] != "3,5", -x[0]))
    return t


def paginas():
    d = site_dir / "data" / "c" / str(ano)
    return sum(1 for _ in d.glob("*/*/*.js")) if d.exists() else 0


def main():
    n = plano()
    if a.plano:
        return 0
    escrever_config()
    if not a.sem_nomes:
        gerar_nomes()
    fila = tarefas(n)
    total_est = sum(q for q, _, _ in fila) if n else None
    logs = BASE / "logs_brasil"
    logs.mkdir(exist_ok=True)
    env = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1",
               NUMEXPR_NUM_THREADS="1", PYTHONUNBUFFERED="1")
    ativos, feitas, tentativas = [], [], {}
    inicio, ult = time.time(), 0
    pag0 = paginas()
    pend = list(fila)
    print(f"\n{len(pend)} tarefas, {a.paralelas} em paralelo. Pode interromper (Ctrl+C) e rodar de novo.\n", flush=True)
    try:
        while pend or ativos:
            while pend and len(ativos) < a.paralelas:
                q, u, cg = pend.pop(0)
                cmd = [sys.executable, str(BASE / "rodar.py"), str(cfg_brasil), "--lote", f"--so={u}", f"--cargos={cg}"]
                if a.refazer:
                    cmd.append("--refazer")
                lf = open(logs / f"{u}_{cg.replace(',', '-')}.log", "a", encoding="utf-8")
                p = subprocess.Popen(cmd, cwd=BASE, env=env, stdout=lf, stderr=subprocess.STDOUT)
                ativos.append((p, u, cg, q, lf))
                print(f"  inicia {u} cargos {cg} (~{int(q)} candidatos)", flush=True)
            time.sleep(2)
            for t in list(ativos):
                p, u, cg, q, lf = t
                if p.poll() is None:
                    continue
                lf.close()
                ativos.remove(t)
                chave = (u, cg)
                if p.returncode != 0 and tentativas.get(chave, 0) < 1:
                    tentativas[chave] = 1
                    print(f"  {u} cargos {cg} caiu (código {p.returncode}); vai tentar de novo.", flush=True)
                    pend.insert(0, (q, u, cg))
                else:
                    feitas.append((u, cg, p.returncode))
                    print(f"  fim    {u} cargos {cg} (código {p.returncode})", flush=True)
            if time.time() - ult > 60:
                ult = time.time()
                novas = paginas() - pag0
                dt = max(1, ult - inicio)
                ritmo = novas / dt * 60
                txt = f"  [{fmt_h(dt)}] {novas} análises novas, {ritmo:.0f}/min"
                if total_est and ritmo > 0:
                    resta = max(0, total_est - novas)
                    txt += f", faltam ~{int(resta)} (ao ritmo atual, {fmt_h(resta / ritmo * 60)})"
                print(txt, flush=True)
    except KeyboardInterrupt:
        print("\nInterrompido. Encerrando processos; rode de novo para continuar.")
        for p, *_ in ativos:
            p.terminate()
        return 130
    print("\nAtualizando índices do site...", flush=True)
    subprocess.run([sys.executable, str(BASE / "rodar.py"), str(cfg_brasil), "--indice"], cwd=BASE, check=False, env=env)
    ruins = [f for f in feitas if f[2] != 0]
    print(f"\nPronto em {fmt_h(time.time() - inicio)}. Páginas no site: {paginas()} ({paginas() - pag0} novas).")
    if ruins:
        print("Tarefas com falha (veja logs_brasil/):", ", ".join(f"{u}[{c}]" for u, c, _ in ruins))
    print("Próximo passo: python publicar.py")
    return 1 if ruins else 0


if __name__ == "__main__":
    sys.exit(main())
