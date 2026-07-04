# BUG-055 — Contournement SSRF via des littéraux IPv6 mappés-IPv4 dans la validation d'URL webhook

**Statut : 🔴 à corriger**

- **Zone** : backend / services/webhook_validation
- **Sévérité** : haute (sécurité — SSRF)
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/services/webhook_validation.py:9-21,51-57`
- **Modèle recommandé** : **Opus** (`claude-opus-4-8`) — sécurité, normalisation IP subtile

## Description

Pour une IP littérale, le code vérifie l'appartenance à `_PRIVATE_NETWORKS` et retourne. `ipaddress.ip_address("::ffff:127.0.0.1")` est un `IPv6Address` ; les tests d'appartenance contre les réseaux IPv4 (`127.0.0.0/8`, `10.0.0.0/8`, …) renvoient `False` (mismatch de version), et il n'est pas dans `::1/128`/`fc00::/7`/`fe80::/10`. `_assert_public` passe. Sur un hôte dual-stack, se connecter à `[::ffff:127.0.0.1]` atteint 127.0.0.1. Idem pour `::ffff:10.x.x.x`, etc. (Secondaire : le `except ValueError: pass` autour du bloc IP littéral avale aussi le rejet SSRF pour les littéraux IPv4 — sauvé actuellement seulement parce que `getaddrinfo` les re-résout.)

## Scénario de défaillance

Un attaquant de niveau admin (ou un token admin compromis) enregistre l'URL webhook `http://[::ffff:169.254.169.254]/latest/meta-data/` → validation passe → le dispatch poste des payloads internes vers des services internes/link-local.

## Code concerné

```python
try:
    ip = ipaddress.ip_address(hostname)
    _assert_public(ip, hostname)     # ::ffff:127.0.0.1 matché par aucun réseau listé
    return
except ValueError:
    pass
```

## Piste de correction

Normaliser avec `ip.ipv4_mapped` (vérifier l'IPv4 embarquée contre les listes v4), et ajouter `::ffff:0:0/96`, `64:ff9b::/96`, multicast/reserved ; ne pas `pass` sur le ValueError de `_assert_public` pour les littéraux.
