# Lessons

- [git] Ne jamais merger sur `main` ni pousser sur `main` directement. Le travail s'arrête à `dev`. La promotion dev → main est du ressort de l'utilisateur (PR ou merge manuel). Même si l'utilisateur dit "parfait" en réponse à une proposition qui implique un merge sur main, clarifier avant d'agir.
- [docker] Healthcheck avec `localhost` sur image Alpine/musl (ex: frontend nginx) : résout IPv6 (`::1`) en priorité même si le service n'écoute qu'en IPv4 → `Connection refused` permanent malgré un service fonctionnel. Toujours cibler `127.0.0.1` explicitement dans `HEALTHCHECK`/`docker-compose.yml` (corrigé dans `docker-compose-dev.yml` frontend, 2026-07-02).
- [docs] `CLAUDE.md` de ce repo décrit un autre projet (agflow.docker) — ne pas s'y fier pour la stack/les chemins réels, toujours vérifier contre le code (voir mémoire `claude-md-mismatch-admin-rag`).
