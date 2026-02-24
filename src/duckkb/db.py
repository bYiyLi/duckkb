import duckdb
from contextlib import contextmanager
from duckkb.config import settings
from duckkb.constants import BUILD_DIR_NAME, DB_FILE_NAME

class DBManager:
    def __init__(self):
        self.db_path = settings.KB_PATH / BUILD_DIR_NAME / DB_FILE_NAME
        
    def get_connection(self, read_only: bool = True) -> duckdb.DuckDBPyConnection:
        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        return duckdb.connect(str(self.db_path), read_only=read_only)

db_manager = DBManager()

@contextmanager
def get_db(read_only: bool = True):
    conn = db_manager.get_connection(read_only=read_only)
    try:
        yield conn
    finally:
        conn.close()
