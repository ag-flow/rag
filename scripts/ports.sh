# shellcheck shell=bash
#
# ports.sh — détection de port hôte libre, sourcé par dev-deploy.sh.
#
# Plusieurs stacks cohabitent sur une même machine de test (ex. ragflow et
# docflow) et publient toutes l'IHM sur le port 80 : la dernière démarrée
# prend le port, l'autre cesse de répondre sans aucune erreur. On choisit donc
# le premier port libre à partir du port souhaité.

# Vrai si un processus écoute sur le port TCP, OU si un conteneur Docker le
# publie. Les deux sources sont nécessaires : avec `userland-proxy: false`,
# Docker publie par règles iptables, sans socket en écoute visible par `ss`.
port_in_use() {
  local port="$1"
  if ss -ltnH "( sport = :${port} )" 2>/dev/null | grep -q .; then
    return 0
  fi
  # Format docker : « 0.0.0.0:80->80/tcp, [::]:80->80/tcp ». Le `:` avant le
  # numéro évite de confondre 80 avec 180 ou 8080.
  if docker ps --format '{{.Ports}}' 2>/dev/null | grep -Eq ":${port}->"; then
    return 0
  fi
  return 1
}

# Affiche le premier port libre dans [début, début + amplitude]. Échoue (code 1,
# rien affiché) si tous sont pris : l'appelant doit s'arrêter, pas deviner.
first_free_port() {
  local port="$1" span="${2:-100}"
  local last=$((port + span))
  while [ "$port" -le "$last" ]; do
    if ! port_in_use "$port"; then
      echo "$port"
      return 0
    fi
    port=$((port + 1))
  done
  return 1
}
