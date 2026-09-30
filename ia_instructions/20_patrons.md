# Patrons de conception — ragflow

> Renvoi vers le standard globals « Fichier d'instructions — Patrons de conception
> (agnostique) » (révision 2026-09-24) : docflow://doc/01a4dba0-2733-4824-ad4b-099e1293e664.
> À lire AVANT d'introduire une nouvelle abstraction (classe de base, protocole, fabrique,
> registre, stratégie…) — **devant un besoin**, jamais par principe.

Le document fait ~38 Ko : il n'est pas recopié ici (il y divergerait). Le lire dans docflow.

Deux règles avant tout le reste :

* **Le patron le plus simple qui résout le problème.** Pas le plus élégant, pas le plus général.
* **Aucun patron s'il n'y a pas de problème.** Une fonction qui suffit doit rester une fonction.
  Une abstraction posée « au cas où » ne se retire jamais.

Chaque patron y a sa section « Quand ne PAS l'utiliser » : la lire avant l'autre.
Catalogue local historique : `docs/patterns/` (antérieur au standard ; en cas d'écart, le standard fait foi).
