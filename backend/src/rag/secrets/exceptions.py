from __future__ import annotations


class HarpocrateVaultsError(Exception):
    """Base pour toutes les erreurs liées aux coffres Harpocrate."""


class HarpocrateDekMissingError(HarpocrateVaultsError):
    """HARPOCRATE_DEK requis mais absent alors qu'au moins un coffre existe en DB."""


class VaultNameAlreadyExistsError(HarpocrateVaultsError):
    """Le nom de coffre est déjà utilisé."""


class VaultNotFoundError(HarpocrateVaultsError):
    """Le coffre demandé n'existe pas."""
