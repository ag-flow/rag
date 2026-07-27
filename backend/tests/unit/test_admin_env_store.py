"""AdminEnvStore : lecture/écriture du fichier admin.env, relu à chaud."""

from __future__ import annotations

from pathlib import Path

from rag.admin_env import (
    KEY_LOCAL_AUTH_DISABLED,
    KEY_OIDC_CLIENT_SECRET,
    AdminEnvStore,
)


def _store(tmp_path: Path) -> AdminEnvStore:
    return AdminEnvStore(tmp_path / "admin.env")


class TestDefaults:
    def test_missing_file_local_auth_enabled(self, tmp_path: Path) -> None:
        # Variable absente ⇒ connexion locale activée.
        assert _store(tmp_path).is_local_auth_disabled() is False

    def test_missing_file_no_client_secret(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        assert store.get_oidc_client_secret() is None
        assert store.has_oidc_client_secret() is False


class TestPublicUrl:
    def test_missing_file_no_public_url(self, tmp_path: Path) -> None:
        # Absent ⇒ None : le caller dérive l'URL de l'adresse d'appel.
        assert _store(tmp_path).get_public_url() is None

    def test_set_then_read_strips_trailing_slash(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.set_public_url("https://rag.yoops.org/")
        assert store.get_public_url() == "https://rag.yoops.org"

    def test_set_empty_clears(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.set_public_url("https://rag.yoops.org")
        store.set_public_url("")
        assert store.get_public_url() is None


class TestLocalAuthFlag:
    def test_set_disabled_then_read(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.set_local_auth_disabled(True)
        assert store.is_local_auth_disabled() is True
        store.set_local_auth_disabled(False)
        assert store.is_local_auth_disabled() is False

    def test_hand_written_true_is_read(self, tmp_path: Path) -> None:
        p = tmp_path / "admin.env"
        p.write_text(f"{KEY_LOCAL_AUTH_DISABLED}=true\n", encoding="utf-8")
        assert _store(tmp_path).is_local_auth_disabled() is True


class TestClientSecret:
    def test_set_then_read(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.set_oidc_client_secret("hrpv_secret_value")
        assert store.get_oidc_client_secret() == "hrpv_secret_value"
        assert store.has_oidc_client_secret() is True

    def test_overwrite_keeps_single_line(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.set_oidc_client_secret("first")
        store.set_oidc_client_secret("second")
        assert store.get_oidc_client_secret() == "second"
        content = (tmp_path / "admin.env").read_text(encoding="utf-8")
        assert content.count(KEY_OIDC_CLIENT_SECRET) == 1


class TestPreservation:
    def test_writing_one_key_preserves_other_and_comments(self, tmp_path: Path) -> None:
        p = tmp_path / "admin.env"
        p.write_text(
            f"# commentaire\n{KEY_OIDC_CLIENT_SECRET}=kept\n",
            encoding="utf-8",
        )
        store = _store(tmp_path)
        store.set_local_auth_disabled(True)

        content = p.read_text(encoding="utf-8")
        assert "# commentaire" in content
        assert store.get_oidc_client_secret() == "kept"
        assert store.is_local_auth_disabled() is True
