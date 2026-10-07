"""Gera arquivos SINTÉTICOS no layout do TSE/IBGE, só para testar o código.
Os números não representam nenhuma eleição real."""
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

rng = np.random.default_rng(7)
OUT = Path(__file__).parent / "synth"
OUT.mkdir(exist_ok=True)

NX = NY = 12
X0, X1, Y0, Y1 = -57.5, -49.5, -33.5, -27.0
dx, dy = (X1 - X0) / NX, (Y1 - Y0) / NY
N = NX * NY

nomes_tse, nomes_ibge = [], []
for i in range(N):
    nomes_tse.append(f"CIDADE {i + 1:03d}")
    nomes_ibge.append(f"Cidade {i + 1:03d}")
nomes_tse[5], nomes_ibge[5] = "SANT'ANA DO TESTE", "Santana do Teste"
nomes_tse[17], nomes_ibge[17] = "VESPASIANO CORREA", "Vespasiano Corrêa"
nomes_tse[30], nomes_ibge[30] = "ENTRE-IJUIS", "Entre-Ijuís"

# --- malha IBGE
polys = []
for j in range(NY):
    for i in range(NX):
        polys.append(box(X0 + i * dx, Y0 + j * dy, X0 + (i + 1) * dx, Y0 + (j + 1) * dy))
malha = gpd.GeoDataFrame({"CD_MUN": [f"43{k:05d}" for k in range(N)], "NM_MUN": nomes_ibge,
                          "SIGLA_UF": "RS"}, geometry=polys, crs=4674)
extra = gpd.GeoDataFrame({"CD_MUN": ["4200001"], "NM_MUN": ["Fora da UF"], "SIGLA_UF": ["SC"]},
                         geometry=[box(-50, -28, -49.9, -27.9)], crs=4674)
pd.concat([malha, extra]).to_file(OUT / "malha_RS.gpkg", driver="GPKG")

# --- candidatos
partidos = [13, 45, 55, 65, 12, 15, 22]
cands = {}  # numero -> nome
for p in partidos:
    for k in range(1, 8 if p != 65 else 9):
        cands[p * 1000 + k] = f"CANDIDATO {p}{k:03d}"
cands[65065] = "HUMBERTO TESTE"
nrs = np.array(sorted(cands))
legendas = np.array(partidos)

cod_tse = 88000 + np.arange(N)
big = {40, 41, 66, 90, 120}  # "capitais" sintéticas
linhas_v, linhas_e = [], []
cx_hot = {}

for i in range(N):
    gi, gj = i % NX, i // NX
    cx, cy = X0 + (gi + 0.5) * dx, Y0 + (gj + 0.5) * dy
    n_loc = int(rng.integers(70, 110)) if i in big else int(rng.integers(2, 14))
    base = 0.004 + 0.05 * (1 - gi / NX) ** 2 + rng.normal(0, 0.004)  # mais forte a oeste
    base = max(base, 0.0)
    for l in range(n_loc):
        if i in big:
            lx, ly = cx + rng.normal(0, dx * 0.16), cy + rng.normal(0, dy * 0.16)
            hot = np.exp(-(((lx - (cx + dx * 0.12)) / (dx * 0.1)) ** 2 +
                           ((ly - (cy - dy * 0.05)) / (dy * 0.1)) ** 2))
            base_l = base * 0.4 + 0.07 * hot
        else:
            lx, ly = cx + rng.uniform(-dx * .3, dx * .3), cy + rng.uniform(-dy * .3, dy * .3)
            base_l = base
        base_l = max(base_l + rng.normal(0, 0.003), 0)
        bairro = f"BAIRRO {'ABCD'[int(lx > cx)]}{'12'[int(ly > cy)]}" if i in big else "CENTRO"
        zona = 1 + (l % 3)
        local = 1000 + l
        invalido = rng.random() < 0.05
        lat = -1 if invalido else ly
        lon = -1 if invalido else lx
        for s in range(int(rng.integers(2, 5))):
            secao = l * 10 + s + 1
            apt = int(rng.integers(180, 330))
            comp = int(apt * rng.uniform(0.72, 0.9))
            n_nom = int(comp * 0.93)
            n_leg = int(comp * 0.02)
            n_br = int(comp * 0.02)
            n_nu = comp - n_nom - n_leg - n_br
            outros = nrs[nrs != 65065]
            w = rng.dirichlet(np.ones(len(outros)) * 0.4)
            p_ours = min(base_l, 0.5)
            probs = np.append(w * (1 - p_ours), p_ours)
            votos = rng.multinomial(n_nom, probs)
            leg = rng.multinomial(n_leg, rng.dirichlet(np.ones(len(legendas))))
            ids = list(outros) + [65065]
            reg = [(nr, v) for nr, v in zip(ids, votos) if v > 0]
            reg += [(int(p), int(v)) for p, v in zip(legendas, leg) if v > 0]
            reg += [(95, n_br), (96, n_nu)]
            for nr, v in reg:
                nm = cands.get(nr, "Voto de legenda" if nr < 95 else
                               ("Branco" if nr == 95 else "Nulo"))
                linhas_v.append(["13/10/2026", "10:00:00", 2022, 2, "Eleição Ordinária", 1, 544,
                                 "Eleições Gerais 2022", "02/10/2022", "E", "RS", "RS",
                                 "RIO GRANDE DO SUL", int(cod_tse[i]), nomes_tse[i], zona, secao,
                                 7, "Deputado Estadual", nr, nm, v, local,
                                 -1, f"ESCOLA {l:03d} {nomes_tse[i][:8]}", f"RUA {l}, {i}"])
            linhas_v.append(["13/10/2026", "10:00:00", 2022, 2, "Eleição Ordinária", 1, 544,
                             "Eleições Gerais 2022", "02/10/2022", "E", "RS", "RS",
                             "RIO GRANDE DO SUL", int(cod_tse[i]), nomes_tse[i], zona, secao,
                             6, "Deputado Federal", 99999, "OUTRO CARGO", 5, local, -1,
                             "X", "Y"])
            fmt = lambda v: f"{v:.6f}".replace(".", ",")
            linhas_e.append(["13/10/2026", "10:00:00", 2022, "RS", int(cod_tse[i]), nomes_tse[i],
                             zona, secao, 0, "Principal", "", local,
                             f"ESCOLA {l:03d} {nomes_tse[i][:8]}", 1, "Escola", f"RUA {l}, {i}",
                             bairro, "90000000", "", fmt(lat), fmt(lon), 1, "Ativo",
                             apt, apt - 3])

cab_v = ["DT_GERACAO", "HH_GERACAO", "ANO_ELEICAO", "CD_TIPO_ELEICAO", "NM_TIPO_ELEICAO",
         "NR_TURNO", "CD_ELEICAO", "DS_ELEICAO", "DT_ELEICAO", "TP_ABRANGENCIA", "SG_UF", "SG_UE",
         "NM_UE", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO", "CD_CARGO", "DS_CARGO",
         "NR_VOTAVEL", "NM_VOTAVEL", "QT_VOTOS", "NR_LOCAL_VOTACAO", "SQ_CANDIDATO",
         "NM_LOCAL_VOTACAO", "DS_LOCAL_VOTACAO_ENDERECO"]
cab_e = ["DT_GERACAO", "HH_GERACAO", "ANO_ELEICAO", "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO",
         "NR_ZONA", "NR_SECAO", "CD_TIPO_SECAO_AGREGADA", "DS_TIPO_SECAO_AGREGADA",
         "NR_SECAO_PRINCIPAL", "NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO", "CD_TIPO_LOCAL",
         "DS_TIPO_LOCAL", "DS_ENDERECO", "NM_BAIRRO", "NR_CEP", "NR_TELEFONE_LOCAL",
         "NR_LATITUDE", "NR_LONGITUDE", "CD_SITUACAO_LOCAL_VOTACAO", "DS_SITUACAO_LOCAL_VOTACAO",
         "QT_ELEITOR_SECAO", "QT_ELEITOR_ELEITORADO_APTO"]

dv = pd.DataFrame(linhas_v, columns=cab_v)
de = pd.DataFrame(linhas_e, columns=cab_e)
# linhas de outra UF, para testar o filtro
outra = de.head(20).copy()
outra["SG_UF"] = "SC"
de = pd.concat([de, outra], ignore_index=True)

dv.to_csv(OUT / "votacao_secao_2022_RS.csv", sep=";", index=False, encoding="latin-1",
          quoting=1)
de.to_csv(OUT / "eleitorado_local_votacao_2022.csv", sep=";", index=False, encoding="latin-1",
          quoting=1)
print(f"votação: {len(dv):,} linhas; locais: {len(de):,} linhas; municípios: {N}")
