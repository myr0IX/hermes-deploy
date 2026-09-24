"""Interactive .env setup: model key, dashboard login, Telegram bot, workspace.

Runs inside the Hermes image (see `make setup`): python, httpx and qrcode ship with it.
Nothing touches .env until every section is answered.
"""

import getpass
import os
import secrets
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import qrcode

ENV_PATH = Path("/repo/.env")
TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/{method}"
POLL_SECONDS = 30
WAIT_SECONDS = 300
MIN_PASSWORD_LENGTH = 12


@dataclass(frozen=True)
class ModelProvider:
    label: str
    env_name: str
    keys_url: str
    check_url: str

    def headers(self, key: str) -> dict[str, str]:
        if self.env_name == "ANTHROPIC_API_KEY":
            return {"x-api-key": key, "anthropic-version": "2023-06-01"}
        return {"Authorization": f"Bearer {key}"}


MODEL_PROVIDERS = {
    "1": ModelProvider("Anthropic", "ANTHROPIC_API_KEY", "https://console.anthropic.com/settings/keys",
                       "https://api.anthropic.com/v1/models"),
    "2": ModelProvider("OpenRouter", "OPENROUTER_API_KEY", "https://openrouter.ai/keys",
                       "https://openrouter.ai/api/v1/key"),
    "3": ModelProvider("OpenAI", "OPENAI_API_KEY", "https://platform.openai.com/api-keys",
                       "https://api.openai.com/v1/models"),
}


class TelegramError(Exception):
    def __init__(self, status_code: int, description: str):
        super().__init__(description)
        self.status_code = status_code


def read_env() -> dict[str, str]:
    values = {}
    for line in ENV_PATH.read_text().splitlines():
        key, separator, value = line.partition("=")
        if separator and not key.startswith("#"):
            values[key.strip()] = value.strip().strip("'\"")
    return values


def write_env(values: dict[str, str]) -> None:
    """Set each key in place (active line, else its `# KEY=` placeholder, else appended).

    Values are single-quoted: Compose interpolates `$` in unquoted env_file values.
    """
    lines = ENV_PATH.read_text().splitlines()
    for key, value in values.items():
        prefixes = (f"{key}=", f"# {key}=") if value else (f"{key}=",)
        index = next((i for i, line in enumerate(lines) if line.startswith(prefixes)), None)
        entry = f"{key}='{value}'"
        if index is not None:
            lines[index] = entry
        elif value:
            lines.append(entry)
    ENV_PATH.write_text("\n".join(lines) + "\n")
    ENV_PATH.chmod(0o600)


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        answer = input(f"{prompt}{suffix} : ").strip() or default
        if "'" not in answer:
            return answer
        print("L'apostrophe n'est pas acceptée.")


def should_configure(section: str, done: bool) -> bool:
    print(f"\n== {section} ==")
    return not done or input("Déjà configuré. Refaire ? [o/N] ").strip().lower() in ("o", "oui")


def print_qr(url: str) -> None:
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.print_ascii(invert=True)
    print(f"  {url}\n")


def telegram_call(client: httpx.Client, token: str, method: str, **params):
    response = client.get(TELEGRAM_API_URL.format(token=token, method=method), params=params)
    data = response.json()
    if not data["ok"]:
        raise TelegramError(response.status_code, data["description"])
    return data["result"]


def ask_model_key(client: httpx.Client, provider: ModelProvider) -> str:
    while True:
        key = getpass.getpass(f"Colle la clé {provider.label} (saisie masquée) : ").strip()
        try:
            status = client.get(provider.check_url, headers=provider.headers(key)).status_code
        except httpx.HTTPError as error:
            print(f"Vérification impossible ({error}), clé gardée telle quelle.")
            return key
        if status in (401, 403):
            print(f"Clé refusée par {provider.label}, réessaie.")
            continue
        if status != 200:
            print(f"Réponse inattendue de {provider.label} ({status}), clé gardée telle quelle.")
        return key


def configure_model(client: httpx.Client, current: dict[str, str]) -> dict[str, str]:
    if not should_configure("Modèle", any(current.get(p.env_name) for p in MODEL_PROVIDERS.values())):
        return {}
    for choice, provider in MODEL_PROVIDERS.items():
        print(f"  {choice}. {provider.label}")
    while (provider := MODEL_PROVIDERS.get(ask("Fournisseur", "1"))) is None:
        print("Choix invalide.")
    print(f"Crée une clé ici : {provider.keys_url}")
    key = ask_model_key(client, provider)
    if provider.env_name == "OPENAI_API_KEY":
        print("Avec OpenAI, ajuste `model` dans data/config.yaml après le premier lancement.")
    # Blank the other keys so provider auto-detection cannot pick a stale one.
    return {p.env_name: key if p is provider else "" for p in MODEL_PROVIDERS.values()}


def ask_password() -> str:
    while True:
        password = getpass.getpass("Mot de passe (Entrée = en générer un) : ")
        if not password:
            password = secrets.token_urlsafe(18)
            print(f"Mot de passe généré, note-le maintenant : {password}")
            return password
        if len(password) < MIN_PASSWORD_LENGTH:
            print(f"{MIN_PASSWORD_LENGTH} caractères minimum.")
        elif "'" in password:
            print("L'apostrophe n'est pas acceptée.")
        elif getpass.getpass("Confirme : ") != password:
            print("Les deux saisies diffèrent.")
        else:
            return password


def configure_dashboard(current: dict[str, str]) -> dict[str, str]:
    username = current.get("HERMES_DASHBOARD_BASIC_AUTH_USERNAME", "")
    if not should_configure("Dashboard", bool(username and current.get("HERMES_DASHBOARD_BASIC_AUTH_PASSWORD"))):
        return {}
    return {
        "HERMES_DASHBOARD_BASIC_AUTH_USERNAME": ask("Identifiant", username or "admin"),
        "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD": ask_password(),
        # New credentials: rotate the signing secret so existing sessions are logged out.
        "HERMES_DASHBOARD_BASIC_AUTH_SECRET": secrets.token_hex(32),
    }


def ask_bot_token(client: httpx.Client) -> tuple[str, str]:
    while True:
        token = getpass.getpass("Colle le token donné par BotFather (saisie masquée) : ").strip()
        try:
            return token, telegram_call(client, token, "getMe")["username"]
        except TelegramError:
            print("Token refusé par Telegram, réessaie.")


def wait_for_owner(client: httpx.Client, token: str) -> dict:
    """Return the sender of the first private message, then acknowledge it so the gateway never sees it."""
    params = {"timeout": POLL_SECONDS}
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        for update in telegram_call(client, token, "getUpdates", **params):
            params["offset"] = update["update_id"] + 1
            message = update.get("message", {})
            sender = message.get("from", {})
            if message.get("chat", {}).get("type") == "private" and not sender.get("is_bot"):
                telegram_call(client, token, "getUpdates", offset=params["offset"], timeout=0)
                return sender
    raise TimeoutError


def configure_telegram(client: httpx.Client, current: dict[str, str]) -> dict[str, str]:
    done = bool(current.get("TELEGRAM_BOT_TOKEN") and current.get("TELEGRAM_ALLOWED_USERS"))
    if not should_configure("Telegram", done):
        return {}
    print("1. Scanne ce QR code : il ouvre BotFather. Envoie /newbot et suis les étapes.\n")
    print_qr("https://t.me/BotFather")
    token, username = ask_bot_token(client)
    print(f"\n2. Bot @{username} trouvé. Scanne ce QR code et appuie sur « Démarrer ».\n")
    print_qr(f"https://t.me/{username}")
    print("En attente de ton message…")
    try:
        owner = wait_for_owner(client, token)
    except TelegramError as error:
        if error.status_code != 409:
            raise
        print(f"Ce bot est déjà relevé ailleurs ({error}). Si Hermes tourne : make stop, puis relance make setup.")
        return {}
    except TimeoutError:
        print(f"Aucun message reçu en {WAIT_SECONDS // 60} min : section ignorée, relance make setup.")
        return {}
    print(f"✓ Bot @{username}, accès réservé à {owner.get('first_name', '')} ({owner['id']}).")
    return {"TELEGRAM_BOT_TOKEN": token, "TELEGRAM_ALLOWED_USERS": str(owner["id"])}


def configure_workspace(current: dict[str, str]) -> dict[str, str]:
    print("\n== Workspace ==")
    path = ask("Chemin absolu, sur le serveur, du projet à monter dans /workspace",
               current.get("WORKSPACE_PATH") or "./workspace")
    return {"WORKSPACE_PATH": path}


def automatic_values(current: dict[str, str]) -> dict[str, str]:
    # The container runs with the host user's UID/GID (`make setup` passes -u).
    return {
        "HERMES_UID": str(os.getuid()),
        "HERMES_GID": str(os.getgid()),
        "HERMES_DASHBOARD_BASIC_AUTH_SECRET": current.get("HERMES_DASHBOARD_BASIC_AUTH_SECRET") or secrets.token_hex(32),
    }


def main() -> None:
    current = read_env()
    with httpx.Client(timeout=POLL_SECONDS + 10) as client:
        values = {
            **automatic_values(current),
            **configure_model(client, current),
            **configure_dashboard(current),
            **configure_telegram(client, current),
            **configure_workspace(current),
        }
    write_env(values)
    print("\n✓ .env à jour. Lance make start (make restart si Hermes tourne déjà).")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        sys.exit("\nInterrompu, .env inchangé.")
    except TelegramError as error:
        sys.exit(f"Telegram a refusé la requête ({error}), .env inchangé.")
    except httpx.HTTPError as error:
        sys.exit(f"Réseau injoignable ({error}), .env inchangé.")
