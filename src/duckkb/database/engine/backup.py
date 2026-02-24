"""备份与恢复模块。

提供知识库的备份和恢复功能，支持数据库、配置文件和数据文件的完整备份。
"""

import shutil
from datetime import UTC, datetime
from pathlib import Path

from duckkb.constants import (
    BACKUP_DIR_NAME,
    BUILD_DIR_NAME,
    DATA_DIR_NAME,
    DB_FILE_NAME,
    MAX_BACKUPS,
)
from duckkb.logger import logger


class BackupManager:
    """知识库备份管理器。

    负责创建和管理知识库的备份，支持完整备份和恢复。

    Attributes:
        kb_path: 知识库根目录路径。
        db_path: 数据库文件路径。
        data_dir: 数据文件目录路径。
        backup_base_dir: 备份根目录路径。
    """

    def __init__(self, kb_path: Path) -> None:
        """初始化备份管理器。

        Args:
            kb_path: 知识库根目录路径。
        """
        self.kb_path = kb_path
        self.db_path = kb_path / BUILD_DIR_NAME / DB_FILE_NAME
        self.data_dir = kb_path / DATA_DIR_NAME
        self.backup_base_dir = kb_path / BUILD_DIR_NAME / BACKUP_DIR_NAME

    def _get_backup_dir(self, timestamp: str) -> Path:
        """获取指定时间戳的备份目录。

        Args:
            timestamp: 时间戳字符串。

        Returns:
            备份目录路径。
        """
        return self.backup_base_dir / timestamp

    def create_backup(self, prefix: str = "") -> Path | None:
        """创建知识库完整备份。

        Args:
            prefix: 备份名称前缀，用于标识备份类型。

        Returns:
            备份目录路径，失败时返回 None。
        """
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        if prefix:
            backup_name = f"{prefix}_{timestamp}"
        else:
            backup_name = timestamp

        backup_dir = self._get_backup_dir(backup_name)

        try:
            backup_dir.mkdir(parents=True, exist_ok=True)

            if self.db_path.exists():
                shutil.copy2(self.db_path, backup_dir / DB_FILE_NAME)
                logger.debug(f"Backed up database to {backup_dir}")

            if self.data_dir.exists():
                shutil.copytree(self.data_dir, backup_dir / DATA_DIR_NAME)
                logger.debug(f"Backed up data directory to {backup_dir}")

            config_path = self.kb_path / "config.yaml"
            if config_path.exists():
                shutil.copy2(config_path, backup_dir / "config.yaml")
                logger.debug(f"Backed up config to {backup_dir}")

            logger.info(f"Created backup: {backup_dir}")
            self._cleanup_old_backups()
            return backup_dir

        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            if backup_dir.exists():
                shutil.rmtree(backup_dir, ignore_errors=True)
            return None

    def restore_backup(self, backup_dir: Path) -> bool:
        """从备份恢复知识库。

        Args:
            backup_dir: 备份目录路径。

        Returns:
            恢复成功返回 True，失败返回 False。
        """
        if not backup_dir.exists():
            logger.error(f"Backup directory does not exist: {backup_dir}")
            return False

        try:
            backup_db = backup_dir / DB_FILE_NAME
            if backup_db.exists():
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup_db, self.db_path)
                logger.debug(f"Restored database from {backup_dir}")

            backup_data = backup_dir / DATA_DIR_NAME
            if backup_data.exists():
                if self.data_dir.exists():
                    shutil.rmtree(self.data_dir)
                shutil.copytree(backup_data, self.data_dir)
                logger.debug(f"Restored data directory from {backup_dir}")

            backup_config = backup_dir / "config.yaml"
            if backup_config.exists():
                shutil.copy2(backup_config, self.kb_path / "config.yaml")
                logger.debug(f"Restored config from {backup_dir}")

            logger.info(f"Restored backup from {backup_dir}")
            return True

        except Exception as e:
            logger.error(f"Failed to restore backup: {e}")
            return False

    def list_backups(self) -> list[dict[str, str | int]]:
        """列出所有可用备份。

        Returns:
            包含备份信息的字典列表，按时间倒序排列。
        """
        if not self.backup_base_dir.exists():
            return []

        backups: list[dict[str, str | int]] = []
        for backup_dir in self.backup_base_dir.iterdir():
            if backup_dir.is_dir():
                stat = backup_dir.stat()
                backups.append(
                    {
                        "name": backup_dir.name,
                        "path": str(backup_dir),
                        "created_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                        "size": sum(f.stat().st_size for f in backup_dir.rglob("*") if f.is_file()),
                    }
                )

        backups.sort(key=lambda x: str(x["created_at"]), reverse=True)
        return backups

    def delete_backup(self, backup_name: str) -> bool:
        """删除指定备份。

        Args:
            backup_name: 备份名称。

        Returns:
            删除成功返回 True，失败返回 False。
        """
        backup_dir = self._get_backup_dir(backup_name)
        if not backup_dir.exists():
            logger.warning(f"Backup does not exist: {backup_name}")
            return False

        try:
            shutil.rmtree(backup_dir)
            logger.info(f"Deleted backup: {backup_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete backup: {e}")
            return False

    def _cleanup_old_backups(self) -> None:
        """清理旧备份，保留最新的 MAX_BACKUPS 个。"""
        backups = self.list_backups()
        if len(backups) <= MAX_BACKUPS:
            return

        for backup in backups[MAX_BACKUPS:]:
            self.delete_backup(str(backup["name"]))

    def get_backup_info(self, backup_name: str) -> dict[str, str | int | bool] | None:
        """获取指定备份的详细信息。

        Args:
            backup_name: 备份名称。

        Returns:
            备份信息字典，不存在时返回 None。
        """
        backup_dir = self._get_backup_dir(backup_name)
        if not backup_dir.exists():
            return None

        info: dict[str, str | int | bool] = {
            "name": backup_name,
            "path": str(backup_dir),
            "has_database": (backup_dir / DB_FILE_NAME).exists(),
            "has_data": (backup_dir / DATA_DIR_NAME).exists(),
            "has_config": (backup_dir / "config.yaml").exists(),
        }

        stat = backup_dir.stat()
        info["created_at"] = datetime.fromtimestamp(stat.st_mtime, UTC).isoformat()
        info["size"] = sum(f.stat().st_size for f in backup_dir.rglob("*") if f.is_file())

        return info
