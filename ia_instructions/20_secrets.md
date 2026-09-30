# Secrets — ragflow

> Fragment généré depuis le standard globals « Fichier d'instructions — spécificités Secrets » (révision 2026-09-24).
> À lire AVANT de manipuler une clef API, un mot de passe, un jeton ou une clef privée (lecture, stockage, log, config).

Dans ragflow : les clefs des providers (embedding, rerank, LLM) sont **référencées** vers les
coffres **Harpocrate** (`backend/src/rag/secrets/`, SDK `backend/vendor/harpocrate-sdk`), jamais
stockées en clair ; les colonnes chiffrées passent par pgcrypto. Spec : `specs/06-secrets.md`,
`specs/11-harpocrate-indatabase.md`, `specs/vault.md`.

### Secrets

- Les secrets vivent dans le gestionnaire centralisé et sont **référencés**, jamais recopiés
- Aucun secret en clair : ni dans le dépôt, ni dans un argument de construction, ni dans une
  variable d'image, ni dans une couche, ni dans un log, ni dans une colonne
- Un secret ne se déballe qu'au **point d'injection**, jamais en amont « pour simplifier »
- Le type qui porte un secret ne doit pas s'afficher : sa représentation textuelle est masquée

### Secrets — portée : utilisateur ou système

Deux portées, et les confondre casse quelque chose à coup sûr :

- **Secret d'utilisateur** — résolu depuis l'espace personnel de la personne, avec un
  repli local. Il n'est lisible que **quand cette personne est là**.
- **Secret système** — résolu sans utilisateur, à partir d'une clef d'infrastructure.
  C'est le seul utilisable par un renouvellement automatique, une tâche de fond, une
  relance nocturne ou une réconciliation.

Choisir la portée d'après **qui déclenche la lecture**, jamais d'après qui possède la
valeur. Un secret d'utilisateur employé par un traitement de fond échoue la nuit, sans
personne pour le voir.

### Secrets — référence et nommage

- Ce qui est versionné ne porte que des **références** : un chemin, jamais une valeur.
  Les valeurs sont posées par l'administrateur ou l'utilisateur, hors du dépôt.
- Un chemin de coffre correspond à **une** variable d'environnement, selon une convention
  stable et lisible — `domaine/nom_de_la_clef` → `NOM_DE_LA_CLEF`. Une correspondance
  devinée au cas par cas devient impossible à auditer.
- Le secret n'est injecté qu'**au point d'usage**, dans l'environnement du processus qui
  en a besoin, jamais dans une image ni dans un fichier de configuration versionné.

### Secrets — deux identifiants d'un même fournisseur ne sont pas interchangeables

Un même fournisseur expose souvent plusieurs identifiants pour des usages différents :
un forfait et une facturation à l'usage, un point d'entrée compatible et un point
d'entrée natif, une clef de lecture et une clef d'écriture.

Ils ont le même air et ne fonctionnent pas au même endroit. Les **nommer distinctement**
et écrire à quoi chacun sert : l'erreur ne se voit pas à la configuration, elle se voit
au premier appel refusé — ou pire, à la première facture.

### Pièges connus

**Une variable d'environnement de construction reste dans l'image.** Effacer le fichier dans une couche ultérieure ne l'efface pas : la couche précédente est toujours là, et lisible par quiconque tire l'image.

**Un secret journalisé par accident l'est pour longtemps.** Il part vers l'agrégateur de logs, s'y réplique et s'y conserve selon une rétention qui n'est pas la vôtre. La rotation est alors la seule issue.

**Un secret dérivé d'un code utilisateur ne convient pas à ce qui tourne sans lui.** Un renouvellement automatique, une tâche de fond, une relance nocturne n'ont pas l'utilisateur sous la main : ces secrets-là doivent dépendre d'une clef système, pas d'un code personnel.

**Un secret collé dans une conversation est compromis.** Il finit dans une transcription, un historique de terminal, une sauvegarde. La bonne réponse est de le faire tourner, pas de l'effacer.

**Un identifiant invalide vaut pire que pas d'identifiant** sur certains services : présenter une clef périmée fait répondre « authentifie-toi » là où l'anonyme passait.

### Part de checklist

- [ ] `git diff` relu **sous l'angle des secrets** avant tout commit
- [ ] Aucune valeur en clair ajoutée dans un fichier versionné, un Dockerfile ou un compose
- [ ] Les nouveaux secrets sont référencés, pas recopiés
- [ ] Aucun log ajouté ne peut contenir une valeur secrète, même en cas d'erreur
- [ ] Les secrets utilisés sans utilisateur présent ne dépendent pas d'un code personnel
- [ ] La portée de chaque secret ajouté correspond à QUI déclenche sa lecture
- [ ] Les identifiants multiples d'un même fournisseur sont nommés distinctement
