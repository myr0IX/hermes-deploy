.PHONY: setup start stop restart ps logs shell update help

help:
	@echo "Première fois : setup → start"
	@echo ""
	@echo "  setup    assistant interactif : crée data/, workspace/ et remplit .env"
	@echo "  start    démarre le conteneur"
	@echo "  stop     arrête le conteneur"
	@echo "  restart  stop + start"
	@echo "  ps       état du conteneur"
	@echo "  logs     suit les logs"
	@echo "  shell    shell dans le conteneur (utilisateur hermes)"
	@echo "  update   git pull + pull de l'image + redémarrage"

# data/ et workspace/ sont créés ici pour rester la propriété de l'utilisateur
# hôte, et pour que .env soit en place avant le premier `up`.
# The wizard runs inside the Hermes image: python, httpx and qrcode ship with it.
setup:
	@mkdir -p data workspace
	@cp -n .env.example .env 2>/dev/null || true
	@docker compose run --rm -u "$$(id -u):$$(id -g)" -v "$(CURDIR):/repo" \
		--entrypoint /opt/hermes/.venv/bin/python hermes /repo/scripts/configure.py

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
