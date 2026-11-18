# Correction du déploiement Node-RED : EBUSY

L'ancienne configuration montait directement `./node_red/flows.json` sur `/data/flows.json`. Lors d'un déploiement, Node-RED remplace ce dernier par renommage d'un fichier temporaire ; Docker interdit de remplacer ce point de montage.

La configuration corrigée monte uniquement le volume `node-red-data` sur `/data`. Un service d'initialisation copie le flux de référence dans ce volume si le fichier est absent, et conserve tout flux déjà sauvegardé. Ce stockage dans `/data` suit le principe décrit par la [documentation Docker de Node-RED](https://nodered.org/docs/getting-started/docker).

## Appliquer la correction

Si des modifications sont encore présentes dans l'éditeur mais non déployées, les exporter avant de recréer le conteneur : menu Node-RED → Exporter → tous les flux → télécharger le JSON.

Dans le dossier utilisé pour lancer Docker Compose, utiliser le `docker-compose.yml` corrigé et le nouveau fichier `node_red/init.js`. Si vous avez extrait le projet ailleurs, y recopier ces deux fichiers.

```powershell
docker compose config --quiet
docker compose stop node-red
docker compose run --rm --no-deps node-red-init
docker compose up -d --no-deps --force-recreate node-red
docker compose logs --tail 50 node-red
```

Cette séquence ne redémarre pas le consumer Python, n'efface pas le volume de données et ne nécessite pas de reconstruire l'image Python. Un simple `restart` ne suffit pas : la recréation applique les nouveaux montages.

Recharger http://localhost:1880, vérifier les flux chargés, puis réappliquer les changements non sauvegardés ou importer l'export si nécessaire. Activer le flux de démonstration après arrêt du consumer Python, puis cliquer sur Déployer. Le déploiement doit réussir sans EBUSY.

Pour vérifier la persistance, redémarrer uniquement Node-RED, recharger la page et vérifier que la modification déployée reste présente :

```powershell
docker compose restart node-red
```

## Vérifications de la correction

La configuration Compose a été validée et l'initialiseur testé localement (première copie puis préservation d'un fichier déjà modifié). La recréation du conteneur et le déploiement dans l'interface restent à effectuer sur l'installation cible : l'accès au moteur Docker depuis cette session renvoie « permission denied ».
