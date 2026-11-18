# État de validation — 18 novembre 2026

## Vérifications réalisées

| Élément | Résultat et preuve |
|---|---|
| Dataset UCI | Téléchargé ; 10 000 lignes, 339 défaillances ; SHA256 dans `data/provenance.json` |
| Modèle Random Forest | Entraîné sur 6 000 lignes ; validation 2 000 ; test 2 000 |
| Notebook | Quatre cellules de code exécutées ; sorties sauvegardées ; validation nbformat réussie ; aucune cellule en erreur |
| Tests automatiques | **15 tests réussis** ; `reports/tests.xml` |
| Dépendances | `pip check` réussi ; SciPy fixé à 1.15.2 après blocage d’import constaté avec 1.18.1 sur cet environnement Windows |
| Intégration réseau | **Réussie** : aMQTT QoS1 → consumer → HTTP → vrai modèle → SQLite → WebSocket ; cinq messages uniques et vérification des doublons |
| Benchmark | **100 messages reçus sur 100 pour chaque protocole** ; HTTP, MQTT et WebSocket ; données brutes conservées |
| Interface navigateur | Ouverte sur serveur local ; connexion WebSocket active ; 100 mesures affichées, courbe et tableau actualisés |
| Docker Compose | `docker compose config --quiet` réussi |
| Exports | JSON Grafana valide ; sous-flux Node-RED testé en JavaScript ; scripts ThingsBoard compilés et comparaison stricte du seuil contrôlée |

Le test d’intégration final s’est terminé avec le code de sortie 0. Son rapport est `reports/integration.json`. Le test de transport utilise un broker **aMQTT 0.11.3 sous Windows**, et non Mosquitto Docker.

## Résultats ML sur le test indépendant

| Politique | Précision | Rappel | F1 |
|---|---:|---:|---:|
| Seuil 0,5 | 90,4 % | 69,1 % | 0,783 |
| Seuil métier 0,7 | 97,1 % | 50,0 % | 0,660 |
| Seuil 0,39 choisi sur validation | 85,5 % | 77,9 % | 0,815 |

Average Precision : **0,8497** ; ROC-AUC : **0,9596** ; Brier : **0,01162**. Le seuil 0,7 reste la configuration livrée. Un seuil critique inférieur à 0,5 nécessiterait également d’abaisser le seuil de retour pour respecter l’hystérésis.

## Résultats réseau locaux

| Protocole | RTT moyen | P95 | Livraison observée |
|---|---:|---:|---:|
| HTTP | 1,506 ms | 2,411 ms | 100 / 100 |
| MQTT | 2,060 ms | 2,674 ms | 100 / 100 |
| WebSocket | 0,453 ms | 0,565 ms | 100 / 100 |

Collecteur validation/écho sans ML ni stockage ; connexions réutilisées ; loopback ; un essai séquentiel par protocole. Ces valeurs ne démontrent aucune supériorité générale. Le volume compté est celui des JSON : 27 140 octets de requêtes et autant d’échos par protocole, hors surcoût réseau.

## Intégrations restant à valider sur la pile Docker

Le moteur Docker n’était pas démarré dans l’environnement de réalisation. Les services **Mosquitto Docker, InfluxDB, Grafana, ThingsBoard et Node-RED** n’ont donc pas été exécutés ensemble. Leurs configurations, clients, provisioning et procédure de recette sont livrés, mais leur fonctionnement intégré n’est pas présenté comme testé.

En particulier, la création réelle d’une alarme dans ThingsBoard, la persistance effective dans InfluxDB, les courbes Grafana et le déploiement du sous-flux dans Node-RED restent à vérifier via `docs/recette.md`. Les tests des adaptateurs ThingsBoard utilisent des réponses HTTP simulées ; ils ne remplacent pas cette recette.
