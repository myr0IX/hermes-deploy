"""Create the Telegram bot through QR codes and fill the TELEGRAM_* lines of .env.

Runs inside the Hermes image (see `make telegram`): python, httpx and qrcode ship with it.
"""

import getpass
import sys
import time
from pathlib import Path

import httpx
import qrcode

ENV_PATH = Path("/repo/.env")
API_URL = "https://api.telegram.org/bot{token}/{method}"
POLL_SECONDS = 30
WAIT_SECONDS = 300


class TelegramError(Exception):
    def __init__(self, status_code: int, description: str):
        super().__init__(description)
        self.status_code = status_code


def call(client: httpx.Client, token: str, method: str, **params):
    response = client.get(API_URL.format(token=token, method=method), params=params)
    data = response.json()
    if not data["ok"]:
        raise TelegramError(response.status_code, data["description"])
    return data["result"]


def print_qr(url: str) -> None:
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.print_ascii(invert=True)
    print(f"  {url}\n")


def ask_token(client: httpx.Client) -> tuple[str, str]:
    while True:
        token = getpass.getpass("Colle le token donné par BotFather (saisie masquée) : ").strip()
        try:
            return token, call(client, token, "getMe")["username"]
        except TelegramError:
            print("Token refusé par Telegram, réessaie.")


def wait_for_owner(client: httpx.Client, token: str) -> dict:
    """Return the sender of the first private message, then acknowledge it so the gateway never sees it."""
    params = {"timeout": POLL_SECONDS}
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        for update in call(client, token, "getUpdates", **params):
            params["offset"] = update["update_id"] + 1
            message = update.get("message", {})
            sender = message.get("from", {})
            if message.get("chat", {}).get("type") == "private" and not sender.get("is_bot"):
                call(client, token, "getUpdates", offset=params["offset"], timeout=0)
                return sender
    raise TimeoutError


def write_env(values: dict[str, str]) -> None:
    lines = ENV_PATH.read_text().splitlines()
    pending = dict(values)
    for index, line in enumerate(lines):
        key = line.split("=", 1)[0]
        if key in pending:
            lines[index] = f"{key}={pending.pop(key)}"
    lines += [f"{key}={value}" for key, value in pending.items()]
    ENV_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    print("1. Scanne ce QR code : il ouvre BotFather. Envoie /newbot et suis les étapes.\n")
    print_qr("https://t.me/BotFather")
    with httpx.Client(timeout=POLL_SECONDS + 10) as client:
        token, username = ask_token(client)
        print(f"\n2. Bot @{username} trouvé. Scanne ce QR code et appuie sur « Démarrer ».\n")
        print_qr(f"https://t.me/{username}")
        print("En attente de ton message…")
        try:
            owner = wait_for_owner(client, token)
        except TelegramError as error:
            if error.status_code == 409:
                sys.exit(f"Ce bot est déjà relevé ailleurs ({error}). Si Hermes tourne : make stop, puis relance.")
            raise
        except TimeoutError:
            sys.exit(f"Aucun message reçu en {WAIT_SECONDS // 60} min, .env inchangé : relance make telegram.")

    write_env({"TELEGRAM_BOT_TOKEN": token, "TELEGRAM_ALLOWED_USERS": str(owner["id"])})
    print(f"\n✓ .env rempli : bot @{username}, accès réservé à {owner.get('first_name', '')} ({owner['id']}).")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nInterrompu, .env inchangé.")
    except httpx.HTTPError as error:
        sys.exit(f"Telegram injoignable ({error}), .env inchangé.")
