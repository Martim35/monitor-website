import json, os, re, sys, urllib.request, unicodedata
from html.parser import HTMLParser
from pathlib import Path
from datetime import datetime, timezone

URL = "https://andaconhecerportugal.pt/"
STATE = Path("estado.json")

class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self.hidden += 1
    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self.hidden:
            self.hidden -= 1
    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)

def run():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=25) as response:
        html = response.read().decode("utf-8", errors="replace")
    parser = Text()
    parser.feed(html)
    raw = " ".join(parser.parts).lower()
    raw = "".join(c for c in unicodedata.normalize("NFKD", raw) if not unicodedata.combining(c))
    raw = re.sub(r"\s+", " ", raw)
    if len(raw) < 150 or "anda" not in raw or "voucher" not in raw:
        raise RuntimeError("Pagina inesperada; estado preservado")
    exhausted = bool(re.search(r"(?:ultimos\s+10[.\s]?000\\s+vouchers\s+ja\s+esgotaram|vouchers?\s+(?:ja\s+)?esgotad[oa]s?|sem\s+vouchers?\s+disponiveis)", raw))
    current = "esgotado" if exhausted else "possivel_reabertura"
    previous = json.loads(STATE.read_text())["estado"] if STATE.exists() else None
    print(f"Estado anterior: {previous}; atual: {current}")
    if previous == "esgotado" and current == "possivel_reabertura":
        url = os.environ.get("N8N_WEBHOOK_URL")
        if not url:
            raise RuntimeError("Falta secret N8N_WEBHOOK_URL")
        data = json.dumps({"evento":"anda_possivel_reabertura","url":URL,"estado_anterior":previous,"estado_atual":current,"mensagem":"A mensagem de vouchers esgotados desapareceu. Confirma a disponibilidade.","verificado_em":datetime.now(timezone.utc).isoformat()}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type":"application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=20) as resp:
            if not 200 <= resp.status < 300:
                raise RuntimeError(f"Webhook HTTP {resp.status}")
        print("Notificacao enviada")
    if previous != current:
        STATE.write_text(json.dumps({"estado":current,"atualizado_em":datetime.now(timezone.utc).isoformat()},indent=2)+"\n")
        print("Estado alterado")
if __name__ == "__main__":
    try: run()
    except Exception as e:
        print(f"ERRO: {e}",file=sys.stderr)
        sys.exit(1)
