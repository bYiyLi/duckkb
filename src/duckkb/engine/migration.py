"""数据库迁移模块。

提供 ontology 配置变更时的数据库迁移功能，支持事务性操作和自动回滚。
"""

from pathlib import Path
from typing import Any

import yaml

from duckkb.config import AppContext
from duckkb.constants import SYS_SEARCH_TABLE
from duckkb.db import get_db
from duckkb.engine.backup import BackupManager
from duckkb.logger import logger
from duckkb.ontology import Ontology, OntologyEngine


class MigrationError(Exception):
    """迁移错误异常。"""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        """初始化迁移错误。

        Args:
            message: 错误信息。
            details: 错误详情字典。
        """
        super().__init__(message)
        self.details = details or {}


class MigrationResult:
    """迁移结果。"""

    def __init__(self) -> None:
        """初始化迁移结果。"""
        self.success = False
        self.tables_added: list[str] = []
        self.tables_removed: list[str] = []
        self.tables_modified: list[str] = []
        self.errors: list[str] = []
        self.backup_path: Path | None = None
        self.rolled_back = False

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式。

        Returns:
            包含迁移结果的字典。
        """
        return {
            "success": self.success,
            "tables_added": self.tables_added,
            "tables_removed": self.tables_removed,
            "tables_modified": self.tables_modified,
            "errors": self.errors,
            "backup_path": str(self.backup_path) if self.backup_path else None,
            "rolled_back": self.rolled_back,
        }


class MigrationManager:
    """数据库迁移管理器。

    负责处理 ontology 配置变更时的数据库迁移，包括：
    - 配置校验
    - 备份创建
    - 模式迁移
    - 数据迁移
    - 自动回滚

    Attributes:
        kb_path: 知识库根目录路径。
        backup_manager: 备份管理器实例。
    """

    def __init__(self, kb_path: Path) -> None:
        """初始化迁移管理器。

        Args:
            kb_path: 知识库根目录路径。
        """
        self.kb_path = kb_path
        self.backup_manager = BackupManager(kb_path)

    def parse_ontology_yaml(self, ontology_yaml: str) -> Ontology:
        """解析 YAML 格式的 ontology 配置。

        Args:
            ontology_yaml: YAML 格式的 ontology 配置字符串。

        Returns:
            解析后的 Ontology 实例。

        Raises:
            MigrationError: YAML 解析或配置验证失败时抛出。
        """
        try:
            data = yaml.safe_load(ontology_yaml)
            if data is None:
                data = {}
            return Ontology(**data)
        except yaml.YAMLError as e:
            raise MigrationError(f"Invalid YAML format: {e}") from e
        except Exception as e:
            raise MigrationError(f"Invalid ontology configuration: {e}") from e

    def get_current_table_names(self) -> list[str]:
        """获取当前数据库中的所有表名。

        Returns:
            表名列表。
        """
        try:
            with get_db(read_only=True) as conn:
                rows = conn.execute(
                    f"SELECT DISTINCT source_table FROM {SYS_SEARCH_TABLE}"
                ).fetchall()
            return [row[0] for row in rows]
        except Exception as e:
            logger.warning(f"Failed to get table names: {e}")
            return []

    def analyze_changes(self, new_ontology: Ontology) -> dict[str, Any]:
        """分析 ontology 变更。

        Args:
            new_ontology: 新的 ontology 配置。

        Returns:
            包含变更分析的字典。
        """
        current_tables = set(self.get_current_table_names())
        new_tables = set(new_ontology.nodes.keys()) if new_ontology.nodes else set()

        return {
            "tables_to_add": list(new_tables - current_tables),
            "tables_to_remove": list(current_tables - new_tables),
            "tables_to_modify": list(current_tables & new_tables),
            "current_tables": list(current_tables),
            "new_tables": list(new_tables),
        }

    def migrate(self, ontology_yaml: str, force: bool = False) -> MigrationResult:
        """执行数据库迁移。

        Args:
            ontology_yaml: YAML 格式的新 ontology 配置。
            force: 是否强制执行（跳过部分安全检查）。

        Returns:
            MigrationResult 实例包含迁移结果。
        """
        result = MigrationResult()

        try:
            new_ontology = self.parse_ontology_yaml(ontology_yaml)
        except MigrationError as e:
            result.errors.append(str(e))
            return result

        changes = self.analyze_changes(new_ontology)
        result.tables_added = changes["tables_to_add"]
        result.tables_removed = changes["tables_to_remove"]
        result.tables_modified = changes["tables_to_modify"]

        if changes["tables_to_remove"] and not force:
            result.errors.append(
                f"Migration would remove tables: {changes['tables_to_remove']}. "
                "Use force=True to proceed."
            )
            return result

        result.backup_path = self.backup_manager.create_backup(prefix="migration")
        if result.backup_path is None:
            result.errors.append("Failed to create backup before migration")
            return result

        try:
            self._apply_schema_changes(new_ontology, changes)
            self._update_config(new_ontology)
            result.success = True
            logger.info(f"Migration completed successfully: {result.to_dict()}")
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            result.errors.append(str(e))
            self._rollback(result)

        return result

    def _apply_schema_changes(self, new_ontology: Ontology, changes: dict[str, Any]) -> None:
        """应用模式变更。

        Args:
            new_ontology: 新的 ontology 配置。
            changes: 变更分析结果。

        Raises:
            MigrationError: 模式变更失败时抛出。
        """
        with get_db(read_only=False) as conn:
            for table_name in changes["tables_to_remove"]:
                try:
                    conn.execute(
                        f"DELETE FROM {SYS_SEARCH_TABLE} WHERE source_table = ?",
                        [table_name],
                    )
                    logger.info(f"Removed table from search index: {table_name}")
                except Exception as e:
                    raise MigrationError(f"Failed to remove table {table_name}: {e}") from e

            if new_ontology.nodes:
                nodes_ddl = OntologyEngine(new_ontology).generate_ddl()
                if nodes_ddl:
                    try:
                        conn.execute(nodes_ddl)
                        logger.info("Applied new ontology DDL")
                    except Exception as e:
                        raise MigrationError(f"Failed to apply new schema: {e}") from e

    def _update_config(self, new_ontology: Ontology) -> None:
        """更新配置文件。

        Args:
            new_ontology: 新的 ontology 配置。
        """
        config_path = self.kb_path / "config.yaml"

        try:
            if config_path.exists():
                with open(config_path, encoding="utf-8") as f:
                    config_data = yaml.safe_load(f) or {}
            else:
                config_data = {}

            config_data["ontology"] = new_ontology.model_dump(exclude_none=True)

            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)

            AppContext.get().kb_config.ontology = new_ontology
            logger.info("Updated config.yaml with new ontology")
        except Exception as e:
            raise MigrationError(f"Failed to update config: {e}") from e

    def _rollback(self, result: MigrationResult) -> None:
        """回滚迁移。

        Args:
            result: 迁移结果对象。
        """
        if result.backup_path is None:
            logger.error("No backup available for rollback")
            return

        logger.warning(f"Rolling back migration from {result.backup_path}")

        if self.backup_manager.restore_backup(result.backup_path):
            result.rolled_back = True
            logger.info("Migration rolled back successfully")
        else:
            result.errors.append("Failed to rollback migration")
            logger.error("Rollback failed - manual intervention required")
