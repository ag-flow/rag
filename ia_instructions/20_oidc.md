# Authentification OIDC — ragflow

> Fragment généré depuis le standard globals « Fichier d'instructions — spécificités Authentification OIDC » (révision 2026-09-24).
> À lire AVANT de toucher à l'authentification (OIDC, compte local, clefs API, dépendances d'autorisation).

Dans ragflow : Keycloak, royaume `yoops` ; authlib ; compte local en repli pilotable depuis
l'IHM. Dépendances d'autorisation dans `backend/src/rag/auth/`. Spec : `specs/10-auth.md`.

**⚠ Écart constaté — à trancher par l'architecte** : le secret client OIDC est aujourd'hui
saisi dans l'IHM et persisté dans `admin.env` (fichier non versionné, relu à chaud), pas
résolu depuis le gestionnaire de secrets comme l'exige le bloc ci-dessous. Ne pas le déplacer
sans décision.

### Authentification

- Fournisseur d'identité de la maison, royaume commun, **client dédié au projet**
- Rôles portés par le fournisseur, jamais recopiés en dur dans le code
- Le secret client vient du gestionnaire de secrets, jamais d'un fichier versionné
- **Fail closed** : une route sans autorisation explicite est refusée, pas ouverte

### Pièges connus

**Le login se dérive, il ne se lit pas.** Un identifiant utilisateur construit depuis une revendication brute (courriel, nom d'affichage) change quand l'utilisateur change d'adresse, et deux personnes peuvent produire le même. Dériver un login normalisé, le valider par regex, et le figer.

**Une revendication de rôle absente n'est pas un rôle vide** : c'est un jeton qu'on n'a pas su lire. Traiter les deux pareil ouvre l'accès à qui présente un jeton mal formé.

**Le domaine du cookie de session décide de ce qui reste connecté.** Un sous-domaine oublié déconnecte l'utilisateur à chaque navigation, et un domaine trop large expose la session à des services voisins.

**Une redirection après connexion est une entrée utilisateur.** Non validée, elle envoie l'utilisateur authentifié vers un site tiers.

### Part de checklist

- [ ] Aucune route sensible atteignable sans autorisation, et le cas est **testé**
- [ ] Aucun rôle codé en dur qui doublerait ce que porte le fournisseur
- [ ] Le secret client n'apparaît ni dans le dépôt, ni dans un log, ni dans une image
- [ ] Les cibles de redirection après connexion sont validées contre une liste connue
