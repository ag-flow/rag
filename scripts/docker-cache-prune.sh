#!/usr/bin/env bash
#
# docker-cache-prune.sh — purge bornée du cache Docker, appelée par dev-deploy.sh.
#
# Usage : scripts/docker-cache-prune.sh <fichier_témoin> [intervalle_jours]
#
# Chaque déploiement reconstruit les images et retague :dev/:latest : l'ancienne
# image devient détaggée et le cache BuildKit grossit sans fin, jusqu'à remplir
# le disque de la machine de test. On purge donc le cache de construction et
# les images détaggées, au plus une fois par intervalle (7 jours par défaut :
# purger à chaque déploiement rendrait chaque build froid).
#
# Interdits volontaires : ni `docker system prune -a` (supprimerait les images
# tierces tirées du registre et les conteneurs arrêtés d'autres stacks), ni
# `docker volume prune` (supprimerait des données, dont la base Postgres).
#
# Ce script sort TOUJOURS en 0 : une purge ratée ne doit jamais faire échouer
# un déploiement par ailleurs réussi. L'échec est signalé, et le témoin n'est
# pas rafraîchi pour que le déploiement suivant retente.

set -uo pipefail

STAMP_FILE="${1:?usage: $0 <fichier_témoin> [intervalle_jours]}"
INTERVAL_DAYS="${2:-7}"

if ! [[ "$INTERVAL_DAYS" =~ ^[1-9][0-9]*$ ]]; then
  echo "⚠  Purge du cache Docker : intervalle invalide '${INTERVAL_DAYS}' — purge sautée." >&2
  exit 0
fi

# find -mtime -N : modifié il y a moins de N jours entiers.
if [ -f "$STAMP_FILE" ] && [ -n "$(find "$STAMP_FILE" -mtime "-${INTERVAL_DAYS}" 2>/dev/null)" ]; then
  echo "ℹ  Purge du cache Docker : dernière purge il y a moins de ${INTERVAL_DAYS} jours — sautée."
  exit 0
fi

# Exécute une commande de purge et affiche la ligne de bilan d'espace récupéré
# (dernière ligne de la sortie Docker : « Total: … » ou « Total reclaimed space: … »).
run_prune() {
  local label="$1"
  shift
  local output
  if ! output="$("$@" 2>&1)"; then
    echo "⚠  Purge du cache Docker : '${label}' a échoué — ${output##*$'\n'}" >&2
    return 1
  fi
  echo "      ${label} : ${output##*$'\n'}"
}

echo "Purge du cache Docker (au plus tous les ${INTERVAL_DAYS} jours)..."
PRUNE_OK=1
run_prune "cache de construction" docker builder prune -a -f || PRUNE_OK=0
run_prune "images détaggées" docker image prune -f || PRUNE_OK=0

if [ "$PRUNE_OK" = "1" ]; then
  touch "$STAMP_FILE" 2>/dev/null \
    || echo "⚠  Purge du cache Docker : témoin ${STAMP_FILE} non écrit — la purge sera retentée au prochain déploiement." >&2
  echo "✓ Purge du cache Docker terminée."
else
  echo "⚠  Purge du cache Docker incomplète — retentée au prochain déploiement (déploiement non affecté)." >&2
fi
exit 0
