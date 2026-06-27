#!/usr/bin/env bash
# deploy.sh — ag-flow.rag
# Télécharge les fichiers de config depuis GitHub (curl, pas git clone)
# et démarre la stack via Docker Compose.
#
# Deux modes selon la disponibilité de GHCR_TOKEN :
#
#   Mode BUILD (défaut) — construit les images localement depuis le code source :
#     bash deploy.sh
#     DEPLOY_DIR=/srv/rag bash deploy.sh
#
#   Mode PULL — télécharge les images pré-buildées depuis GHCR (packages privés) :
#     GHCR_TOKEN=ghp_... bash deploy.sh
#     GHCR_TOKEN=ghp_... GHCR_USER=monlogin bash deploy.sh
#
# Ce script est idempotent : il peut être relancé pour mettre à jour
# les fichiers de config et les images sans écraser un .env existant.

set -euo pipefail

# ─── Configuration ────────────────────────────────────────────────────────────

REPO="https://github.com/ag-flow/rag"
REPO_RAW="https://raw.githubusercontent.com/ag-flow/rag/main"
REMOTE_DIR="deploy/prod"
DEPLOY_DIR="${DEPLOY_DIR:-/opt/rag}"

# Mode pull GHCR — optionnel
GHCR_TOKEN="${GHCR_TOKEN:-}"
GHCR_USER="${GHCR_USER:-}"

CONFIG_FILES=(
    "docker-compose.yml"
    "docker-compose.build.yml"
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

for cmd in docker curl python3; do
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

# ─── Création du répertoire cible ─────────────────────────────────────────────

section "Création du répertoire $DEPLOY_DIR..."

mkdir -p "$DEPLOY_DIR"
info "Répertoire : $DEPLOY_DIR"

# ─── Téléchargement des fichiers de configuration ─────────────────────────────

section "Téléchargement des fichiers de configuration..."

for file in "${CONFIG_FILES[@]}"; do
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

# ─── Vérifier que .env est rempli ─────────────────────────────────────────────

if ! grep -q "^RAG_MASTER_KEY=.\+" "$ENV_FILE" 2>/dev/null; then
    echo
    warn "Le fichier .env n'est pas encore configuré."
    echo
    echo "  1. Remplir ${BOLD}${ENV_FILE}${RESET} :"
    echo "       cd ${DEPLOY_DIR} && \$EDITOR .env"
    echo
    echo "  2. Générer les secrets :"
    echo "       POSTGRES_PASSWORD : openssl rand -hex 24"
    echo "       RAG_MASTER_KEY    : openssl rand -hex 32"
    echo "       RAG_SESSION_SECRET: openssl rand -hex 32"
    echo "       HARPOCRATE_DEK    : openssl rand -hex 32  (si coffre Harpocrate)"
    echo
    echo "  3. Hash bcrypt admin :"
    echo "       python3 -c \"import bcrypt; print(bcrypt.hashpw(b'MON_MDP', bcrypt.gensalt(12)).decode())\""
    echo "       Coller le résultat dans RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH"
    echo "       IMPORTANT : dans .env, écrire \$\$ au lieu de \$ dans le hash bcrypt"
    echo
    echo "  4. Relancer ce script pour builder et démarrer :"
    echo "       curl -fsSL https://raw.githubusercontent.com/ag-flow/rag/main/deploy/prod/deploy.sh | bash"
    echo
    exit 0
fi

# ─── Mode PULL (GHCR_TOKEN fourni) ────────────────────────────────────────────

if [ -n "$GHCR_TOKEN" ]; then
    section "Mode PULL — authentification GHCR..."

    if [ -z "$GHCR_USER" ]; then
        GHCR_USER=$(curl -fsSL -H "Authorization: Bearer $GHCR_TOKEN" \
            https://api.github.com/user \
            | python3 -c "import sys,json; print(json.load(sys.stdin)['login'])" 2>/dev/null || echo "")
        if [ -z "$GHCR_USER" ]; then
            error "Impossible de récupérer le login GitHub. Passer GHCR_USER explicitement."
            exit 1
        fi
    fi

    echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin
    info "Connecté à ghcr.io en tant que $GHCR_USER"

    section "Téléchargement des images GHCR..."
    cd "$DEPLOY_DIR"
    docker compose pull
    docker compose up -d
    info "Stack démarrée (mode pull)."

# ─── Mode BUILD (défaut) ──────────────────────────────────────────────────────

else
    section "Mode BUILD — téléchargement du code source..."

    BUILD_CONTEXT=$(mktemp -d)
    trap 'rm -rf "$BUILD_CONTEXT"' EXIT

    TARBALL_URL="${REPO}/archive/refs/heads/main.tar.gz"
    info "Source : $TARBALL_URL"
    curl -fsSL "$TARBALL_URL" | tar xz -C "$BUILD_CONTEXT" --strip-components=1
    info "Code extrait dans : $BUILD_CONTEXT"

    section "Build des images Docker..."
    cd "$DEPLOY_DIR"
    export BUILD_CONTEXT
    docker compose --progress=plain -f docker-compose.build.yml build
    info "Images buildées."

    section "Démarrage de la stack..."
    docker compose -f docker-compose.build.yml up -d
    info "Stack démarrée (mode build)."
fi

# ─── Résumé final ─────────────────────────────────────────────────────────────

section "Déploiement terminé."
echo
echo -e "  Répertoire : ${BOLD}${DEPLOY_DIR}${RESET}"
echo
echo "  Commandes utiles :"
echo "    docker compose -f $DEPLOY_DIR/docker-compose.build.yml ps"
echo "    docker compose -f $DEPLOY_DIR/docker-compose.build.yml logs -f backend"
echo "    curl http://localhost/health"
echo
