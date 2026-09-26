"""Vérifie que 's1mone web' est bien enregistrée comme commande (sans démarrer de vrai serveur)."""

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


def test_web_command_is_registered_and_documented():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "web" in result.stdout
