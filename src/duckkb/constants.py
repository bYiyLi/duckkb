"""全局常量定义模块。

本模块定义了 DuckKB 项目中使用的所有全局常量，包括：
- 查询限制
- 嵌入模型配置
- 日志级别配置
- 类型别名定义
"""

import re

from duckkb.exceptions import InvalidTableNameError

QUERY_RESULT_SIZE_LIMIT = 2 * 1024 * 1024
QUERY_DEFAULT_LIMIT = 1000

EMBEDDING_MODEL_DIMS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_EMBEDDING_DIM = 1536
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_CHUNK_SIZE = 800
DEFAULT_TOKENIZER = "jieba"
CONFIG_FILE_NAME = "config.yaml"

VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

KNOWN_EMBEDDING_DIMS = {1536, 3072, 4096}
VALID_METRICS = {"cosine", "l2", "inner"}
DEFAULT_METRIC = "cosine"

TABLE_NAME_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

type SearchRow = tuple[str, str, str, str, str, list[float], str, float]


def validate_table_name(table_name: str) -> str:
    """验证表名是否安全。

    表名必须以字母或下划线开头，只能包含字母、数字和下划线。
    这是为了防止 SQL 注入攻击。

    Args:
        table_name: 待验证的表名。

    Returns:
        验证通过的表名。

    Raises:
        InvalidTableNameError: 表名格式不安全时抛出。
    """
    if not table_name:
        raise InvalidTableNameError(table_name, "Table name cannot be empty")
    if not TABLE_NAME_PATTERN.match(table_name):
        raise InvalidTableNameError(
            table_name,
            "must start with letter or underscore, and contain only alphanumeric characters and underscores",
        )
    if len(table_name) > 64:
        raise InvalidTableNameError(table_name, "too long (max 64 characters)")
    return table_name
