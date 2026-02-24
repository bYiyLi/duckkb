class DuckKBError(Exception):
    """Base exception for DuckKB"""

    pass


class ConfigurationError(DuckKBError):
    """Configuration related errors"""

    pass


class DatabaseError(DuckKBError):
    """Database related errors"""

    pass


class SyncError(DuckKBError):
    """Synchronization errors"""

    pass
