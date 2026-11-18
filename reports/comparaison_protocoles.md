# Comparaison expérimentale des protocoles

RTT applicatif validation/écho, connexions réutilisées, localhost, séquentiel, sans ML ni stockage.

Broker : Mosquitto Docker. Ordre : ['HTTP', 'MQTT', 'WebSocket'].

| Protocole | Émis | Reçus uniques | Livraison | Moyenne RTT ms | P95 ms | Octets requêtes / échos |
|---|---:|---:|---:|---:|---:|---:|
| HTTP | 100 | 100 | 100.0% | 2.29869585 | 4.848056 | 27140 / 27140 |
| MQTT | 100 | 100 | 100.0% | 90.63026966 | 95.32024 | 27140 / 27140 |
| WebSocket | 100 | 100 | 100.0% | 0.78009602 | 1.170443 | 27140 / 27140 |

Octets JSON applicatifs uniquement, hors en-têtes, handshakes, ACK, retransmissions et TCP/IP.

Le volume affiché ne permet pas de comparer le surcoût réseau. Une capture Wireshark est nécessaire pour cela. La livraison mesure les échos valides reçus avant timeout (5 s), sans perturbation réseau artificielle. Une exécution locale unique ne prouve pas la fiabilité en production.

MQTT comporte deux passages par le broker, HTTP et WebSocket un aller-retour direct. Répéter les essais pour étudier la variabilité. Les résultats ne représentent pas la latence de toute la chaîne ML.