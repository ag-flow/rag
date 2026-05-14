#!/usr/bin/env bash
# Télécharge le wheel du SDK Harpocrate dans backend/vendor/.
# Utilisé en local (avant `uv sync`) et au build Docker.
#
# Usage :
#   ./scripts/fetch-harpocrate-sdk.sh                       # défaut https://vault.yoops.org
#   HARPOCRATE_URL=https://other.host ./scripts/fetch-harpocrate-sdk.sh

set -euo pipefail

HARPOCRATE_URL="${HARPOCRATE_URL:-https://vault.yoops.org}"
VENDOR_DIR="$(cd "$(dirname "$0")/.." && pwd)/vendor"

# Le nom doit respecter PEP 427 (nom-version-python_tag-abi_tag-platform_tag.whl)
# pour que `uv` accepte le wheel. La version dans le filename DOIT correspondre
# à la version interne du wheel (uv vérifie). Quand Harpocrate sort une nouvelle
# version, mettre à jour ici + Dockerfile + pyproject.toml [tool.uv.sources].
WHEEL_NAME="harpocrate-0.4.0-py3-none-any.whl"

mkdir -p "$VENDOR_DIR"
rm -f "$VENDOR_DIR"/harpocrate-*.whl

echo "[fetch-harpocrate-sdk] downloading from $HARPOCRATE_URL/v1/sdk/python-wheel"
curl -fsSL "$HARPOCRATE_URL/v1/sdk/python-wheel" -o "$VENDOR_DIR/$WHEEL_NAME"

echo "[fetch-harpocrate-sdk] saved to $VENDOR_DIR/$WHEEL_NAME"
