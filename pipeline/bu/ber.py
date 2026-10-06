"""Leitor mínimo de BER (ASN.1) para os boletins de urna do TSE. Sem dependências externas."""
from __future__ import annotations


class No:
    __slots__ = ("cls", "cons", "tag", "val", "filhos")

    def __init__(self, cls, cons, tag, val, filhos):
        self.cls, self.cons, self.tag, self.val, self.filhos = cls, cons, tag, val, filhos

    def inteiro(self) -> int:
        return int.from_bytes(self.val, "big", signed=True)

    def texto(self) -> str:
        return self.val.decode("latin-1")


def parse(buf: bytes, i: int = 0, fim: int | None = None) -> list[No]:
    fim = len(buf) if fim is None else fim
    nos = []
    while i < fim:
        b = buf[i]
        cls, cons, tag = b >> 6, (b >> 5) & 1, b & 31
        i += 1
        if tag == 31:
            tag = 0
            while True:
                x = buf[i]
                i += 1
                tag = (tag << 7) | (x & 127)
                if not x & 128:
                    break
        n = buf[i]
        i += 1
        if n & 128:
            k = n & 127
            if k == 0:
                raise ValueError("comprimento indefinido não suportado")
            n = int.from_bytes(buf[i:i + k], "big")
            i += k
        v = buf[i:i + n]
        nos.append(No(cls, bool(cons), tag, v, parse(buf, i, i + n) if cons else None))
        i += n
    return nos
