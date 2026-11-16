
import json
import os
import re
import sys
import urllib.request
import unicodedata

from html.parser import HTMLParser
from pathlib import Path
from datetime import datetime, timezone


URL = "https://andaconhecerportugal.pt/"
STATE = Path("estado.json")


class Text(HTMLParser):

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg"):
            if self.hidden:
                self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def run():

    # 1. Consultar a página
    req = urllib.request.Request(
        URL,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Cache-Control": "no-cache",
            "Accept-Language": "pt-PT,pt;q=0.9"
        }
    )

    with urllib.request.urlopen(req, timeout=25) as response:
        html = response.read().decode(
            "utf-8",
            errors="replace"
        )

    # 2. Extrair texto visível
    parser = Text()
    parser.feed(html)

    raw = " ".join(parser.parts).lower()

    # Remover acentos
    raw = "".join(
        c for c in unicodedata.normalize("NFKD", raw)
        if not unicodedata.combining(c)
    )

    # Normalizar espaços
    raw = re.sub(r"\s+", " ", raw)

    # 3. Validar conteúdo
    if (
        len(raw) < 150
        or "anda" not in raw
        or "voucher" not in raw
    ):
        raise RuntimeError(
            "Página inesperada ou incompleta. "
            "Estado anterior preservado."
        )

    # 4.  Verificar se a mensagem atual de esgotamento existe
    exhausted = bool(re.search(
        r"\binfelizmente\s+ja\s+esgotamos\s+os\s+30[.\s]?000\s+vouchers\s+deste\s+ano\b",
        raw
    ))



    current = (
        "esgotado"
        if exhausted
        else "possivel_reabertura"
    )

    # 5. Ler estado anterior
    previous = (
        json.loads(
            STATE.read_text(encoding="utf-8")
        ).get("estado")
        if STATE.exists()
        else None
    )

    print(
        f"Estado anterior: {previous}; "
        f"atual: {current}"
    )

    # 6. Enviar notificação apenas
    # quando deixa de estar esgotado
    if (
        previous == "esgotado"
        and current == "possivel_reabertura"
    ):

        webhook = os.environ.get("N8N_WEBHOOK_URL")

        if not webhook:
            raise RuntimeError(
                "Secret N8N_WEBHOOK_URL não configurado."
            )

        payload = {
            "evento": "anda_possivel_reabertura",
            "estado_anterior": previous,
            "estado_atual": current,
            "mensagem": (
                "A mensagem de vouchers esgotados "
                "desapareceu. Confirma a disponibilidade."
            ),
            "url": URL,
            "verificado_em": datetime.now(
                timezone.utc
            ).isoformat()
        }

        data = json.dumps(
            payload,
            ensure_ascii=False
        ).encode("utf-8")

        request = urllib.request.Request(
            webhook,
            data=data,
            headers={
                "Content-Type": "application/json"
            },
            method="POST"
        )

        with urllib.request.urlopen(
            request,
            timeout=20
        ) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError(
                    f"Webhook HTTP {response.status}"
                )

        print("Notificação enviada ao n8n!")

    # 7. Guardar estado apenas se mudou
    if previous != current:

        STATE.write_text(
            json.dumps(
                {
                    "estado": current,
                    "atualizado_em": datetime.now(
                        timezone.utc
                    ).isoformat()
                },
                indent=2,
                ensure_ascii=False
            ) + "\n",
            encoding="utf-8"
        )

        print("Estado alterado")

    else:
        print("Estado sem alterações")


if __name__ == "__main__":

    try:
        run()

    except Exception as e:
        print(f"ERRO: {e}", file=sys.stderr)
        sys.exit(1)
