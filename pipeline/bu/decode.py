"""Decodifica um boletim de urna (arquivo *-bu.dat) do TSE e devolve os votos por cargo.

Estrutura (ASN.1/BER), conforme observada em boletins reais de 2026:
  envelope { cabeçalho, ..., OCTET STRING = boletim }
  boletim  { ..., [3] {{município, zona}, local, seção}, ..., SEQ eleições }
  eleição  { id, aptos, ..., SEQ grupos }
  grupo    { tipo (1 majoritário, 2 proporcional), comparecimento, SEQ cargos }
  cargo    { [1] código do cargo, ..., SEQ votáveis }
  votável  { [1] tipo do voto (1 nominal, 2 branco, 3 nulo, 4 legenda), [2] quantidade,
             [3] {partido, número} (só nominal e legenda), ordem, hash }
Cada cargo é validado: a soma dos votos tem de bater com o comparecimento (x2 no Senado quando há 2 vagas).
"""
from __future__ import annotations

from .ber import parse

COD_BRANCO, COD_NULO = 95, 96  # convenção do arquivo "votação por seção" do TSE


class BoletimInvalido(ValueError):
    pass


def decodificar(dados: bytes) -> dict:
    """Retorna {local, secao_bu, eleicoes: [{id, aptos, cargos: {cargo: {comparecimento, votos: [(numero, qtd)]}}}]}."""
    try:
        env = parse(dados)[0]
        miolo = next(f for f in env.filhos if not f.cons and f.cls == 0 and f.tag == 4)
        bu = parse(miolo.val)[0]
        ident = next(f for f in bu.filhos if f.cons and f.cls == 0 and f.tag == 16 and len(f.filhos) == 3
                     and f.filhos[0].cons and not f.filhos[1].cons)
        local, secao = ident.filhos[1].inteiro(), ident.filhos[2].inteiro()
        eleicoes = max((f for f in bu.filhos if f.cons and f.cls == 0 and f.tag == 16),
                       key=lambda f: len(f.val))
    except (StopIteration, IndexError, ValueError) as e:
        raise BoletimInvalido(f"estrutura inesperada: {e}") from e

    saida = []
    for e in eleicoes.filhos:
        try:
            id_el, aptos = e.filhos[0].inteiro(), e.filhos[1].inteiro()
            cargos = {}
            for grupo in e.filhos[4].filhos:
                comparec = grupo.filhos[1].inteiro()
                for cg in grupo.filhos[2].filhos:
                    codigo = cg.filhos[0].inteiro()
                    votos, soma = [], 0
                    for v in cg.filhos[2].filhos:
                        c = {f.tag: f for f in v.filhos if f.cls == 2}
                        tipo, qtd = c[1].inteiro(), c[2].inteiro()
                        if tipo == 2:
                            numero = COD_BRANCO
                        elif tipo == 3:
                            numero = COD_NULO
                        else:  # 1 nominal, 4 legenda
                            numero = c[3].filhos[1].inteiro()
                        votos.append((numero, qtd))
                        soma += qtd
                    cargos[codigo] = {"comparecimento": comparec, "soma": soma, "votos": votos}
        except (IndexError, KeyError, ValueError) as ex:
            raise BoletimInvalido(f"eleição {e.filhos[0].inteiro() if e.filhos else '?'}: {ex}") from ex
        saida.append({"id": id_el, "aptos": aptos, "cargos": cargos})
    return {"local": local, "secao_bu": secao, "eleicoes": saida}
