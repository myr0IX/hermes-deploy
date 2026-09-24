# hermes-deploy

Déploiement Docker de [Hermes Agent](https://hermes-agent.nousresearch.com) (Nous Research).

Tout se passe sur la machine qui héberge le conteneur : on clone ce repo dessus, on remplit `.env`, on lance. Ici, le homelab (voir le repo `HomeLab`).

## Prérequis

- Docker et `git` sur la machine
- Telegram sur ton téléphone
- Une clé API de modèle (Anthropic, OpenAI ou OpenRouter)

## Installation

```
git clone https://github.com/myr0IX/hermes-deploy.git
cd hermes-deploy
make setup          # assistant interactif : remplit .env
make start
make logs           # vérifier le démarrage, puis écrire au bot sur Telegram
```

`make setup` pose les questions section par section et n'écrit `.env` qu'à la fin (Ctrl-C : rien n'est modifié) :

1. **Modèle** : Anthropic, OpenRouter ou OpenAI. Le lien vers la page de création de clé s'affiche, la clé collée est vérifiée auprès du fournisseur.
2. **Dashboard** : identifiant et mot de passe locaux (Entrée = mot de passe généré). Pas d'OAuth via Nous Portal.
3. **Telegram** : deux QR codes à scanner avec le téléphone. BotFather : envoyer `/newbot`, puis coller le token dans le terminal. Le nouveau bot : appuyer sur « Démarrer », ton user ID est détecté à partir de ce message.
4. **Workspace** : le projet monté dans `/workspace`.

`HERMES_UID`/`HERMES_GID` et le secret de session du dashboard sont posés automatiquement. Relancé, `make setup` propose de refaire chaque section déjà remplie ; ensuite `make restart` si Hermes tourne.

Le bot est créé par BotFather sur ton compte : il t'appartient entièrement, sans passer par le service d'onboarding de Nous (dont le bot gestionnaire garderait le droit de relire et de révoquer le token). Pour refaire la section Telegram sur un bot déjà utilisé par Hermes, faire d'abord `make stop`.

## Mises à jour

`make update` — `git pull` + pull de l'image + redémarrage. `data/` et `.env` sont gitignored, ils ne bougent pas.

L'image étant épinglée, `update` ne change pas de version tant que le tag n'est pas bumpé dans `docker-compose.yml`.

## Dashboard

Le dashboard (`9119`) n'est publié que sur la loopback. Sur un serveur headless, y accéder par tunnel SSH **depuis ton poste** :

```
ssh -N -L 9119:127.0.0.1:9119 homelab    # puis http://localhost:9119
```

L'API OpenAI-compatible n'est pas exposée. Pour l'activer : `API_SERVER_ENABLED=true`, `API_SERVER_HOST=0.0.0.0`, `API_SERVER_KEY` dans `.env`, et publier `127.0.0.1:8642:8642` dans le compose.

## Cibles `make`

| Cible      | Effet                                          |
| ---------- | ---------------------------------------------- |
| `setup`    | crée `data/`, `workspace/`, remplit `.env`     |
| `start`    | démarre le conteneur                           |
| `stop`     | arrête le conteneur                            |
| `restart`  | `stop` + `start`                               |
| `ps`       | état du conteneur                              |
| `logs`     | suit les logs                                  |
| `shell`    | shell dans le conteneur (utilisateur `hermes`) |
| `update`   | `git pull` + pull de l'image + redémarrage     |

## Choix de déploiement

**Rien n'est publié hors de `127.0.0.1`.** Un port publié sur `0.0.0.0` **contournerait `ufw`** : le DNAT posé par Docker et sa chaîne `FORWARD` sont évalués avant les chaînes d'`ufw`, donc un `deny incoming` ne s'appliquerait pas. Publier sur l'IP du tunnel WireGuard (`10.8.0.1`) casserait le démarrage du conteneur tant que l'interface n'est pas montée. D'où le tunnel SSH ci-dessus.

**Version épinglée dans `docker-compose.yml`**, une seule fois : `${HERMES_VERSION:-v2026.9.7}`. Pas de `:latest`. Pour changer de version : modifier le défaut, ou poser `HERMES_VERSION` dans `.env`.

**Pas de socket Docker monté.** Hermes sait déléguer l'exécution à des conteneurs (`TERMINAL_DOCKER_IMAGE`, `HERMES_DOCKER_BINARY`), ce qui imposerait de monter `/var/run/docker.sock` — soit root sur l'hôte depuis le conteneur. On reste sur l'exécution locale par défaut.

**`cap_drop: ALL` + six capabilities rendues.** Le conteneur démarre root (s6-overlay), chown le volume de données, puis bascule sur l'utilisateur `hermes` : `SETUID`/`SETGID` sont indispensables, `CHOWN`/`DAC_OVERRIDE`/`FOWNER` servent à la préparation du volume, `KILL` à l'arrêt propre. Le profil « drop ALL » sans exception de la doc sécurité concerne les sandbox lancées *par* Hermes, pas la passerelle.

**Plafond mémoire à 4 Go** (`deploy.resources.limits`), le homelab n'ayant que 7,6 Go à partager avec le reste des services. La doc recommande 2 à 4 Go, dont au moins 2 Go si l'outil navigateur est utilisé — d'où aussi `shm_size: 1g` (Chromium/Playwright).

## Pièges

- `TELEGRAM_ALLOWED_USERS` attend l'ID de **ton compte humain**, pas le préfixe numérique du token du bot (`123456789:ABC...` → `123456789` est l'ID du bot, mauvaise valeur). Symptôme : le bot ignore tous les messages. `make setup` le détecte correctement ; à surveiller seulement en remplissant à la main.
- Compose interprète les `$` des valeurs de `.env` non entourées d'apostrophes : un mot de passe `ab$cd` deviendrait `ab`. `make setup` écrit tout entre apostrophes ; en éditant à la main, faire pareil.
- **Ne pas lancer `hermes gateway setup`** dans le conteneur : l'assistant écrit dans `/opt/data/.env`, qui est rechargé par-dessus l'environnement du compose et masquerait silencieusement ce `.env`. Tout se configure ici.
- Le dashboard n'est **pas** joignable à `http://<ip-serveur>:9119` — c'est volontaire, passer par le tunnel SSH.
- `data/` contient les clés API, les sessions et la mémoire de l'agent : gitignored, jamais commité.
- Avec une clé OpenAI ou OpenRouter seule, le modèle par défaut (`anthropic/claude-opus-4.6`) ne conviendra pas : ajuster `model` dans `data/config.yaml` après le premier lancement.
