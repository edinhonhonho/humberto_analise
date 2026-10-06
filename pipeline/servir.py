#!/usr/bin/env python3
"""Abre o site em http://localhost:8000 (pasta site/ ao lado deste arquivo). Ctrl+C encerra.

    python servir.py            # porta 8000
    python servir.py 9000       # outra porta
"""
import functools
import http.server
import sys
import threading
import webbrowser
from pathlib import Path

porta = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
raiz = Path(__file__).parent / "site"
if not raiz.exists():
    sys.exit(f"Não achei {raiz}. Rode antes: python rodar.py --lote")
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(raiz))
srv = http.server.ThreadingHTTPServer(("127.0.0.1", porta), handler)
url = f"http://localhost:{porta}/"
print(f"Servindo {raiz} em {url}  (Ctrl+C para parar)")
threading.Timer(0.8, lambda: webbrowser.open(url)).start()
try:
    srv.serve_forever()
except KeyboardInterrupt:
    pass
