#!/usr/bin/env bash
# deploy.sh — ag-flow.rag
# Télécharge les fichiers de déploiement depuis GitHub et les installe
# dans le répertoire cible sur la machine de production.
#
# Usage :
#   bash deploy.sh                  # installe dans /opt/rag (défaut)
#   DEPLOY_DIR=/srv/rag bash deploy.sh
#
# Ce script est idempotent : il peut être relancé pour mettre à jour
# les fichiers sans écraser un .env existant.

set -euo pipefail

# ─── Configuration ────────────────────────────────────────────────────────────

REPO_RAW="https://raw.githubusercontent.com/ag-flow/rag/main"
REMOTE_DIR="deploy/prod"
DEPLOY_DIR="${DEPLOY_DIR:-/opt/rag}"

# GHCR_TOKEN : Personal Access Token GitHub (scope : read:packages)
# Requis si les packages GHCR sont privés.
# Peut être passé en variable d'environnement :
#   GHCR_TOKEN=ghp_... bash deploy.sh
GHCR_TOKEN="${GHCR_TOKEN:-}"
GHCR_USER="${GHCR_USER:-}"

FILES=(
    "docker-compose.yml"
    "Caddyfile"
    "pricing.yml"
    ".env.example"
)

# ─── Couleurs ─────────────────────────────────────────────────────────────────

BOLD="\033[1m"
GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"
RESET="\033[0m"

info()    { echo -e "${GREEN}[INFO]${RESET}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
section() { echo -e "\n${BOLD}$*${RESET}"; }

# ─── Vérifications préalables ─────────────────────────────────────────────────

section "Vérification des prérequis..."

for cmd in docker curl; do
    if ! command -v "$cmd" &>/dev/null; then
        error "$cmd n'est pas installé."
        exit 1
    fi
    info "$cmd : OK"
done

if ! docker compose version &>/dev/null; then
    error "Le plugin Docker Compose n'est pas installé (requis : v2.20+)."
    exit 1
fi
info "docker compose : OK"

DOCKER_VERSION=$(docker --version | grep -oP '\d+\.\d+' | head -1)
DOCKER_MAJOR=$(echo "$DOCKER_VERSION" | cut -d. -f1)
if [ "$DOCKER_MAJOR" -lt 24 ]; then
    warn "Docker $DOCKER_VERSION détecté. Version 24+ recommandée."
fi

# ─── Authentification GHCR (si packages privés) ──────────────────────────────

if [ -n "$GHCR_TOKEN" ]; then
    section "Authentification GHCR..."
    if [ -z "$GHCR_USER" ]; then
        # Récupérer le login depuis l'API GitHub
        GHCR_USER=$(curl -fsSL -H "Authorization: Bearer $GHCR_TOKEN" \
            https://api.github.com/user | python3 -c "import sys,json; print(json.load(sys.stdin)['login'])" 2>/dev/null || echo "")
        if [ -z "$GHCR_USER" ]; then
            error "Impossible de récupérer le login GitHub. Vérifier le token ou passer GHCR_USER."
            exit 1
        fi
    fi
    echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin
    info "Connecté à ghcr.io en tant que $GHCR_USER"
else
    warn "GHCR_TOKEN non défini — les images doivent être publiques."
    warn "Si le pull échoue, relancer avec : GHCR_TOKEN=ghp_... bash deploy.sh"
fi

# ─── Création du répertoire cible ─────────────────────────────────────────────

section "Création du répertoire $DEPLOY_DIR..."

mkdir -p "$DEPLOY_DIR"
info "Répertoire : $DEPLOY_DIR"

# ─── Téléchargement des fichiers ──────────────────────────────────────────────

section "Téléchargement des fichiers depuis GitHub..."

for file in "${FILES[@]}"; do
    url="${REPO_RAW}/${REMOTE_DIR}/${file}"
    dest="${DEPLOY_DIR}/${file}"

    curl -fsSL "$url" -o "$dest"
    info "Téléchargé : $file"
done

# ─── Initialisation du .env ───────────────────────────────────────────────────

section "Initialisation de la configuration..."

ENV_FILE="${DEPLOY_DIR}/.env"

if [ -f "$ENV_FILE" ]; then
    warn ".env existant conservé (non écrasé)."
else
    cp "${DEPLOY_DIR}/.env.example" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    info ".env créé depuis .env.example (chmod 600)."
fi

# ─── Résumé ───────────────────────────────────────────────────────────────────

section "Installation terminée."
echo
echo -e "  Répertoire : ${BOLD}${DEPLOY_DIR}${RESET}"
echo
echo -e "  Fichiers installés :"
for file in "${FILES[@]}" ".env"; do
    echo "    • ${DEPLOY_DIR}/${file}"
done

if ! grep -q "^RAG_MASTER_KEY=.\+" "$ENV_FILE" 2>/dev/null; then
    echo
    warn "Le fichier .env n'est pas encore configuré."
    echo
    echo "  Étapes suivantes :"
    echo
    echo -e "  1. Remplir ${BOLD}${ENV_FILE}${RESET} :"
    echo "       cd ${DEPLOY_DIR}"
    echo "       \$EDITOR .env"
    echo
    echo "  2. Générer les secrets requis :"
    echo "       POSTGRES_PASSWORD : openssl rand -hex 24"
    echo "       RAG_MASTER_KEY    : openssl rand -hex 32"
    echo "       RAG_SESSION_SECRET: openssl rand -hex 32"
    echo "       HARPOCRATE_DEK    : openssl rand -hex 32  (si coffre Harpocrate)"
    echo
    echo "  3. Générer le hash du mot de passe admin :"
    echo "       python3 -c \"import bcrypt; print(bcrypt.hashpw(b'MON_MDP', bcrypt.gensalt(12)).decode())\""
    echo
    echo "  4. Démarrer la stack :"
    echo "       cd ${DEPLOY_DIR} && docker compose up -d"
else
    echo
    info ".env déjà configuré."
    echo
    echo "  Pour mettre à jour la stack :"
    echo "    cd ${DEPLOY_DIR} && docker compose pull && docker compose up -d"
fi

echo
