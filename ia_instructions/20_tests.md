# Tests — ragflow

> Fragment généré depuis le standard globals « Fichier d'instructions — Tests (agnostique) »
> (révision 2026-09-25). À lire AVANT d'écrire ou de modifier un test. Forme concrète
> (pytest, Vitest, commandes) : `ia_instructions/10_python.md`, `ia_instructions/10_typescript.md`.
> Seuils de couverture par zone de ragflow : **à définir** — `docs/tests-python.md` décrit
> les zones d'un autre projet (`Agents/`, `hitl/`) et ne s'applique pas tel quel.

### Tests — philosophie

La couverture est un **outil pour trouver ce qui n'est pas testé**, jamais un score à
maximiser. On teste pour avoir confiance en modifiant, pas pour cocher une case.

Un bon test prouve un comportement, **casse quand ce comportement change**, s'exécute
vite et se lit sans effort. Un test qui ne casse jamais ne prouve rien.

**Une tâche est finie quand les tests passent** — voir « Définition de terminé » dans le
fichier d'instructions.

### Tests — ce qui est exigé

- **Règle du delta** : le code ajouté ou modifié est couvert à 90 % sur les lignes qui ont
  bougé. On ne juge pas le projet entier, on juge le changement.
- **Seuils par zone**, pas un seuil global : le cœur partagé et la logique métier critique
  se tiennent haut, l'interface d'administration bas. Un seuil unique fait mentir la moyenne.
- En dessous de 50 % sur une zone → alerte. **Au-dessus de 90 % → probablement du test
  inutile**, écrit pour le score.
- Les **cas de rejet sécurité** sont des tests, jamais des revues manuelles : traversée de
  chemin, isolation entre comptes, jeton rejoué, entrée malformée.

### Tests — ce qu'on teste obligatoirement

Par NATURE de l'unité, pas par langage :

- **Accès aux données** : chaque lecture et écriture, avec une doublure — dont le cas
  « rien trouvé », qui est celui qu'on oublie.
- **Accès aux fichiers** : avec des fichiers temporaires, jamais le dépôt lui-même.
- **Orchestration** : un test de bout en bout du flux, plus les branches qui s'arrêtent.
- **Points d'entrée outillés** (routes, commandes, tools) : le cas nominal ET les erreurs.
- **Récursivité** : profondeur 0 (arrêt immédiat), profondeur 1, profondeur maximale
  (l'erreur de profondeur doit être rendue, jamais un débordement de pile), et données
  manquantes ou circulaires.

### Tests — ce qu'on ne teste PAS

- Les journaux : vérifier qu'un message est écrit n'apporte rien.
- Les imports différés et le code d'infrastructure.
- Le code de glue qui ne fait que passer des paramètres sans décider.
- Le contenu des gabarits et des textes.
- La configuration statique : constantes, tables de correspondance.

### Tests — quand

- **Nouveau module** : tests écrits avant ou avec le code. Pas de fusion sans tests.
- **Correction de bug** : d'abord un test qui REPRODUIT le bug et qui ÉCHOUE ; puis la
  correction ; le test reste pour toujours.
- **Refactorisation** : les tests existants passent **sans modification**. Si un test casse,
  ce n'est pas une refactorisation — c'est un changement de comportement.
- **Modification d'un module** : lancer ses tests AVANT de toucher au code. S'ils échouent
  déjà, les réparer d'abord — sinon on ne saura pas ce qu'on a cassé.

### Tests — nommage et structure

Nom : `test_<ce_qui_est_testé>_<condition>_<résultat_attendu>`. Un nom qui ne dit pas le
résultat attendu oblige à lire le corps pour savoir ce qui est vérifié.

Un fichier de test par module ; les fixtures partagées dans le fichier de conftest du
cadre de test.

### Tests — où et comment les exécuter

**Avant de valider un sujet, évalue où le test sera le plus révélateur — et privilégie
les machines de test.** C'est là que le livrable tourne dans sa configuration réelle, avec
ses journaux et ses métriques : c'est là qu'un défaut a le plus de chances de se montrer.
Un test local qui passe ne dispense pas de la validation sur une machine de test dès que
celle-ci peut révéler davantage.

Leur Docker (voir « Machines de test » dans le fichier d'instructions) sert aussi bien à
lancer les conteneurs livrés qu'à exécuter les tests unitaires, les tests ATDD ou tout
autre type de test que tu juges nécessaire.

- Le **service testé** est livré par la procédure (« Livrer sur une machine de test ») et
  n'est jamais simulé par un conteneur lancé à la main.
- Les **outils de test** — runner, base jetable, doublure, outil de mesure — tournent
  librement dans Docker. Une base jetable par exécution, jamais partagée.
- Pour éprouver une page réelle, utiliser le `browserless-chromium` de la machine.
- Devant un échec, lire **les vrais logs du service** dans la stack centralisée : on ne
  devine pas depuis un message d'erreur tronqué, on ne réinvente pas une instrumentation
  locale.

Script de déploiement à écrire ou corriger : standard globals « Script de déploiement sur
machine de test » (docflow://doc/b7c55859-56e1-47f6-a319-c9494b125cbd) — voir
`ia_instructions/20_deploiement.md`.

### Pièges connus

**Le script de déploiement se met à jour lui-même depuis git avant de déployer.** Le réseau et l'accès au dépôt sont donc un prérequis, pas un confort : il n'existe pas de mode « déploie ce qui est déjà là ». Un dépôt public reste par ailleurs soumis à un quota de requêtes anonymes par adresse IP — franchi, il fait répondre « authentifie-toi » sur un dépôt pourtant ouvert, ce qui ressemble à un problème de droits alors que c'en est un de débit.

**Un test local vert n'est pas une validation.** Il réussit grâce à un cache, à un fichier non versionné, à une configuration qui n'est pas celle de la cible. La machine de test part d'une copie fraîche du dépôt : ce qui manque s'y voit.

**Un test écrit après le code n'a pas prouvé qu'il mord.** La seule preuve est de l'avoir vu rouge. À défaut, casser volontairement le code et vérifier qu'il échoue — sinon on garde un test aveugle qui donne une fausse assurance.

**Un jeu d'essai qui porte déjà la valeur attendue rend le test inutile.** Si la doublure a un champ vide et que le test vérifie qu'il est vide, il reste vert même quand le code recopie la valeur. Choisir des valeurs **discriminantes**.

**Comparer un nombre d'échecs ne prouve pas l'absence de régression.** Deux suites peuvent afficher le même total avec des échecs différents. Comparer l'**ensemble** des tests en échec, pas leur compte.

**Une suite partagée entre deux exécutions concurrentes se détruit elle-même.** Deux campagnes sur la même base jetable effacent mutuellement leurs tables : une base par exécution.

**Un test qui dépend de l'horloge ou de l'aléatoire échoue un jour sur cent**, toujours chez quelqu'un d'autre. Injecter l'instant et la graine.

### Part de checklist tests

- [ ] Les tests passent — la tâche n'est pas finie avant
- [ ] La validation a eu lieu là où le test est le plus révélateur — sur une machine de test dès qu'elle peut révéler davantage que le local
- [ ] Le code ajouté ou modifié est couvert à 90 % sur les lignes changées
- [ ] Chaque correction de bug est accompagnée du test qui le reproduisait
- [ ] Les tests écrits après le code ont été éprouvés en cassant le code
- [ ] Les cas de rejet sécurité sont des tests, pas des intentions
- [ ] La suite complète passe, et l'ensemble des échecs préexistants est inchangé
- [ ] Tout diagnostic s'appuie sur les journaux réels du service, pas sur une supposition
- [ ] La machine derrière l'alias SSH a été vérifiée avant d'y déployer ou d'y conclure
- [ ] Le commit est poussé sur `dev` AVANT le déploiement
- [ ] Le déploiement est passé par `dev-deploy.sh`, sans construction manuelle
