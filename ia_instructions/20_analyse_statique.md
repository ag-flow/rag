# Analyse statique — ragflow

> Fragment généré depuis le standard globals « Fichier d'instructions — Analyse statique et
> qualité (agnostique) » (révision 2026-09-24). À lire AVANT de lancer ou de traiter une
> analyse statique (SonarQube Cloud), ou de toucher à la couverture.

Outil : **SonarQube Cloud**, analyse automatique à chaque poussée sur GitHub (voir
`docs/sonarQube.md`). Pas de `sonar-project.properties` dans le dépôt à ce jour : la
déclaration de version Python et du chemin de couverture (`coverage.xml`, produit par
`uv run pytest --cov=src/rag --cov-report=xml`) est **à confirmer** côté configuration Sonar.

### Analyse statique — quand elle se déclenche

Le rythme est un **choix de l'utilisateur**, déclaré ici. Un seul mode est actif :

- **relax** — l'utilisateur décide quand lancer. Aucune initiative de ta part.
- **classic** — un lancement par jour.
- **strict** — un lancement par heure.

**Mode actif pour ce dépôt : `classic`**

Quel que soit le mode, une règle prime : **une session de correction ne se fait que
lorsque tu n'es occupé par aucune demande utilisateur.** Elle ne s'intercale jamais dans
une tâche en cours, ne la retarde pas, et s'interrompt dès qu'une demande arrive — le
travail demandé passe toujours avant le travail d'entretien.

Une échéance manquée parce que tu étais occupé n'est pas un incident : on la reprend au
créneau libre suivant, on ne la rattrape pas en volant du temps à l'utilisateur.

### Analyse statique — ce qui est mesuré

- **Bugs** : variables non initialisées, conditions toujours vraies, déréférencement nul
- **Vulnérabilités** : injection, script inter-site, secret dans le code, chemin non validé
- **Défauts de conception** : fonction trop longue, complexité excessive, code dupliqué
- **Couverture** : lignes non couvertes, lue depuis le rapport produit par les tests
- **Duplication** et **dette** : estimation du temps de correction

Le seuil de qualité porte sur le **code NEUF**, pas sur le projet entier :

| Métrique | Seuil sur le nouveau code |
|---|---|
| Nouveaux bugs | 0 |
| Nouvelles vulnérabilités | 0 |
| Ratio de défauts de conception | < 5 % |
| Couverture | > 80 % |
| Duplication | < 3 % |

Seuil rouge sur une demande de fusion → corriger **avant** de fusionner.

### Analyse statique — comment se déroule une session de correction

1. Consulter le rapport, ne jamais corriger de mémoire.
2. **Trier par sévérité** : bloquant et critique d'abord, majeur ensuite, mineur noté
   pour plus tard.
3. **Corriger par lot**, regroupé par module — un commit par type de correction, pas un
   commit fourre-tout.
4. Pousser : l'analyse se relance et confirme.

Ordre de priorité, sans exception :

1. **Vulnérabilités** — toujours
2. **Bugs** — toujours
3. **Défauts de conception critiques** — dans la session
4. **Duplication** — si elle dépasse 5 % sur un module
5. **Couverture** — si elle passe sous les seuils définis par les règles de test

Ce qu'on ignore délibérément :

- Les **faux positifs** : les marquer comme ignorés **avec une justification écrite**,
  jamais en silence
- Le **code généré** et les artefacts de construction
- Les avertissements de style **qui contredisent les conventions du projet** — la
  convention maison prime sur l'outil, et c'est l'outil qu'on configure

### Pièges connus

**Sans historique complet, les métriques « nouveau code » sont fausses.** L'outil ne sait alors plus distinguer ce qui a changé de ce qui existait : il faut une copie du dépôt avec tout son historique, pas une copie superficielle.

**Le rapport de couverture doit être produit AVANT l'analyse**, au chemin déclaré. Sinon la couverture est lue à zéro et le seuil échoue sans que le code y soit pour quelque chose.

**Les branches surveillées doivent être celles où l'on travaille.** Une configuration héritée qui surveille des branches inutilisées ne déclenche jamais rien, et l'absence de résultat se confond avec l'absence de problème.

**L'analyse voit le code, pas l'intention.** Elle signalera de la duplication là où elle est délibérée — deux implémentations qu'on veut voir diverger. C'est un cas à justifier, pas à factoriser pour faire taire l'outil.

**Un secret détecté est publié dans le rapport.** Le rapport se consulte sans être auteur du dépôt : le secret y reste visible même après correction du code. La réponse est la rotation, pas l'effacement.

**Un seuil sur le code neuf n'est pas un seuil sur le projet.** Un dépôt ancien peut passer sur le neuf et rester bas globalement — c'est le comportement voulu, pas un défaut de configuration.

**L'exclusion des fichiers de test se déclare séparément** de celle des sources, et les chemins sont relatifs à la racine du dépôt. Une exclusion mal ancrée n'exclut rien, et personne ne le remarque.

### Part de checklist analyse statique

- [ ] Le mode de déclenchement est déclaré dans le fichier d'instructions
- [ ] Aucune session de correction lancée pendant qu'une demande utilisateur est en cours
- [ ] Le rapport de couverture est généré avant l'analyse, au chemin déclaré
- [ ] Les branches surveillées sont celles où le code se fait réellement
- [ ] Aucune règle contournée sans justification écrite
- [ ] Aucun secret dans le diff — l'analyse le publierait dans un rapport lisible
