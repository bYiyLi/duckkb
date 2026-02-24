import os
import time

import pytest

from duckkb.constants import (
    BACKUP_DIR_NAME,
    BUILD_DIR_NAME,
    DATA_DIR_NAME,
    DB_FILE_NAME,
    MAX_BACKUPS,
)
from duckkb.engine.backup import BackupManager


class TestBackupManager:
    @pytest.fixture
    def kb_path(self, tmp_path):
        """Create a temporary knowledge base structure."""
        kb_path = tmp_path / "test_kb"
        kb_path.mkdir()

        # Create build and data directories
        (kb_path / BUILD_DIR_NAME).mkdir()
        (kb_path / DATA_DIR_NAME).mkdir()

        # Create dummy db file
        db_file = kb_path / BUILD_DIR_NAME / DB_FILE_NAME
        db_file.write_text("dummy db content")

        # Create dummy data file
        data_file = kb_path / DATA_DIR_NAME / "test.jsonl"
        data_file.write_text('{"id": "1"}')

        # Create dummy config
        config_file = kb_path / "config.yaml"
        config_file.write_text("dummy config")

        return kb_path

    def test_create_backup(self, kb_path):
        manager = BackupManager(kb_path)
        backup_path = manager.create_backup(prefix="test")

        assert backup_path is not None
        assert backup_path.exists()
        assert (backup_path / DB_FILE_NAME).exists()
        assert (backup_path / DATA_DIR_NAME).exists()
        assert (backup_path / "config.yaml").exists()
        assert "test_" in backup_path.name

    def test_list_backups(self, kb_path):
        manager = BackupManager(kb_path)
        backup1 = manager.create_backup(prefix="b1")
        backup2 = manager.create_backup(prefix="b2")

        backups = manager.list_backups()
        assert len(backups) == 2
        assert backups[0]["name"] == backup2.name  # Sorted by time desc (or name if same second?)
        assert backups[1]["name"] == backup1.name

    def test_restore_backup(self, kb_path):
        manager = BackupManager(kb_path)

        # Create a backup
        backup_path = manager.create_backup(prefix="orig")
        assert backup_path is not None

        # Modify original files
        db_file = kb_path / BUILD_DIR_NAME / DB_FILE_NAME
        db_file.write_text("modified db")

        # Restore
        success = manager.restore_backup(backup_path)
        assert success

        # Verify content
        assert db_file.read_text() == "dummy db content"

    def test_delete_backup(self, kb_path):
        manager = BackupManager(kb_path)
        backup_path = manager.create_backup()
        assert backup_path.exists()

        success = manager.delete_backup(backup_path.name)
        assert success
        assert not backup_path.exists()

    def test_cleanup_old_backups(self, kb_path):
        manager = BackupManager(kb_path)

        # Manually create directories to simulate backups
        backup_base = kb_path / BUILD_DIR_NAME / BACKUP_DIR_NAME
        backup_base.mkdir(parents=True, exist_ok=True)

        # Create more than MAX_BACKUPS
        for i in range(MAX_BACKUPS + 5):
            d = backup_base / f"backup_{i}"
            d.mkdir()
            # Ensure different mtime
            os.utime(d, (time.time() + i, time.time() + i))

        manager._cleanup_old_backups()

        backups = manager.list_backups()
        assert len(backups) <= MAX_BACKUPS
