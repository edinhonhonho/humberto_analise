"""Leitura dos arquivos abertos do TSE e da malha municipal do IBGE.

Arquivos esperados (todos aceitos como .zip ou .csv soltos):

1. votacao_secao_ANO_UF.csv    -> votos por seção eleitoral (portal de dados abertos, "Resultados")
2. eleitorado_local_votacao_ANO.csv -> eleitorado por seção/local de votação, com endereço,
   bairro e coordenadas (portal de dados abertos, "Eleitorado")
3. Malha municipal do IBGE da UF (shapefile, GeoPackage ou GeoJSON, .zip aceito)

Os nomes de colunas são normalizados para maiúsculas. Quando o TSE muda um nome de coluna
entre eleições, a detecção abaixo avisa qual coluna foi escolhida (veja o log).
"""
from __future__ import annotations

import codecs
import difflib
import re
import unicodedata
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

UF_IBGE = {
    "RO": 11, "AC": 12, "AM": 13, "RR": 14, "PA": 15, "AP": 16, "TO": 17, "MA": 21,
    "PI": 22, "CE": 23, "RN": 24, "PB": 25, "PE": 26, "AL": 27, "SE": 28, "BA": 29,
    "MG": 31, "ES": 32, "RJ": 33, "SP": 35, "PR": 41, "SC": 42, "RS": 43, "MS": 50,
    "MT": 51, "GO": 52, "DF": 53,
}

# Códigos de cargo do TSE para eleições proporcionais
CARGOS_PROPORCIONAIS = {6: "Deputado Federal", 7: "Deputado Estadual", 8: "Deputado Distrital",
                        13: "Vereador"}
COD_BRANCO, COD_NULO = 95, 96


def norm_nome(s) -> str:
    """Chave de comparação de nomes: sem acento, maiúscula, só letras e números."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]", "", s)


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.strip().str.replace(",", ".", regex=False),
                         errors="coerce")


# --------------------------------------------------------------------------- CSV genérico
def _open_csv(path, member_regex: str | None = None):
    path = Path(path)
    if path.suffix.lower() == ".zip":
        zf = zipfile.ZipFile(path)
        names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if member_regex:
            sel = [n for n in names if re.search(member_regex, n, re.I)]
            names = sel or names
        if not names:
            raise FileNotFoundError(f"Nenhum CSV dentro de {path.name}")
        names.sort(key=lambda n: zf.getinfo(n).file_size, reverse=True)
        return zf.open(names[0]), names[0]
    return open(path, "rb"), path.name


def _sniff_encoding(head: bytes) -> str:
    dec = codecs.getincrementaldecoder("utf-8")()
    try:
        dec.decode(head, final=False)  # tolera caractere cortado no fim do bloco
        return "utf-8"
    except UnicodeDecodeError:
        return "latin-1"


def iter_csv(path, member_regex: str | None = None, usecols: set[str] | None = None,
             chunksize: int = 500_000, log=print):
    """Itera o CSV do TSE em blocos. Tudo como texto; converte depois."""
    fh, name = _open_csv(path, member_regex)
    head = fh.read(65536)
    fh.seek(0)
    enc = _sniff_encoding(head)
    sep = ";" if head.count(b";") >= head.count(b",") else ","
    log(f"  lendo {name} (encoding={enc}, sep='{sep}')")
    if callable(usecols):
        sel = lambda c: bool(usecols(c.strip().upper()))  # noqa: E731
    elif usecols:
        sel = lambda c: c.strip().upper() in usecols  # noqa: E731
    else:
        sel = None
    for ch in pd.read_csv(fh, sep=sep, encoding=enc, dtype=str, chunksize=chunksize,
                          usecols=sel, low_memory=False):
        ch.columns = [c.strip().strip('"').upper() for c in ch.columns]
        yield ch


# --------------------------------------------------------------------------- votação por seção
_VOTOS_COLS = {"SG_UF", "NR_TURNO", "CD_CARGO", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA",
               "NR_SECAO", "NR_VOTAVEL", "NM_VOTAVEL", "QT_VOTOS", "NR_LOCAL_VOTACAO",
               "NM_LOCAL_VOTACAO", "DS_LOCAL_VOTACAO_ENDERECO", "QT_APTOS"}
_VOTOS_REQ = ["NR_TURNO", "CD_CARGO", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO",
              "NR_VOTAVEL", "QT_VOTOS"]


_CHAVES = ["CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO", "NR_LOCAL_VOTACAO",
           "NM_LOCAL_VOTACAO", "DS_LOCAL_VOTACAO_ENDERECO"]


def _raw_cargo(path, cargo: int, turno: int, uf: str | None, log=print) -> pd.DataFrame:
    """Votos do cargo agregados por seção e votável (todos os candidatos). É a parte lenta (lê o CSV
    inteiro), por isso o resultado fica em cache ao lado do arquivo e serve a qualquer candidato."""
    import pickle
    path = Path(path)
    st = path.stat()
    cache = path.parent / ".cache" / f"{path.stem}_c{cargo}_t{turno}_{uf or 'x'}_{st.st_size}_{int(st.st_mtime)}.pkl"
    if cache.exists():
        try:
            raw = pickle.loads(cache.read_bytes())
            log(f"  votação do cargo {cargo} lida do cache ({len(raw):,} linhas)")
            return raw
        except Exception:  # noqa: BLE001
            pass
    parts, linhas = [], 0
    for ch in iter_csv(path, r"votacao_secao", _VOTOS_COLS, log=log):
        faltam = [c for c in _VOTOS_REQ if c not in ch.columns]
        if faltam:
            raise KeyError(f"Colunas ausentes no arquivo de votação: {faltam}. "
                           f"Colunas lidas: {list(ch.columns)}")
        if uf and "SG_UF" in ch.columns:
            ch = ch[ch["SG_UF"].str.strip() == uf]
        ch = ch[(_num(ch["NR_TURNO"]) == turno) & (_num(ch["CD_CARGO"]) == cargo)]
        if ch.empty:
            continue
        ch = ch.copy()
        linhas += len(ch)
        ch["QT_VOTOS"] = _num(ch["QT_VOTOS"]).fillna(0).astype("int64")
        ch["NR_VOTAVEL"] = _num(ch["NR_VOTAVEL"]).fillna(-1).astype("int64")
        for c in ("CD_MUNICIPIO", "NR_ZONA", "NR_SECAO"):
            ch[c] = _num(ch[c]).astype("int64")
        for c in ("NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO", "DS_LOCAL_VOTACAO_ENDERECO"):
            if c not in ch.columns:
                ch[c] = ""
            ch[c] = ch[c].fillna("")
        if "NM_VOTAVEL" not in ch.columns:
            ch["NM_VOTAVEL"] = ""
        ch["NM_VOTAVEL"] = ch["NM_VOTAVEL"].fillna("").astype(str)
        aggs = {"QT_VOTOS": "sum"}
        if "QT_APTOS" in ch.columns:  # presente quando o arquivo vem dos boletins de urna (baixar_bu.py)
            ch["QT_APTOS"] = _num(ch["QT_APTOS"]).fillna(0)
            aggs["QT_APTOS"] = "max"
        parts.append(ch.groupby(_CHAVES + ["NR_VOTAVEL", "NM_VOTAVEL"], as_index=False).agg(aggs))
    if not parts:
        raise ValueError(f"Nenhuma linha para cargo={cargo}, turno={turno}, uf={uf}. "
                         "Confira o arquivo e o código do cargo (7 = Deputado Estadual).")
    aggs = {"QT_VOTOS": "sum"}
    if "QT_APTOS" in parts[0].columns:
        aggs["QT_APTOS"] = "max"
    raw = pd.concat(parts, ignore_index=True).groupby(_CHAVES + ["NR_VOTAVEL", "NM_VOTAVEL"],
                                                       as_index=False).agg(aggs)
    raw.attrs["linhas"] = linhas
    try:
        cache.parent.mkdir(exist_ok=True)
        cache.write_bytes(pickle.dumps(raw, protocol=4))
    except OSError:
        pass
    return raw


def load_votacao_secao(path, numero: int, cargo: int = 7, turno: int = 1, uf: str | None = None,
                       log=print, raw: pd.DataFrame | None = None):
    """Lê votacao_secao e devolve (secoes, candidatos, info).

    secoes: uma linha por seção, com votos do candidato, do partido, válidos, brancos, nulos.
    candidatos: votos de todos os candidatos do cargo por município (para contexto/ranking).
    Serve a qualquer cargo: o número do partido sai do início do número do candidato (partidos.py).
    `raw` permite reaproveitar a leitura (modo em lote)."""
    from .partidos import partido_de
    numero = int(numero)
    partido = partido_de(numero)
    if raw is None:
        raw = _raw_cargo(path, cargo, turno, uf, log=log)
    nr = raw["NR_VOTAVEL"].to_numpy()
    qt = raw["QT_VOTOS"].to_numpy()
    branco, nulo = nr == COD_BRANCO, nr == COD_NULO
    proporcional = cargo in CARGOS_PROPORCIONAIS
    legenda = (nr <= 99) if proporcional else np.zeros(len(nr), bool)  # voto de legenda tem 2 dígitos
    valido = ~(branco | nulo)
    party = partido_de(np.maximum(nr, 0))
    v = raw[_CHAVES + (["QT_APTOS"] if "QT_APTOS" in raw.columns else [])].copy()
    v["v_cand"] = np.where(nr == numero, qt, 0)
    v["v_partido"] = np.where(valido & (party == partido), qt, 0)
    v["v_validos"] = np.where(valido, qt, 0)
    v["v_brancos"] = np.where(branco, qt, 0)
    v["v_nulos"] = np.where(nulo, qt, 0)
    v["v_total"] = qt
    aggs_f = {c: "sum" for c in ["v_cand", "v_partido", "v_validos", "v_brancos", "v_nulos", "v_total"]}
    if "QT_APTOS" in v.columns:
        aggs_f["QT_APTOS"] = "max"
    secoes = v.groupby(_CHAVES, as_index=False).agg(aggs_f)

    ehc = valido & ~legenda
    cand = (raw.loc[ehc, ["CD_MUNICIPIO", "NR_VOTAVEL", "NM_VOTAVEL", "QT_VOTOS"]]
            .groupby(["CD_MUNICIPIO", "NR_VOTAVEL", "NM_VOTAVEL"], as_index=False)["QT_VOTOS"].sum())
    vazio = cand["NM_VOTAVEL"].isna() | (cand["NM_VOTAVEL"].astype(str).str.strip() == "")
    cand.loc[vazio, "NM_VOTAVEL"] = cand.loc[vazio, "NR_VOTAVEL"].astype(str)  # boletins não trazem o nome

    meu = cand[cand["NR_VOTAVEL"] == numero]
    if meu.empty:
        colegas = (cand[partido_de(cand["NR_VOTAVEL"]) == partido].groupby(["NR_VOTAVEL", "NM_VOTAVEL"])
                   ["QT_VOTOS"].sum().sort_values(ascending=False).head(10))
        raise ValueError(f"Candidato {numero} sem votos no arquivo. Candidatos do partido "
                         f"{partido} com mais votos:\n{colegas}")
    nome = meu["NM_VOTAVEL"].mode().iat[0]
    linhas = int(raw.attrs.get("linhas", len(raw)))
    info = {"numero": numero, "nome": nome, "partido_num": partido, "cargo": cargo,
            "turno": turno, "uf": uf, "linhas_lidas": linhas,
            "votos_total": int(meu["QT_VOTOS"].sum())}
    log(f"  candidato {numero} = {nome}; {info['votos_total']:,} votos; "
        f"{len(secoes):,} seções; {linhas:,} linhas do cargo")
    return secoes, cand, info


def mais_votados(raw: pd.DataFrame, cargo: int, n: int) -> list[int]:
    """Números dos n candidatos mais votados do cargo (sem branco, nulo e legenda)."""
    nr = raw["NR_VOTAVEL"]
    ok = ~nr.isin([COD_BRANCO, COD_NULO])
    if cargo in CARGOS_PROPORCIONAIS:
        ok &= nr > 99
    tot = raw[ok].groupby("NR_VOTAVEL")["QT_VOTOS"].sum().sort_values(ascending=False)
    return [int(x) for x in tot.head(n).index]


# --------------------------------------------------------------------------- eleitorado/locais
_ELEITORES_PRIORIDADE = ["QT_ELEITOR_ELEITORADO_APTO", "QT_ELEITOR_SECAO", "QT_ELEITORES_APTOS",
                         "QT_ELEITOR", "QT_ELEITORES"]


def load_perfil(path, uf: str, log=print) -> pd.DataFrame:
    """Perfil do eleitorado por seção (várias linhas por seção) -> eleitores aptos por seção.

    Não traz coordenadas nem bairro: serve só para a base de eleitores (taxas por eleitor)."""
    usecols = {"SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", "QT_ELEITORES_PERFIL",
               "QT_ELEITORES", "QT_ELEITOR"}
    partes = []
    for ch in iter_csv(path, r"perfil", usecols, log=log):
        if "SG_UF" in ch.columns:
            ch = ch[ch["SG_UF"].str.strip() == uf]
        if ch.empty:
            continue
        c_q = next((c for c in ("QT_ELEITORES_PERFIL", "QT_ELEITORES", "QT_ELEITOR")
                    if c in ch.columns), None)
        if c_q is None:
            raise KeyError(f"Sem coluna de quantidade de eleitores no perfil: {list(ch.columns)}")
        d = pd.DataFrame({"CD_MUNICIPIO": _num(ch["CD_MUNICIPIO"]).astype("int64"),
                          "NR_ZONA": _num(ch["NR_ZONA"]).astype("int64"),
                          "NR_SECAO": _num(ch["NR_SECAO"]).astype("int64"),
                          "eleitores": _num(ch[c_q]).fillna(0)})
        partes.append(d.groupby(["CD_MUNICIPIO", "NR_ZONA", "NR_SECAO"], as_index=False).sum())
    if not partes:
        raise ValueError(f"Nenhuma linha de {uf} no perfil do eleitorado.")
    out = pd.concat(partes, ignore_index=True).groupby(
        ["CD_MUNICIPIO", "NR_ZONA", "NR_SECAO"], as_index=False)["eleitores"].sum()
    log(f"  perfil: {len(out):,} seções, {int(out['eleitores'].sum()):,} eleitores aptos")
    return out


def load_locais(path, uf: str, col_eleitores: str | None = None, log=print):
    """Eleitorado por local de votação. Devolve (tabela, nivel), com nivel 'secao' ou 'local'
    conforme o arquivo tenha ou não a coluna NR_SECAO. Traz coordenadas e bairro, se houver."""
    partes = []
    manter = re.compile(r"^(SG_UF|CD_MUNICIPIO|NR_ZONA|NR_SECAO|NR_LOCAL_VOTACAO|NM_LOCAL_VOTACAO|"
                        r"DS_ENDERECO|DS_LOCAL_VOTACAO_ENDERECO|NM_BAIRRO|NR_LATITUDE|NR_LONGITUDE|"
                        r"LATITUDE|LONGITUDE|QT_ELEITOR.*|NM_MUNICIPIO)$")
    for ch in iter_csv(path, r"eleitorado|local", lambda c: manter.match(c), log=log):
        if "SG_UF" in ch.columns:
            ch = ch[ch["SG_UF"].str.strip() == uf]
        if len(ch):
            partes.append(ch)
    if not partes:
        raise ValueError(f"Nenhuma linha de {uf} no arquivo de locais de votação.")
    df = pd.concat(partes, ignore_index=True)
    cols = list(df.columns)

    def achar(candidatos=(), regex=None):
        for c in candidatos:
            if c in cols:
                return c
        if regex:
            for c in cols:
                if re.search(regex, c):
                    return c
        return None

    nivel = "secao" if "NR_SECAO" in cols else "local"
    c_el = col_eleitores or achar(_ELEITORES_PRIORIDADE, r"^QT_ELEITOR")
    c_lat = achar(["NR_LATITUDE", "LATITUDE"], r"LAT")
    c_lon = achar(["NR_LONGITUDE", "LONGITUDE"], r"LON")
    c_bai = achar(["NM_BAIRRO"], r"BAIRRO")
    c_end = achar(["DS_ENDERECO", "DS_LOCAL_VOTACAO_ENDERECO"], r"ENDERECO")
    c_nom = achar(["NM_LOCAL_VOTACAO"], r"NM_LOCAL")
    c_nlv = achar(["NR_LOCAL_VOTACAO"], r"NR_LOCAL")
    log(f"  nível do arquivo: {nivel}; colunas escolhidas -> eleitores={c_el} lat={c_lat} "
        f"lon={c_lon} bairro={c_bai} local={c_nom} nr_local={c_nlv}")
    if nivel == "local" and c_nlv is None:
        raise KeyError("Arquivo de locais sem NR_SECAO nem NR_LOCAL_VOTACAO; não há como casar "
                       f"com a votação. Colunas: {cols}")
    if c_lat is None or c_lon is None:
        log("  AVISO: o arquivo não tem latitude/longitude; mapas por hexágono ficarão de fora.")

    out = pd.DataFrame({
        "CD_MUNICIPIO": _num(df["CD_MUNICIPIO"]).astype("int64"),
        "NR_ZONA": _num(df["NR_ZONA"]).astype("int64"),
        "eleitores": _num(df[c_el]) if c_el else np.nan,
        "lat": _num(df[c_lat]) if c_lat else np.nan,
        "lon": _num(df[c_lon]) if c_lon else np.nan,
        "e_bairro": df[c_bai].fillna("").str.strip() if c_bai else "",
        "e_endereco": df[c_end].fillna("").str.strip() if c_end else "",
        "e_local_nome": df[c_nom].fillna("").str.strip() if c_nom else "",
    })
    if nivel == "secao":
        out["NR_SECAO"] = _num(df["NR_SECAO"]).astype("int64")
        return out.drop_duplicates(["CD_MUNICIPIO", "NR_ZONA", "NR_SECAO"]), nivel
    out["_loc"] = _num(df[c_nlv]).astype("Int64")
    return out.drop_duplicates(["CD_MUNICIPIO", "NR_ZONA", "_loc"]), nivel


def juntar_secoes_locais(secoes: pd.DataFrame, perfil: pd.DataFrame | None = None,
                         locais: pd.DataFrame | None = None, nivel: str = "secao",
                         log=print) -> pd.DataFrame:
    """Une votos por seção + eleitores (perfil) + coordenadas/bairro (locais)."""
    m = secoes.copy()
    m["eleitores"] = np.nan
    if perfil is not None:
        m = m.drop(columns="eleitores").merge(perfil, on=["CD_MUNICIPIO", "NR_ZONA", "NR_SECAO"],
                                              how="left")
    for c, v in (("lat", np.nan), ("lon", np.nan), ("e_bairro", ""), ("e_endereco", ""),
                 ("e_local_nome", "")):
        m[c] = v
    if locais is not None:
        if nivel == "secao":
            r = locais.rename(columns={"eleitores": "_el"})
            m = m.drop(columns=["lat", "lon", "e_bairro", "e_endereco", "e_local_nome"]).merge(
                r, on=["CD_MUNICIPIO", "NR_ZONA", "NR_SECAO"], how="left")
            m["eleitores"] = m["eleitores"].fillna(m["_el"])
            m = m.drop(columns="_el")
        else:
            m["_loc"] = _num(m["NR_LOCAL_VOTACAO"]).astype("Int64")
            r = locais.drop(columns="eleitores")
            m = m.drop(columns=["lat", "lon", "e_bairro", "e_endereco", "e_local_nome"]).merge(
                r, on=["CD_MUNICIPIO", "NR_ZONA", "_loc"], how="left")
            m = m.drop(columns="_loc")
    if "QT_APTOS" in m.columns:  # último recurso: aptos informados no próprio boletim de urna
        m["eleitores"] = m["eleitores"].fillna(m["QT_APTOS"].where(m["QT_APTOS"] > 0))
    for c in ("e_bairro", "e_endereco", "e_local_nome"):
        m[c] = m[c].fillna("")
    log(f"  seções com eleitores: {m['eleitores'].notna().mean():.1%}; "
        f"com coordenada: {m['lat'].notna().mean():.1%}")
    m["local_nome"] = m["NM_LOCAL_VOTACAO"].where(m["NM_LOCAL_VOTACAO"] != "", m["e_local_nome"])
    m["endereco"] = m["DS_LOCAL_VOTACAO_ENDERECO"].where(m["DS_LOCAL_VOTACAO_ENDERECO"] != "",
                                                         m["e_endereco"])
    sem = m["local_nome"].astype(str).str.strip() == ""
    m.loc[sem, "local_nome"] = "Local " + m.loc[sem, "NR_LOCAL_VOTACAO"].astype(str)
    m["bairro"] = m["e_bairro"].replace("", "(sem bairro)")
    return m


def filtrar_coordenadas(m: pd.DataFrame, bounds, log=print) -> pd.DataFrame:
    """Marca seções com coordenada utilizável (dentro do retângulo da UF, com folga)."""
    minx, miny, maxx, maxy = bounds
    pad = 0.5
    ok = (m["lat"].between(miny - pad, maxy + pad) & m["lon"].between(minx - pad, maxx + pad)
          & ~((m["lat"].abs() < 1e-6) & (m["lon"].abs() < 1e-6)))
    m = m.copy()
    m.loc[~ok, ["lat", "lon"]] = np.nan
    log(f"  seções com coordenada válida: {ok.mean():.1%}")
    return m


# --------------------------------------------------------------------------- malha IBGE
def load_malha(path, uf: str, mun_tse: pd.DataFrame, log=print) -> gpd.GeoDataFrame:
    """Lê a malha municipal e cria a ponte código TSE <-> IBGE por nome (dentro da UF)."""
    gdf = gpd.read_file(path)
    geom = gdf.geometry.name
    gdf.columns = [c if c == geom else c.upper() for c in gdf.columns]
    c_cod = next((c for c in ["CD_MUN", "CD_GEOCODM", "CODE_MUNI", "GEOCODIGO"] if c in gdf), None)
    c_nom = next((c for c in ["NM_MUN", "NM_MUNICIP", "NAME_MUNI", "NOME", "NM_MUNICI"]
                  if c in gdf), None)
    if not c_cod or not c_nom:
        raise KeyError(f"Não achei colunas de código/nome na malha: {list(gdf.columns)}")
    gdf = gdf[gdf[c_cod].astype(str).str.startswith(str(UF_IBGE[uf]))].copy()
    gdf = gdf.rename(columns={c_cod: "cd_ibge", c_nom: "nm_ibge"})
    gdf = gdf.to_crs(4326)

    tse = mun_tse.drop_duplicates("CD_MUNICIPIO").copy()
    tse["chave"] = tse["NM_MUNICIPIO"].map(norm_nome)
    gdf["chave"] = gdf["nm_ibge"].map(norm_nome)
    mapa = dict(zip(tse["chave"], tse["CD_MUNICIPIO"]))
    gdf["CD_MUNICIPIO"] = gdf["chave"].map(mapa)

    # segunda chance: nomes quase iguais (apóstrofos, abreviações)
    sem = gdf["CD_MUNICIPIO"].isna()
    livres = [k for k in mapa if k not in set(gdf.loc[~sem, "chave"])]
    for i in gdf.index[sem]:
        par = difflib.get_close_matches(gdf.at[i, "chave"], livres, n=1, cutoff=0.84)
        if par:
            gdf.at[i, "CD_MUNICIPIO"] = mapa[par[0]]
            livres.remove(par[0])
            log(f"  nome aproximado: IBGE '{gdf.at[i, 'nm_ibge']}' ~ TSE chave '{par[0]}'")
    n_sem = gdf["CD_MUNICIPIO"].isna().sum()
    sem_malha = set(tse["CD_MUNICIPIO"]) - set(gdf["CD_MUNICIPIO"].dropna().astype(int))
    log(f"  malha: {len(gdf)} municípios; sem correspondência no TSE: {n_sem}; "
        f"municípios do TSE sem polígono: {len(sem_malha)}")
    gdf = gdf[gdf["CD_MUNICIPIO"].notna()].copy()
    gdf["CD_MUNICIPIO"] = gdf["CD_MUNICIPIO"].astype("int64")
    return gdf[["CD_MUNICIPIO", "cd_ibge", "nm_ibge", geom]].reset_index(drop=True)


# --------------------------------------------------------------------------- prestação de contas
def load_despesas(path, numero: int, log=print) -> pd.DataFrame | None:
    """Despesas do candidato (prestação de contas). Opcional."""
    partes = []
    for ch in iter_csv(path, r"despesas", None, log=log):
        c_nr = next((c for c in ch.columns if c in ("NR_CANDIDATO", "NR_CAND")), None)
        if c_nr is None:
            log("  AVISO: coluna NR_CANDIDATO não encontrada nas despesas.")
            return None
        ch = ch[_num(ch[c_nr]) == int(numero)]
        if len(ch):
            partes.append(ch)
    if not partes:
        log("  AVISO: nenhuma despesa encontrada para o candidato.")
        return None
    df = pd.concat(partes, ignore_index=True)
    c_vr = next((c for c in df.columns if c.startswith("VR_DESPESA")), None)
    df["valor"] = _num(df[c_vr]) if c_vr else np.nan
    return df


# --------------------------------------------------------------------------- candidatos (nomes e siglas)
def load_candidatos(path, cargo: int | None = None, log=print) -> pd.DataFrame | None:
    """Lista de candidatos para dar nome e partido aos números. Aceita o arquivo gerado por
    baixar_bu.py (candidatos_ANO_UF.csv) ou o consulta_cand_ANO_UF.csv do TSE.
    Devolve: numero, nome, sigla, situacao, votos_oficial (quando existir)."""
    if not path:
        return None
    p = Path(path)
    if p.suffix.lower() == ".zip":
        with zipfile.ZipFile(p) as z:
            nm = next((n for n in z.namelist() if n.lower().endswith(".csv") and "_brasil" not in n.lower()), None)
            if nm is None:
                return None
            df = pd.read_csv(z.open(nm), sep=";", encoding="latin-1", dtype=str, low_memory=False)
    else:
        try:
            df = pd.read_csv(p, sep=";", encoding="utf-8", dtype=str, low_memory=False)
        except UnicodeDecodeError:
            df = pd.read_csv(p, sep=";", encoding="latin-1", dtype=str, low_memory=False)
    df.columns = [c.strip().upper() for c in df.columns]
    if "NR_CANDIDATO" not in df.columns:
        return None
    if cargo is not None and "CD_CARGO" in df.columns:
        df = df[df["CD_CARGO"].astype(str) == str(cargo)]
    nome = "NM_URNA_CANDIDATO" if "NM_URNA_CANDIDATO" in df.columns else "NM_CANDIDATO"
    out = pd.DataFrame({
        "numero": pd.to_numeric(df["NR_CANDIDATO"], errors="coerce"),
        "nome": df[nome].astype(str).str.strip(),
        "sigla": df.get("SG_PARTIDO", pd.Series("", index=df.index)).astype(str).str.strip(),
        "situacao": df.get("DS_SIT_TOT_TURNO", pd.Series("", index=df.index)).astype(str).str.strip(),
        "votos_oficial": pd.to_numeric(df.get("QT_VOTOS_OFICIAL", pd.Series(np.nan, index=df.index)),
                                       errors="coerce"),
    }).dropna(subset=["numero"])
    out["numero"] = out["numero"].astype(int)
    log(f"  candidatos: {len(out):,} em {Path(path).name}")
    return out.drop_duplicates("numero").reset_index(drop=True)
