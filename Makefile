IMAGE := nousresearch/hermes-agent:v2026.6.5

.PHONY: setup init start stop logs update shell

setup:
	@mkdir -p data
	@cp -n .env.example .env 2>/dev/null || true
	@echo ""
	@echo "1. Remplis .env avec ton token Telegram et ton user ID"
	@echo "2. Lance: make init"

init:
	@echo ""
	@echo "Scanne ce QR code avec Telegram pour créer ton bot via @BotFather :"
	@echo ""
	@python3 -c "import qrcode; qr = qrcode.QRCode(); qr.add_data('https://t.me/botfather'); qr.print_ascii(invert=True)" 2>/dev/null || \
		(pip3 install qrcode --quiet && python3 -c "import qrcode; qr = qrcode.QRCode(); qr.add_data('https://t.me/botfather'); qr.print_ascii(invert=True)")
	@echo ""
	@echo "Dans @BotFather : /newbot → donne un nom → copie le token dans .env"
	@echo ""
	@read -p "Appuie sur Entrée quand ton token est dans .env..." _; \
	docker run -it --rm \
		-v $(PWD)/data:/opt/data \
		--env-file .env \
		$(IMAGE) \
		gateway setup

start:
	docker compose up -d

stop:
	docker compose down

logs:
	docker compose logs -f hermes

shell:
	docker exec -it hermes bash

# Pour upgrader : mettre à jour IMAGE ici ET dans docker-compose.yml
update:
	docker pull $(IMAGE)
	docker compose up -d
