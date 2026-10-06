"""Número do partido a partir do número do candidato, para qualquer cargo.

O número do candidato começa com o do partido (2 dígitos): presidente e governador têm 2 dígitos
(o próprio partido), senador 3, deputado federal 4 e estadual 5. Voto de legenda também tem 2 dígitos.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def partido_de(n):
    """Aceita inteiro, array ou Series; devolve o mesmo tipo (Series mantém o índice)."""
    a = np.asarray(n, dtype="int64")
    dig = np.floor(np.log10(np.maximum(a, 1))).astype("int64") + 1
    p = a // (10 ** np.maximum(dig - 2, 0))
    if isinstance(n, pd.Series):
        return pd.Series(p, index=n.index)
    return int(p) if p.ndim == 0 else p
