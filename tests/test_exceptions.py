import pytest

from duckkb.exceptions import ConfigurationError, DatabaseError, DuckKBError, SyncError


class TestExceptions:
    def test_duckkb_error_is_exception(self):
        assert issubclass(DuckKBError, Exception)

    def test_configuration_error_inherits_duckkb_error(self):
        assert issubclass(ConfigurationError, DuckKBError)
        assert issubclass(ConfigurationError, Exception)

    def test_database_error_inherits_duckkb_error(self):
        assert issubclass(DatabaseError, DuckKBError)
        assert issubclass(DatabaseError, Exception)

    def test_sync_error_inherits_duckkb_error(self):
        assert issubclass(SyncError, DuckKBError)
        assert issubclass(SyncError, Exception)

    def test_duckkb_error_can_be_raised(self):
        with pytest.raises(DuckKBError):
            raise DuckKBError("Test error")

    def test_configuration_error_can_be_raised(self):
        with pytest.raises(ConfigurationError):
            raise ConfigurationError("Config error")

    def test_database_error_can_be_raised(self):
        with pytest.raises(DatabaseError):
            raise DatabaseError("DB error")

    def test_sync_error_can_be_raised(self):
        with pytest.raises(SyncError):
            raise SyncError("Sync error")

    def test_configuration_error_caught_by_duckkb_error(self):
        with pytest.raises(DuckKBError):
            raise ConfigurationError("Should be caught as DuckKBError")

    def test_exception_message(self):
        try:
            raise DuckKBError("Custom message")
        except DuckKBError as e:
            assert str(e) == "Custom message"
