# Projet 11 — Livraison Docker portable

## Contenu

Le projet applicatif (API, modèle entraîné, dataset, simulateur et consumer) est contenu dans l'image `pdm-project:1.0`. Les autres services gardent leurs images dédiées. Une seule archive `projet-11-images.tar` transporte les sept images : projet Python, Mosquitto, InfluxDB, Grafana, Node-RED, PostgreSQL et ThingsBoard.

Cette archive est créée par `EXPORTER-DOCKER.ps1` depuis le dossier source. Elle n'est pas préconstruite dans le ZIP du code : l'accès au moteur Docker est refusé depuis la session de réalisation.

## Construire et exporter depuis le projet source

Démarrer Docker Desktop en mode conteneurs Linux, puis exécuter depuis PowerShell :

```powershell
.\EXPORTER-DOCKER.ps1
```

Le script crée un nouveau dossier `export-docker-...` à côté du projet. Il construit l'image applicative, récupère les images externes manquantes, puis sauvegarde toutes les images et les configurations. Le téléchargement et l'export peuvent représenter plusieurs Go. Aucun conteneur actif n'est arrêté par ce script.

Le dossier de livraison contient `projet-11-images.tar`, sa somme SHA256, `images-manifest.txt`, `docker-compose.yml`, `.env.example` et les fichiers de configuration et de référence. Copier le dossier entier sur l'autre ordinateur. Le modèle et les données sont aussi intégrés à l'image applicative.

## Importer sur la machine cible

Docker Desktop et Docker Compose doivent être disponibles. Utiliser la même architecture de processeur que celle indiquée dans `images-manifest.txt` (habituellement linux/amd64).

Depuis le dossier de livraison :

```powershell
$expected = ((Get-Content .\projet-11-images.sha256).Trim() -split '\s+')[0]
$actual = (Get-FileHash .\projet-11-images.tar -Algorithm SHA256).Hash
if ($expected -ne $actual) { throw 'Archive incomplète ou modifiée.' }
docker image load --input .\projet-11-images.tar
if (!(Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d --no-build --pull never
```

Le Compose portable utilise un nom de projet distinct, `maintenance-predictive-iot-portable`, et de nouveaux volumes. Les ports restent les mêmes : arrêter l'autre déploiement avant de lancer les deux sur un même ordinateur.

## Initialiser ThingsBoard sur une nouvelle installation

Exécuter l'installation de base UNE SEULE FOIS par nouveau volume PostgreSQL :

```powershell
docker compose --profile full up -d --pull never postgres
docker compose --profile full run --rm --pull never -e INSTALL_TB=true -e LOAD_DEMO=true thingsboard
docker compose --profile full up -d --pull never thingsboard
```

Attendre que http://localhost:8080 réponde, puis :

```powershell
docker compose run --rm --no-deps --pull never api python -m pdm.provision_thingsboard --url http://thingsboard:8080
notepad .env
```

Remplacer `TB_ENABLED=0` par `TB_ENABLED=1`, enregistrer, puis :

```powershell
docker compose --profile full up -d --no-build --pull never
docker compose --profile demo up -d --no-build --pull never simulator
```

Pour les démarrages suivants, réutiliser ces deux dernières commandes sans réinitialiser ThingsBoard.

## Interfaces

| Interface | URL | Identifiants par défaut |
|---|---|---|
| Supervision | http://localhost:8000 | Aucun |
| API | http://localhost:8000/docs | Aucun |
| Grafana | http://localhost:3000 | admin / pdm-local-password |
| InfluxDB | http://localhost:8086 | admin / pdm-local-password |
| Node-RED | http://localhost:1880 | Aucun |
| ThingsBoard | http://localhost:8080 | tenant@thingsboard.org / tenant |

Si Node-RED montre uniquement son flux d'accueil, importer `node_red/flows.json`. Pour utiliser cette branche, arrêter le consumer Python avant d'activer le flux et de cliquer sur Déployer. Les mesures du simulateur peuvent ensuite être envoyées avec :

```powershell
docker compose stop consumer
docker compose --profile demo run --rm --no-deps --pull never simulator python -m pdm.simulator --count 20 --interval 1
```

## Périmètre de l'export

Les images transportent les logiciels et le modèle. Les historiques des bases, les flux modifiés dans le volume Node-RED, les alarmes existantes et les tokens de l'installation d'origine ne sont pas inclus. Ce paquet permet une nouvelle installation du projet ; il ne remplace pas une sauvegarde des volumes.

Les configurations publiques sont copiées depuis le projet source. Les données personnelles de `.env` et `runtime/` ne sont pas copiées. La validation Docker de la construction, de l'export et de l'import reste à effectuer depuis un terminal disposant de l'accès au moteur.

Références : [docker image save](https://docs.docker.com/reference/cli/docker/image/save/) et [docker image load](https://docs.docker.com/reference/cli/docker/image/load/).
