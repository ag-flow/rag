# Observabilité et logs — ragflow

> Fragment généré depuis le standard globals « Fichier d'instructions — Observabilité et logs (agnostique) » (révision 2026-09-24).
> À lire AVANT d'ajouter ou de modifier une ligne de journal.

Collecte : Grafana Alloy (`deploy/alloy-config.alloy`) lit le flux des conteneurs Docker et
pousse vers Loki ; interrogation par `devpod__logs_query` (label `host="rag-dev"` pour la
machine de dev). Événements clés et requêtes utiles : article docflow `ragflow` « 14 —
Observabilité ». Forme Python : `structlog.get_logger(__name__)` (voir `10_python.md`).

### Journalisation

- **Journalisation structurée**, jamais d'écriture directe sur la sortie standard. Un
  message libre ne se filtre pas et ne s'agrège pas.
- **Aucun secret dans un log**, y compris dans un chemin d'erreur. Ce qui part vers
  l'agrégateur s'y réplique et s'y conserve selon une rétention qui n'est pas la nôtre :
  un secret journalisé se règle par rotation, pas par effacement.
- **Une charge utile non authentifiée ne se journalise pas telle quelle** : la recopier
  revient à écrire dans nos journaux ce qu'un inconnu a envoyé.
- Journaliser les **décisions**, pas les étapes : ce qui a été refusé et pourquoi, ce qui a
  été appliqué et à quoi. Une trace par étape noie la seule ligne qui comptait.
- Les journaux sont centralisés et consultables : ils font partie du diagnostic, pas d'un
  fichier local qu'on ira chercher en dernier recours.

### Pièges connus

**Le silence ressemble à un système en bon ordre.** Un flux qui ne parvient plus ne produit aucune erreur — il produit rien. Ce qui doit alerter, c'est l'absence de message attendu, et ça se surveille explicitement.

**Une clef réservée du journaliseur casse à l'exécution, pas au lint.** La plupart des bibliothèques structurées réservent un nom pour le message lui-même ; le passer en argument nommé lève une erreur en production et jamais pendant les vérifications.

**Un journal n'est pas un rattrapage.** Écrire « échec » au niveau erreur ne répare rien et n'est lu par personne au bon moment. Si l'échec doit être retenté, il faut un état persistant qui le porte, pas une ligne de journal.

**La collecte se fait sur le flux du conteneur, pas sur un fichier.** Écrire dans un fichier à l'intérieur du conteneur produit des journaux que personne ne collecte et qui disparaissent au redémarrage.

### Part de checklist

- [ ] Aucune écriture directe sur la sortie standard ajoutée
- [ ] Aucun log ajouté ne peut contenir un secret, même en cas d'erreur
- [ ] Les messages ajoutés portent une décision, pas une étape
- [ ] Aucune clef réservée du journaliseur employée comme nom d'argument
