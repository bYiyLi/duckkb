"""CLI 测试。"""

import json
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from duckkb.cli import app

runner = CliRunner()


class TestCLICommands:
    """CLI 命令测试。"""

    def test_version_command(self):
        """测试版本命令。"""
        result = runner.invoke(app, ["version"])

        assert result.exit_code == 0
        assert "DuckKB v" in result.stdout

    def test_help_command(self):
        """测试帮助命令。"""
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "DuckKB" in result.stdout


class TestGetKnowledgeIntro:
    """获取知识库介绍测试。"""

    def test_get_knowledge_intro(self, default_kb_path):
        """测试获取知识库介绍。"""
        result = runner.invoke(app, ["-k", str(default_kb_path), "get-knowledge-intro"])

        assert result.exit_code == 0
        assert "# 知识库介绍" in result.stdout
        assert "## 使用说明" in result.stdout
        assert "## 表结构" in result.stdout


class TestImportKnowledge:
    """导入知识数据测试。"""

    def test_import_knowledge_success(self, default_kb_path, tmp_path):
        """测试成功导入知识数据。"""
        yaml_content = """
- type: Character
  name: CLI测试角色
  bio: 这是一个通过CLI导入的测试角色
"""
        yaml_file = tmp_path / "test_bundle.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        result = runner.invoke(
            app,
            ["-k", str(default_kb_path), "import", str(yaml_file)],
        )

        assert result.exit_code == 0

        response = json.loads(result.stdout)
        assert response["status"] == "success"

    def test_import_knowledge_file_not_found(self, default_kb_path, tmp_path):
        """测试导入不存在的文件。"""
        result = runner.invoke(
            app,
            ["-k", str(default_kb_path), "import", str(tmp_path / "nonexistent.yaml")],
        )

        assert result.exit_code != 0


class TestCLIWithCustomKB:
    """自定义知识库 CLI 测试。"""

    def test_custom_kb_path(self, test_kb_path):
        """测试自定义知识库路径。"""
        result = runner.invoke(app, ["-k", str(test_kb_path), "version"])

        assert result.exit_code == 0

    def test_kb_path_creation(self, tmp_path):
        """测试知识库路径自动创建。"""
        new_kb_path = tmp_path / "new_kb"

        result = runner.invoke(app, ["-k", str(new_kb_path), "version"])

        assert result.exit_code == 0
        assert new_kb_path.exists()
