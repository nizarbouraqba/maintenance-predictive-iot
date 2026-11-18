# Projet 11 — Maintenance prédictive des équipements industriels

Projet pédagogique **Master Data & IA**, réalisé à partir du texte fourni : une chaîne IoT locale avec AI4I, Random Forest, MQTT QoS 1, API REST, WebSocket, InfluxDB, Grafana, ThingsBoard et Node-RED.

**Commencer par la démonstration Python ci-dessous.** Le modèle entraîné, les données, le notebook et les résultats expérimentaux sont inclus. Le statut exact des vérifications se trouve dans [VALIDATION.md](VALIDATION.md).

Pour transporter le projet sous forme d'images Docker, exécuter `EXPORTER-DOCKER.ps1` et suivre le [guide de livraison Docker](GUIDE-IMAGE-DOCKER.md). Le script construit l'image applicative et crée une archive contenant toutes les images nécessaires. Cette archive n'est pas préconstruite dans le ZIP source.

## 1. Ce que le système fait

- Rejoue les observations du jeu de test, absentes de l’entraînement.
- Calcule un score de défaillance avec le même pipeline de features à l’entraînement et en service.
- Accepte les mesures par HTTP ou par MQTT via le consumer.
- Conserve un journal SQLite transactionnel, déduplique par `message_id`, puis livre vers InfluxDB et ThingsBoard avec retries.
- Diffuse les nouveaux résultats sur WebSocket et affiche une interface de supervision.
- Déclenche une alarme au-dessus de 0,7, puis attend trois scores strictement inférieurs à 0,5 pour revenir à la normale.
- Synchronise les seuils depuis les attributs partagés de ThingsBoard et propose un sous-flux Node-RED réutilisable.
- Compare MQTT, HTTP et WebSocket sur un même collecteur de validation/écho, avec au moins 100 messages par protocole.

**Limite scientifique :** AI4I est synthétique. `Machine failure` décrit la défaillance à l’observation courante. Le projet ne prédit pas un nombre d’heures avant panne. Il ne fabrique pas de vibrations ou de courant absents du dataset. `SIM_AI4I` désigne un flux de rejeu, pas une véritable machine suivie dans le temps. `measured_at` reste nul ; `sent_at` et `received_at` décrivent le rejeu.

## 2. Démonstration Python sans Docker

Prérequis : Python **3.12**, accès Internet pour l’installation initiale. Commandes exécutées dans le dossier qui contient ce README.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn pdm.api:app --host 127.0.0.1 --port 8000
```

Dans un second terminal, depuis ce même dossier :

```powershell
.\.venv\Scripts\python.exe -m pdm.simulator --protocol http --count 200 --interval 0.5
```

Ouvrir [la supervision](http://localhost:8000) et [la documentation interactive API](http://localhost:8000/docs). Le stockage local et WebSocket fonctionnent dans ce mode. Arrêter avec `Ctrl+C`.

Sur Linux/macOS, remplacer `.\.venv\Scripts\python.exe` par `.venv/bin/python` et `py -3.12` par `python3.12`.

## 3. Déploiement principal avec Docker Compose

Prérequis : Docker Desktop démarré en mode conteneurs Linux. Prévoir plusieurs Go libres ; ThingsBoard demande davantage de mémoire que la démo Python.

```powershell
Copy-Item .env.example .env
docker compose up -d --build
docker compose --profile demo up -d simulator
```

Le premier `up` construit l’image Python ; le modèle fourni est utilisé. Le simulateur rejoue 2 000 lignes à une seconde d’intervalle, puis s’arrête. Pour recommencer : `docker compose --profile demo up -d --force-recreate simulator`.

| Service | Adresse | Identifiants locaux de démonstration |
|---|---|---|
| Supervision et API | http://localhost:8000 | Aucun |
| Grafana | http://localhost:3000 | admin / pdm-local-password |
| InfluxDB | http://localhost:8086 | admin / pdm-local-password |
| Node-RED | http://localhost:1880 | Aucun |
| Mosquitto | localhost:1883 | Anonyme, local uniquement |
| ThingsBoard (profil full) | http://localhost:8080 | tenant@thingsboard.org / tenant |

Grafana reçoit automatiquement sa source InfluxDB et le dashboard **Projet 11 — Maintenance industrielle**. Les ports publiés écoutent seulement sur `127.0.0.1`. Les valeurs de `.env.example` sont des identifiants de démonstration, à remplacer avant tout déploiement partagé.

Commandes utiles :

```powershell
docker compose ps
docker compose logs --tail 100 api consumer
docker compose stop
```

`stop` conserve les données. Ne pas supprimer les volumes si l’historique doit être conservé.

## 4. Ajouter ThingsBoard et ses alarmes

Lors de la **première installation seulement**, initialiser sa base :

```powershell
docker compose --profile full up -d postgres
docker compose --profile full run --rm -e INSTALL_TB=true -e LOAD_DEMO=true thingsboard
docker compose --profile full up -d thingsboard
```

Attendre l’ouverture de http://localhost:8080. Le chargement initial peut durer quelques minutes. Provisionner ensuite la chaîne dédiée, le profil, le device et les attributs :

```powershell
docker compose run --rm api python -m pdm.provision_thingsboard --url http://thingsboard:8080
```

Dans `.env`, remplacer `TB_ENABLED=0` par `TB_ENABLED=1`, puis :

```powershell
docker compose --profile full up -d api consumer thingsboard
```

Le fichier `runtime/tb_devices.json` contient le token du device et est exclu de Git. Dans ThingsBoard : **Entities → Devices → SIM_AI4I → Attributes → Shared attributes**, modifier `seuil_critique`, `seuil_retour` ou `clear_count`. Le service relit ces attributs environ toutes les cinq secondes lorsque les intégrations répondent. Un seuil invalide est refusé et l’ancienne configuration reste active.

La chaîne [alarm_rule_chain.json](thingsboard/alarm_rule_chain.json) sauvegarde la télémétrie, teste `panne_probable > seuil_critique`, crée l’alarme **Risque de défaillance / CRITICAL**, puis l’efface lorsque le service annonce le retour stabilisé. Elle est attachée au profil dédié ; la chaîne racine globale n’est pas remplacée. Le seuil évalué est celui utilisé lors de l’inférence et transporté dans la télémétrie, ce qui conserve le sens des messages retardés.

La reprovision remet les seuils à leurs valeurs initiales. Après la première installation, utiliser simplement `docker compose --profile full up -d` ; ne pas réinitialiser PostgreSQL.

## 5. Sous-flux Node-RED

Le service `node-red-init` copie le flux initial dans le volume `node-red-data` uniquement si aucun `flows.json` n'y existe. Node-RED peut ensuite sauvegarder ses déploiements dans ce volume. Le fichier de référence `node_red/flows.json` reste disponible pour les imports et n'est pas modifié par l'éditeur.

Si vous utilisez une ancienne configuration et obtenez `EBUSY ... rename '/data/flows.json.$$$' -> '/data/flows.json'`, appliquer la [procédure de correction](CORRECTION-NODE-RED.md).

Le flux est chargé dans Node-RED mais son onglet est désactivé par défaut pour éviter deux consumers actifs. Pour sa démonstration :

1. Arrêter le consumer Python : `docker compose stop consumer`.
2. Dans Node-RED, activer l’onglet **Maintenance AI4I — branche optionnelle** et déployer.
3. Relancer le simulateur. Observer les réponses de l’API dans Debug.
4. Le sous-flux **Valider une mesure AI4I** est réutilisable ; sa variable `API_URL` est configurable par instance.

Le prétraitement canonique et le calcul des features restent dans le pipeline Python. Le flux Node-RED assure un premier contrôle et l’appel REST. Sa branche de démonstration n’offre pas le retry persistant du consumer Python : celui-ci reste le chemin recommandé pour les essais de fiabilité. Désactiver l’onglet avant de redémarrer le consumer.

## 6. Réentraîner et comprendre le modèle

```powershell
.\.venv\Scripts\python.exe -m pdm.download
.\.venv\Scripts\python.exe -m pdm.train
```

Le script produit le modèle, les splits 60/20/20, les prédictions du test, les métriques et la figure d’évaluation. Il n’ajuste pas le modèle sur le test. Après réentraînement, redémarrer l’API ; avec Docker, reconstruire l’image.

Le notebook [entrainement_model.ipynb](notebooks/entrainement_model.ipynb) reprend exploration, déséquilibre, entraînement, métriques et limites. Pour l’ouvrir dans VS Code/Jupyter, installer `requirements-dev.txt` et sélectionner le Python de `.venv`.

Résultats : [rapport ML](reports/performance_ml.md), [métriques JSON](reports/ml_metrics.json), [figure](reports/ml_evaluation.png).

## 7. Comparaison des protocoles

Avec Mosquitto démarré par Docker et les dépendances Python installées :

```powershell
.\.venv\Scripts\python.exe -m pdm.benchmark --count 100 --broker-label "Mosquitto Docker local"
```

Le programme démarre temporairement un collecteur sur le port 8090, effectue une chauffe, réutilise les connexions puis mesure les aller-retours applicatifs avec `perf_counter_ns`. Chaque protocole reçoit les mêmes JSON et effectue la même validation. L’inférence ML et le stockage sont exclus pour isoler les transports.

Sorties : [comparaison](reports/comparaison_protocoles.md), `benchmark.json`, `benchmark_raw.jsonl`. Les volumes sont des **octets JSON applicatifs**, pas des octets sur le réseau. Pour le trafic total, réaliser une capture Wireshark sur les ports concernés, connexions et ACK compris. La livraison observée est calculée à partir des réponses valides uniques avant le timeout de cinq secondes.

Les résultats livrés indiquent explicitement le broker réellement utilisé. Les relancer avec Mosquitto produit les résultats propres à votre installation et remplace les fichiers précédents.

## 8. Tests

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m tests.run_integration
docker compose config --quiet
```

Le test d’intégration démarre des processus temporaires sur les ports 18000 et 18883, avec un broker **aMQTT de test**, puis vérifie MQTT → consumer → API → modèle réel → SQLite → WebSocket, la déduplication et l’historique. Il exécute aussi le benchmark de 100 messages par protocole. Il ferme ses processus à la fin et n’a pas besoin de Docker.

Pour la recette de la pile Docker, suivre [docs/recette.md](docs/recette.md). Les résultats non exécutés ne sont pas présentés comme validés.

## 9. Contrat API

| Route | Fonction |
|---|---|
| `POST /api/telemetry` | Valider, calculer, conserver ; réponse `duplicate` si déjà reçu |
| `GET /api/history?machine=SIM_AI4I&limit=100` | Historique du journal local |
| `GET /api/history?source=influx&machine=SIM_AI4I` | Historique InfluxDB sur les 30 derniers jours |
| `GET /api/config/SIM_AI4I` | Seuils actuellement utilisés |
| `PUT /api/config/SIM_AI4I` | Changer les seuils en mode local sans ThingsBoard |
| `GET /health` | Modèle chargé, intégrations, messages et livraisons en attente |
| `WS /ws` | Nouvelles prédictions ; heartbeat toutes les dix secondes sans mesure |

Le schéma complet est consultable dans `/docs`. Un même identifiant avec un autre contenu est rejeté en HTTP 409. Les timestamps sans fuseau, NaN, valeurs physiques négatives et champs inconnus sont refusés. La validation ne rejette pas arbitrairement une mesure élevée qui pourrait être une anomalie réelle.

## 10. Organisation

```text
pdm/                 modèle, entraînement, API, MQTT, intégrations, benchmark
pdm/static/          interface de supervision WebSocket
data/                dataset UCI, provenance SHA256, splits
models/              pipeline Random Forest sérialisé
notebooks/           analyse ML reproductible
tests/               tests unitaires/API et scénario réseau réel
grafana/             dashboard et provisioning
thingsboard/         chaîne de règles importable
node_red/            flux complet et sous-flux exporté
mosquitto/           configuration du broker
reports/             mesures réellement produites et rapports
docs/                architecture, recette, trame de soutenance, sources
runtime/             généré au lancement : journal, rejets, tokens locaux
```

Le projet vise une instance locale de démonstration avec **un worker API**. La diffusion WebSocket et le verrou d’ingestion sont locaux au processus ; plusieurs workers nécessiteraient un bus partagé et une coordination transactionnelle supplémentaire. La journalisation est sans purge automatique ; prévoir une politique de rétention pour un usage long.

## Sources

- [AI4I 2020, UCI — DOI 10.24432/C5HS5C](https://doi.org/10.24432/C5HS5C), S. Matzka, CC BY 4.0.
- [Paho MQTT Python](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html).
- [InfluxDB v2 et client Python](https://docs.influxdata.com/influxdb/v2/api-guide/client-libraries/python/).
- [ThingsBoard : installation Docker](https://thingsboard.io/docs/installation/docker/) et [nœud Create Alarm](https://thingsboard.io/docs/reference/rule-engine/nodes/action/create-alarm/).
- [Node-RED : sous-flux](https://nodered.org/docs/user-guide/editor/workspace/subflows).

Le PDF original mentionné dans le texte n’était pas joint ; la couverture des exigences repose sur le texte fourni.
