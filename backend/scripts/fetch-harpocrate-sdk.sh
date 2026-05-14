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

mkdir -p "$VENDOR_DIR"
rm -f "$VENDOR_DIR"/harpocrate-*.whl

echo "[fetch-harpocrate-sdk] downloading from $HARPOCRATE_URL/v1/sdk/python-wheel"
curl -fsSL "$HARPOCRATE_URL/v1/sdk/python-wheel" -o "$VENDOR_DIR/harpocrate-sdk.whl"

echo "[fetch-harpocrate-sdk] saved to $VENDOR_DIR/harpocrate-sdk.whl"
