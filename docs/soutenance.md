# Trame de soutenance — 10 à 12 minutes

1. **Problème industriel (1 min)** : éviter des arrêts imprévus en analysant les conditions de fonctionnement. Distinguer corrective, préventive et prédictive.
2. **Données et limites (1 min)** : AI4I synthétique, 10 000 lignes, défaillances rares ; classification courante sans estimation d’horizon futur.
3. **Architecture (2 min)** : montrer le schéma à trois niveaux et expliquer MQTT, REST et WebSocket. Positionner InfluxDB, Grafana, ThingsBoard et Node-RED.
4. **ML (2 min)** : features réelles, exclusion des modes de panne, split 60/20/20, Random Forest, tableau de précision/rappel/F1 et effet du seuil 0,7. Présenter les chiffres réellement générés dans le rapport ML.
5. **Démonstration (3 min)** : rejeu des lignes de test, graphiques, alarme, modification de l’attribut partagé et retour à la normale. Montrer la déduplication et le sous-flux.
6. **Réseau (1 min)** : montrer le benchmark mesuré, définir le RTT et le périmètre des octets comptés, préciser le broker utilisé.
7. **Conclusion (1 min)** : chaîne intégrée, limites de validation, puis extension NASA C-MAPSS/RUL et validation par moteur.

Questions à préparer : pourquoi l’accuracy seule trompe-t-elle ? Pourquoi QoS1 impose-t-il de dédupliquer ? Pourquoi les températures ne suffisent-elles pas ? Quelle différence entre score et probabilité calibrée ? Pourquoi ne pas appliquer une moyenne glissante aux lignes arbitraires d’AI4I ? Quel comportement si InfluxDB est indisponible ?
