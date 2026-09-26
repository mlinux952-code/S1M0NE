"""Tests du Configuration Manager (Phase 1, étape 1)."""

from pathlib import Path

from core.config import Settings, load_settings


def test_config_toml_loads_and_has_expected_sections():
    s = load_settings()
    assert "server" in s.raw_toml
    assert "storage" in s.raw_toml
    assert "logging" in s.raw_toml


def test_data_dir_defaults_inside_project():
    s = load_settings()
    assert s.data_dir.is_absolute()
    assert "S1M0NE" in str(s.data_dir)


def test_env_override_for_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    s = load_settings()
    assert s.data_dir == tmp_path


def test_secrets_are_never_read_from_toml():
    s = load_settings()
    # Aucune section de config.toml ne doit contenir de vrai secret.
    for section, values in s.raw_toml.items():
        if isinstance(values, dict):
            for key in values:
                assert "token" not in key.lower()
                assert "secret" not in key.lower()


def test_safe_dict_masks_sensitive_env_keys(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("GITHUB_TOKEN=abcd1234\nS1MONE_LOG_LEVEL=DEBUG\n")
    config_file = Path("config/config.toml")
    s = load_settings(config_path=config_file, env_path=env_file)
    assert "GITHUB_TOKEN" in s.as_safe_dict()["_env_keys_present"]
    # la valeur elle-même ne doit jamais fuiter dans as_safe_dict (seule la clé apparaît)
    assert "abcd1234" not in str(s.as_safe_dict())
