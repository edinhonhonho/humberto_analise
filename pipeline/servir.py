#!/usr/bin/env python3
"""Abre o site em http://localhost:8000 e gera na hora a análise de qualquer candidato que ainda não tenha.

    python servir.py                  # usa config.json, porta 8000
    python servir.py config_rs.json   # outra configuração
    python servir.py --porta 9000
    python servir.py --sem-indice     # não recria a lista de candidatos ao iniciar

No botão "Trocar candidato" aparecem todos os candidatos de cada cargo. Quem já tem análise abre na hora;
os outros levam a uma página que roda a análise (10 a 20 segundos) e abre o resultado. Ctrl+C encerra.
"""
import functools
import http.server
import json
import subprocess
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path

BASE = Path(__file__).parent
args = [a for a in sys.argv[1:] if not a.startswith("--")]
porta = 8000
if "--porta" in sys.argv:
    porta = int(sys.argv[sys.argv.index("--porta") + 1])
    args = [a for a in args if a != str(porta)]
cfg_path = Path(args[0]) if args else BASE / "config.json"
cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
saida = Path(cfg.get("saida", "saida_{ano}").format(ano=cfg["ano"], uf=cfg["uf"]))
raiz = (BASE / saida).resolve().parent / "site" if not saida.is_absolute() else saida.parent / "site"
if not (BASE / "rodar.py").exists():
    sys.exit("Rode este arquivo dentro da pasta pipeline_eleicao.")


def rodar(*extra, timeout=900):
    return subprocess.run([sys.executable, str(BASE / "rodar.py"), str(cfg_path), *extra], cwd=BASE,
                          capture_output=True, text=True, errors="replace", timeout=timeout)


if "--sem-indice" not in sys.argv:
    print("Listando os candidatos de cada cargo (na primeira vez pode levar 1 a 2 minutos) ...", flush=True)
    r = rodar("--indice")
    print(r.stdout.strip() or r.stderr.strip()[-600:])

if not raiz.exists():
    print("Ainda não há análises. Gerando as dos candidatos em destaque ...", flush=True)
    r = rodar("--destaques")
    print(r.stdout.strip()[-400:] or r.stderr.strip()[-400:])

trava_geral = threading.Semaphore(2)
travas: dict = {}
travas_lock = threading.Lock()


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def _json(self, obj, status=200):
        corpo = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/api/gerar":
            q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
            try:
                ano, uf, cargo, num = int(q["ano"]), q["uf"].upper(), q["cargo"], int(q["numero"])
                if not cargo.replace("-", "").isalnum() or len(uf) != 2:
                    raise ValueError
            except (KeyError, ValueError):
                return self._json({"ok": False, "erro": "Pedido inválido."}, 400)
            rel = f"data/c/{ano}/{uf.lower()}/{cargo}/{num}.js"
            if (raiz / rel).exists():
                return self._json({"ok": True, "url": f"index.html?c={ano}/{uf.lower()}/{cargo}/{num}"})
            with travas_lock:
                trava = travas.setdefault((ano, uf, cargo, num), threading.Lock())
            with trava, trava_geral:
                if not (raiz / rel).exists():
                    try:
                        r = rodar("--um", uf, cargo, str(num))
                    except subprocess.TimeoutExpired:
                        return self._json({"ok": False, "erro": "A análise demorou demais."})
                    if not (raiz / rel).exists():
                        fim = (r.stdout + r.stderr).strip().splitlines()[-3:]
                        return self._json({"ok": False, "erro": "Não consegui gerar: " + " | ".join(fim)})
            return self._json({"ok": True, "url": f"index.html?c={ano}/{uf.lower()}/{cargo}/{num}"})
        return super().do_GET()

    def log_message(self, fmt, *a):
        if "/api/" in (a[0] if a else ""):
            super().log_message(fmt, *a)


handler = functools.partial(Handler, directory=str(raiz))
srv = http.server.ThreadingHTTPServer(("127.0.0.1", porta), handler)
url = f"http://localhost:{porta}/"
print(f"Servindo {raiz} em {url}  (Ctrl+C para parar)", flush=True)
threading.Timer(0.8, lambda: webbrowser.open(url)).start()
try:
    srv.serve_forever()
except KeyboardInterrupt:
    pass
