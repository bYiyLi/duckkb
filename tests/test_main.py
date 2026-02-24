from unittest.mock import patch

from typer.testing import CliRunner

from duckkb import __version__
from duckkb.config import AppContext
from duckkb.main import app

runner = CliRunner()


class TestMainCLI:
    def test_version_command(self, tmp_path):
        kb_path = tmp_path / "test_kb"
        result = runner.invoke(app, ["--kb-path", str(kb_path), "version"])
        assert result.exit_code == 0
        AppContext.reset()

    def test_version_format(self):
        assert __version__ == "0.1.0"

    def test_serve_command_creates_kb_path(self, tmp_path):
        kb_path = tmp_path / "test_kb"
        with patch("duckkb.main.mcp.run"):
            runner.invoke(app, ["--kb-path", str(kb_path), "serve"])
        assert kb_path.exists()

    def test_app_context_initialized_with_kb_path(self, tmp_path):
        kb_path = tmp_path / "test_kb"
        with patch("duckkb.main.mcp.run"):
            runner.invoke(app, ["--kb-path", str(kb_path), "serve"])
        AppContext.reset()

    def test_help_command(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "DuckKB" in result.output

    def test_version_help(self):
        result = runner.invoke(app, ["version", "--help"])
        assert result.exit_code == 0

    def test_serve_help(self):
        result = runner.invoke(app, ["serve", "--help"])
        assert result.exit_code == 0
