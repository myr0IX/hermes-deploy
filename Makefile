.PHONY: setup telegram start stop restart ps logs shell update help

help:
	@echo "Première fois : setup → telegram → éditer .env → start"
	@echo ""
	@echo "  setup    crée data/, workspace/ et .env à partir de .env.example"
	@echo "  telegram crée le bot Telegram par QR code et remplit .env"
	@echo "  start    démarre le conteneur"
	@echo "  stop     arrête le conteneur"
	@echo "  restart  stop + start"
	@echo "  ps       état du conteneur"
	@echo "  logs     suit les logs"
	@echo "  shell    shell dans le conteneur (utilisateur hermes)"
	@echo "  update   git pull + pull de l'image + redémarrage"

# data/ et workspace/ sont créés ici pour rester la propriété de l'utilisateur
# hôte, et pour que .env soit en place avant le premier `up`.
setup:
	@mkdir -p data workspace
	@cp -n .env.example .env 2>/dev/null || true
	@echo ""
	@echo "1. Lance: make telegram (QR codes : crée le bot, remplit token et user ID)"
	@echo "2. Remplis .env : clé du modèle, identifiants dashboard"
	@echo "3. Vérifie HERMES_UID/HERMES_GID dans .env (id -u, id -g)"
	@echo "4. Lance: make start"

# Runs inside the Hermes image: python, httpx and qrcode ship with it.
telegram:
	docker compose run --rm -u "$$(id -u):$$(id -g)" -v "$(CURDIR):/repo" \
		--entrypoint /opt/hermes/.venv/bin/python hermes /repo/scripts/telegram_setup.py

start:
	docker compose up -d

stop:
	docker compose down

restart: stop start

ps:
	docker compose ps

logs:
	docker compose logs -f hermes

# -u hermes : en root, tout fichier créé sous /opt/data casse la passerelle.
shell:
	docker exec -it -u hermes hermes bash

update:
	git pull --ff-only
	docker compose pull
	docker compose up -d
