"""Monta a pasta 'site_publicar' pronta para hospedar (Vercel, GitHub Pages, Cloudflare Pages...).

Copia 'site/' sem os restos de versões antigas (pastas numéricas por cargo e índices antigos) e sem
arquivos temporários, e mostra o tamanho final. Uso:  python publicar.py [pasta_site] [pasta_saida]
"""
import re
import shutil
import sys
from pathlib import Path

src = Path(sys.argv[1] if len(sys.argv) > 1 else "site")
dst = Path(sys.argv[2] if len(sys.argv) > 2 else "site_publicar")
if not src.is_dir():
    sys.exit(f"Pasta {src} não encontrada.")


def ignorar(pasta, nomes):
    pasta = Path(pasta)
    sai = []
    for n in nomes:
        if n in (".trava", "Thumbs.db", ".DS_Store"):
            sai.append(n)
        elif pasta.parent == src and re.fullmatch(r"\d{4}", pasta.name) is None and False:
            pass
        elif pasta.parent.parent == src and re.fullmatch(r"\d{4}", pasta.parent.name) and re.fullmatch(r"\d+", n):
            sai.append(n)   # site/ANO/UF/<número do cargo>: formato antigo
        elif pasta.name == "idx" and re.fullmatch(r"\d{4}_[A-Z]{2}_\d+\.(js|json)", n):
            sai.append(n)   # índice antigo por número de cargo
    return sai


if dst.exists():
    shutil.rmtree(dst)
shutil.copytree(src, dst, ignore=ignorar)
arqs = [f for f in dst.rglob("*") if f.is_file()]
print(f"{dst}: {len(arqs)} arquivos, {sum(f.stat().st_size for f in arqs) / 1e6:.0f} MB")
