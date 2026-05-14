#!/usr/bin/env bash
#
# dev-deploy.sh — Déploiement DEV du service ag-flow.rag sur LXC 303.
#
# Mode UNIQUE de livraison test (cf. CLAUDE.md § Livraison test) :
#   1. Travail commité + pushé sur la branche `dev`
#   2. Sur la machine de test : `cd /opt/rag && ./dev-deploy.sh`
#
# Le script :
#   1. Vérifie les pré-requis (.git, .env, docker compose)
#   2. Pull la branche `dev` (ou la branche passée en argument)
#   3. Build les images locales rag-backend + rag-frontend
#   4. Down + pull deps registry + up de la stack docker-compose.dev.yml
#
# Init initiale du répertoire /opt/rag : faite manuellement par l'utilisateur
# d'après `Install-dev.md`. Ce script n'est PAS responsable du premier clone.

set -euo pipefail

# Branche cible : argument positionnel optionnel. Par défaut `dev` —
# c'est la branche de livraison test imposée, ne pas changer sauf debug.
TARGET_BRANCH="${1:-dev}"
COMPOSE_FILE="docker-compose.dev.yml"

# ─── 0) Pré-requis ───────────────────────────────────────────────────────────

if ! command -v docker >/dev/null 2>&1; then
  echo "✗ Docker absent — le LXC doit avoir Docker installé (cf. Install-dev.md)." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "✗ Docker Compose v2 manquant (commande 'docker compose' absente)." >&2
  exit 1
fi

if [ ! -d ".git" ]; then
  echo "✗ Pas un repo git. Ce script doit tourner depuis /opt/rag (cf. Install-dev.md)." >&2
  exit 1
fi

if [ ! -f ".env" ]; then
  echo "✗ .env absent. Suivre Install-dev.md § Étape 3 pour créer le fichier." >&2
  exit 1
fi

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "✗ $COMPOSE_FILE absent à la racine du repo." >&2
  exit 1
fi

# ─── 1) Pull branche dev ─────────────────────────────────────────────────────

echo "[1/4] Fetch + switch + pull branche ${TARGET_BRANCH}..."
git fetch origin
git checkout "$TARGET_BRANCH"
git pull --ff-only origin "$TARGET_BRANCH"

# ─── 2) Build images locales ─────────────────────────────────────────────────

# Build conditionnel : on construit uniquement les répertoires existants.
# Tant que l'implémentation n'a pas démarré, backend/ ou frontend/ peuvent être absents
# — dans ce cas le service correspondant ne tournera pas, et compose le signalera.

if [ -d "backend" ] && [ -f "backend/Dockerfile" ]; then
  echo "[2/4] Build rag-backend:latest..."
  docker build -t rag-backend:latest backend/
else
  echo "[2/4] backend/Dockerfile absent — skip build backend (phase d'amorçage)."
fi

if [ -d "frontend" ] && [ -f "frontend/Dockerfile" ]; then
  echo "      Build rag-frontend:latest..."
  docker build -t rag-frontend:latest frontend/
else
  echo "      frontend/Dockerfile absent — skip build frontend (phase d'amorçage)."
fi

# ─── 3) Down + pull registry ─────────────────────────────────────────────────

echo "[3/4] Arrêt de la stack (incl. orphelins)..."
docker compose -f "$COMPOSE_FILE" down --remove-orphans || true

echo "      Pull images registry (postgres, caddy, pgweb)..."
docker compose -f "$COMPOSE_FILE" pull postgres caddy pgweb || true

# ─── 4) Up ───────────────────────────────────────────────────────────────────

echo "[4/4] Démarrage de la stack..."
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans --pull never

echo
echo "✓ Déploiement DEV terminé. Services :"
docker compose -f "$COMPOSE_FILE" ps
echo
echo "Logs en direct :"
echo "  docker compose -f ${COMPOSE_FILE} logs -f backend"
echo "  docker compose -f ${COMPOSE_FILE} logs -f frontend"
echo

# ─── Affichage final : URLs d'accès ──────────────────────────────────────────

detect_eth0_ip() {
  ip -4 -o addr show dev eth0 2>/dev/null \
    | awk '{print $4}' | cut -d/ -f1 | head -1
}

ETH0_IP="$(detect_eth0_ip)"
HOST="${ETH0_IP:-localhost}"

cat <<EOF
═════════════════════════════════════════════════════════════════
  UI / API   →  http://${HOST}        (via Caddy)
  API direct →  http://${HOST}:8000/health
  pgweb      →  http://${HOST}:8081
  Postgres   →  ${HOST}:5432  (user: rag, db: rag_config)
═════════════════════════════════════════════════════════════════
EOF
