from duckkb.config import settings
from duckkb.constants import SCHEMA_FILE_NAME, SYS_CACHE_TABLE, SYS_SEARCH_TABLE
from duckkb.db import get_db
from duckkb.logger import logger

SYS_SCHEMA_DDL = f"""
CREATE TABLE IF NOT EXISTS {SYS_SEARCH_TABLE} (
    ref_id VARCHAR,
    source_table VARCHAR,
    source_field VARCHAR,
    segmented_text TEXT,
    embedding_id VARCHAR,
    metadata JSON,
    priority_weight FLOAT DEFAULT 1.0,
    PRIMARY KEY (ref_id, source_table, source_field)
);

CREATE TABLE IF NOT EXISTS {SYS_CACHE_TABLE} (
    content_hash VARCHAR PRIMARY KEY,
    embedding FLOAT[{settings.EMBEDDING_DIM}],
    last_used TIMESTAMP
);
"""


def init_schema():
    """Initialize the database schema."""
    logger.info("Initializing schema...")

    with get_db(read_only=False) as conn:
        # 1. Create system tables
        conn.execute(SYS_SCHEMA_DDL)
        logger.debug("System tables ensured.")

        # 2. Apply user schema if exists
        schema_path = settings.KB_PATH / SCHEMA_FILE_NAME
        if schema_path.exists():
            logger.info(f"Applying schema from {schema_path}")
            schema_sql = schema_path.read_text(encoding="utf-8")
            try:
                conn.execute(schema_sql)
            except Exception as e:
                logger.error(f"Failed to apply schema.sql: {e}")
                raise
        else:
            logger.warning(f"No {SCHEMA_FILE_NAME} found in {settings.KB_PATH}")


def get_schema_info() -> str:
    """Return the schema definition."""
    schema_path = settings.KB_PATH / SCHEMA_FILE_NAME
    user_schema = ""
    if schema_path.exists():
        user_schema = (
            f"-- User Schema ({SCHEMA_FILE_NAME})\n{schema_path.read_text(encoding='utf-8')}\n\n"
        )

    return f"{user_schema}-- System Schema\n{SYS_SCHEMA_DDL}"
