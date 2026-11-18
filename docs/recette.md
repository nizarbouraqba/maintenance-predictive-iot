# Recette de la pile complète

Cette procédure sert à valider les services Docker sur l’installation cible. Elle ne constitue pas un compte rendu de tests déjà exécutés.

1. Démarrer la pile, puis vérifier `docker compose ps` et `/health` : modèle chargé, aucune erreur Influx, file de livraison se vidant.
2. Démarrer le simulateur et vérifier la croissance de `events`. Ouvrir la supervision : les points arrivent sans rechargement de page.
3. Comparer le dernier `message_id` de `/api/history` avec `/api/history?source=influx`. Vérifier le dashboard Grafana après quelques secondes.
4. Republier exactement un JSON avec le même identifiant. Le nombre d’événements uniques ne doit pas augmenter. Changer le couple en conservant l’identifiant : HTTP 409 attendu.
5. Arrêter temporairement InfluxDB. Publier quelques mesures : l’API continue à journaliser, `/health` devient dégradé et la file augmente. Redémarrer InfluxDB et vérifier que la file se vide et que les points sont visibles.
6. Provisionner ThingsBoard et activer `TB_ENABLED`. Vérifier que `SIM_AI4I` reçoit `panne_probable`, `status` et les seuils.
7. Pour une alarme reproductible, utiliser `reports/test_predictions.csv` pour retrouver une ligne de test avec `score > 0.7`, puis la rejouer avec un nouvel identifiant. Vérifier une alarme **CRITICAL / Risque de défaillance** dans ThingsBoard. Il s’agit d’un scénario sélectionné pour la démonstration, pas d’un échantillon pour calculer des performances.
8. Modifier le shared attribute `seuil_critique` à 0,9, en conservant `seuil_retour=0,5`. Vérifier `/api/config/SIM_AI4I` après synchronisation ; aucune reconstruction de l’image n’est nécessaire.
9. Rejouer trois observations à faible score avec des identifiants nouveaux : retour NORMAL dans le journal, puis alarme effacée dans ThingsBoard. Un doublon ne doit pas compter comme une nouvelle observation.
10. Arrêter le consumer Python, activer la branche Node-RED, et vérifier une prédiction dans Debug. Désactiver la branche après l’essai et redémarrer le consumer.
11. Exécuter le benchmark sur 100 messages au minimum. Conserver le JSON brut, le rapport, la version du broker et les conditions d’exécution.

Consigner les résultats, les erreurs éventuelles et les captures dans un compte rendu distinct. Ne pas remplacer un résultat manquant par les valeurs illustratives de l’énoncé.
