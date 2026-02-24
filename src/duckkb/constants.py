"""全局常量定义模块。

本模块定义了 DuckKB 项目中使用的所有全局常量，包括：
- 目录和文件命名
- 查询限制
- 缓存配置
- 错误反馈设置
"""

DEFAULT_KB_DIR_NAME = "knowledge-bases"
DATA_DIR_NAME = "data"
BUILD_DIR_NAME = ".build"
DB_FILE_NAME = "knowledge.db"
SCHEMA_FILE_NAME = "schema.sql"
SYS_SEARCH_TABLE = "_sys_search"
SYS_CACHE_TABLE = "_sys_cache"

QUERY_RESULT_SIZE_LIMIT = 2 * 1024 * 1024
QUERY_DEFAULT_LIMIT = 1000

CACHE_EXPIRE_DAYS = 30

MAX_ERROR_FEEDBACK = 5
