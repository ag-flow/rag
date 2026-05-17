#!/usr/bin/env bash
# M5e-T11 — Smoke E2E sur LXC 303, mode dégradé.
#
# La création workspace via API requiert un coffre Harpocrate par défaut
# valide (design pré-existant, hors scope M5e). Le LXC 303 n'a pas de token
# Harpocrate valide actuellement → bypass via INSERT SQL direct, puis test
# du GET endpoint qui est le périmètre M5e à valider.
set -euo pipefail

ENV_FILE=/opt/rag/.env
[ -f "$ENV_FILE" ] || { echo "ERR: $ENV_FILE absent"; exit 1; }
MK=$(grep ^RAG_MASTER_KEY= "$ENV_FILE" | cut -d= -f2-)
DEK=$(grep ^RAG_API_KEY_DEK= "$ENV_FILE" | cut -d= -f2-)
[ -n "$MK" ]  || { echo "ERR: RAG_MASTER_KEY vide";  exit 1; }
[ -n "$DEK" ] || { echo "ERR: RAG_API_KEY_DEK vide"; exit 1; }

API_KEY="smoke-key-$(date +%s)"
FP=$(printf '%s' "$API_KEY" | sha256sum | cut -d' ' -f1)
BASE=http://localhost:8000/workspaces
SQL_INSERT="INSERT INTO workspaces (name, api_key_encrypted, api_key_fingerprint, rag_cnx, rag_base) VALUES ('ws_smoke_m5e', pgp_sym_encrypt('${API_KEY}'::text, '${DEK}'::text)::bytea, '${FP}', 'postgresql://smoke/none', 'rag_smoke');"

echo "=== INSERT direct workspace ws_smoke_m5e (bypass Harpocrate) ==="
docker exec rag-postgres psql -U rag -d rag_config -v ON_ERROR_STOP=1 -c "$SQL_INSERT"

echo
echo "=== Vérif INSERT en BDD ==="
docker exec rag-postgres psql -U rag -d rag_config -c "SELECT name, api_key_fingerprint FROM workspaces WHERE name='ws_smoke_m5e';"

echo
echo "=== GET 1 — endpoint M5e-T8 ==="
GET1=$(curl -sS -H "Authorization: Bearer $MK" "$BASE/ws_smoke_m5e/apikey")
echo "$GET1"
GET1_KEY=$(echo "$GET1" | python3 -c "import json,sys;print(json.load(sys.stdin)['api_key'])")

echo
echo "=== GET 2 — idempotence ==="
GET2=$(curl -sS -H "Authorization: Bearer $MK" "$BASE/ws_smoke_m5e/apikey")
echo "$GET2"
GET2_KEY=$(echo "$GET2" | python3 -c "import json,sys;print(json.load(sys.stdin)['api_key'])")

echo
echo "=== GET 3 — workspace inexistant (404) ==="
curl -sS -o /dev/null -w "HTTP %{http_code}\n" \
  -H "Authorization: Bearer $MK" \
  "$BASE/does_not_exist/apikey"

echo
echo "=== GET 4 — sans auth (401) ==="
curl -sS -o /dev/null -w "HTTP %{http_code}\n" \
  "$BASE/ws_smoke_m5e/apikey"

echo
echo "=== Assertions ==="
[ "$GET1_KEY" = "$API_KEY" ] || { echo "FAIL: GET1 != INSERT (déchiffrement KO) — got '$GET1_KEY' want '$API_KEY'"; exit 2; }
[ "$GET1_KEY" = "$GET2_KEY" ] || { echo "FAIL: GET1 != GET2 (non idempotent)"; exit 3; }
echo "OK : GET1 == GET2 == clé en clair (idempotent + déchiffrement pgcrypto valide)"

echo
echo "=== Cleanup ==="
docker exec rag-postgres psql -U rag -d rag_config -c "DELETE FROM workspaces WHERE name = 'ws_smoke_m5e';" >/dev/null

echo
echo "=== Smoke M5e PASS ==="
