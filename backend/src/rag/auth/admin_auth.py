from __future__ import annotations

# require_admin est le même objet fonction que require_master_key_or_authenticated_admin.
# Cet alias permet aux tests d'utiliser dependency_overrides[require_admin]
# pour court-circuiter l'authentification, y compris la dépendance router-level.
from rag.auth.bearer import require_master_key_or_authenticated_admin as require_admin

__all__ = ["require_admin"]
