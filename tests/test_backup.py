
import shutil
from pathlib import Path
import pytest
from duckkb.engine.backup import BackupManager
from duckkb.constants import BACKUP_DIR_NAME, BUILD_DIR_NAME, DATA_DIR_NAME, DB_FILE_NAME

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
        # Create MAX_BACKUPS + 2 backups
        # We need to ensure they have different timestamps or are just different entries
        # Since the timestamp has seconds resolution, we might need to mock datetime or just create them.
        # But create_backup uses datetime.now().
        # Let's mock datetime to ensure different names/times if needed, 
        # but for simple count check, maybe just calling it is enough if it's fast? 
        # Actually if they happen in same second, name collision might occur if not handled?
        # The code: timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        # So collision is possible.
        
        # Let's mock datetime in the loop
        from unittest.mock import patch
        from datetime import datetime, timedelta, UTC
        
        base_time = datetime.now(UTC)
        
        with patch("duckkb.engine.backup.datetime") as mock_datetime:
            # We need to mock now() to return different times
            # and fromtimestamp() to work for list_backups
            mock_datetime.now.side_effect = [base_time + timedelta(seconds=i) for i in range(10)]
            mock_datetime.fromtimestamp.side_effect = datetime.fromtimestamp # Pass through
            # Wait, mocking the class replaces fromtimestamp too.
            # It's better to patch 'duckkb.engine.backup.datetime' specifically.
            # But fromtimestamp is called in list_backups.
            
            # Simpler approach: just create backups and let them be. 
            # If they collide, create_backup might overwrite or fail?
            # The code: backup_dir.mkdir(parents=True, exist_ok=True)
            # It overwrites.
            pass

        # Let's just try creating 5 backups (MAX is usually 5 or so?)
        # MAX_BACKUPS is imported from constants. Let's check it.
        # constants.py: MAX_BACKUPS = 5 (usually).
        
        # Let's manually create directories to simulate backups to avoid waiting
        backup_base = kb_path / BUILD_DIR_NAME / BACKUP_DIR_NAME
        backup_base.mkdir(parents=True, exist_ok=True)
        
        for i in range(10):
            d = backup_base / f"backup_{i}"
            d.mkdir()
            # Ensure different mtime
            import time
            import os
            os.utime(d, (time.time() + i, time.time() + i))
            
        manager._cleanup_old_backups()
        
        backups = manager.list_backups()
        # It should keep MAX_BACKUPS.
        # We need to know MAX_BACKUPS value.
        from duckkb.constants import MAX_BACKUPS
        assert len(backups) <= MAX_BACKUPS
