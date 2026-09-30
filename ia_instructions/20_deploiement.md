# Script de déploiement — ragflow

> Fragment généré depuis le standard globals « Fichier d'instructions — Script de déploiement
> sur machine de test (agnostique) » (révision 2026-09-24). À lire AVANT de modifier
> `dev-deploy.sh`, un fichier `docker-compose*.yml`, un `Dockerfile` ou `deploy/`.

Le standard complet fait foi : docflow://doc/b7c55859-56e1-47f6-a319-c9494b125cbd. Les pannes qui
justifient chaque garde : docflow://doc/57f4967c-1595-40ae-8e83-853bfa090804 — **les lire avant de
retirer une garde**.

## Ce que `dev-deploy.sh` doit faire, dans l'ordre

0. Survivre à la perte de la session : ignorer SIGHUP, tout journaliser dans un fichier.
1. Vérifier les prérequis, et donner la commande d'installation dans le message d'erreur.
2. Se mettre à jour depuis le dépôt, puis **se ré-exécuter** dans sa version récupérée.
   Dépôt privé : mode bootstrap de deploy key générée SUR l'hôte.
3. Initialiser l'état de façon idempotente (jamais régénérer ce qui est durable).
4. Compléter la configuration sans écraser l'existante.
5. Construire, arrêter (`--remove-orphans`), relancer — la construction vaut validation.
6. Détecter les conflits de ports APRÈS l'arrêt, jamais avant.
7. Attendre un conteneur réellement exécutable avant de migrer.
8. Vérifier que le schéma est à jour, pas seulement que la commande a réussi.
9. Contrôle de santé final, avec plafond de temps, sur le bon port.
10. Purger cache de construction et images détaggées, au plus une fois par semaine, sans
    jamais faire échouer le déploiement.
11. Isoler les modes destructifs (`--reset`) derrière un drapeau explicite.

Spécificité ragflow : les migrations (base de config et bases de workspace) sont jouées par le
**lifespan du backend** avant qu'il ne serve ; un schéma en échec empêche donc `/health` de
répondre. Les étapes 7 et 8 se vérifient par le contrôle de santé et les logs de démarrage.

## ⚠ Écarts constatés au 2026-09-26 (à traiter en tickets, pas au passage)

`dev-deploy.sh` ne couvre pas encore : l'étape 0 (ni SIGHUP ignoré, ni fichier de journal),
l'étape 2 (pas de ré-exécution après mise à jour, pas de bootstrap de deploy key), l'étape 10
(purge hebdomadaire — ticket backlog `cef4eff3` existant).

## Part de checklist

- [ ] Le script se relance sans danger après un échec partiel
- [ ] Il échoue **bruyamment** quand la migration n'a pas atteint la dernière version
- [ ] Il n'écrase aucun secret ni aucun élément cryptographique existant
- [ ] Les sondes de port se font après l'arrêt de la stack, pas avant
- [ ] L'image est construite depuis la copie fraîche du dépôt, jamais réutilisée d'ailleurs
- [ ] Le déploiement reste diagnosticable même si la session est tombée
- [ ] La purge d'espace disque est bornée en fréquence, limitée au cache et aux images détaggées, et ne peut pas faire échouer le déploiement
- [ ] Sur dépôt privé, un mode bootstrap génère la deploy key **sur l'hôte** (clé privée jamais collée), affiche la clé publique en dernier, et se met en pause pour l'enregistrer avant de tirer
