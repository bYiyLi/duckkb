# 知识库配置优化计划

## 目标

1. 在知识库目录下添加 `config.yaml` 文件保存知识库配置
2. 移除环境变量配置方式
3. `KB_PATH` 通过 CLI 启动时传入

---

## 当前架构问题

```
┌─────────────────────────────────────────────────────────────┐
│  config.py                                                  │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ settings = Settings()  # 模块导入时立即实例化        │    │
│  │ - KB_PATH (环境变量/默认值)                          │    │
│  │ - OPENAI_API_KEY (环境变量)                          │    │
│  │ - EMBEDDING_MODEL (环境变量/默认值)                  │    │
│  │ - EMBEDDING_DIM (环境变量/默认值)                    │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
         ↓ 导入时依赖
┌─────────────────────────────────────────────────────────────┐
│  db.py, schema.py, logger.py, embedding.py, server.py       │
│  - 直接使用 settings.XXX                                    │
│  - 模块级单例 (db_manager, SYS_SCHEMA_DDL)                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 新架构设计

```
┌─────────────────────────────────────────────────────────────┐
│  config.py                                                  │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ GlobalConfig (全局配置，启动时初始化)                │    │
│  │ - OPENAI_API_KEY                                    │    │
│  │ - OPENAI_BASE_URL                                   │    │
│  └─────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ KBConfig (知识库配置，从 config.yaml 加载)          │    │
│  │ - EMBEDDING_MODEL                                   │    │
│  │ - EMBEDDING_DIM                                     │    │
│  │ - LOG_LEVEL                                         │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  knowledge-bases/my-kb/                                     │
│  ├── config.yaml          # 知识库配置                      │
│  ├── data/               # JSONL 数据文件                   │
│  ├── build/              # 构建产物 (DuckDB, 缓存)          │
│  └── schema.sql          # 用户自定义 schema                │
└─────────────────────────────────────────────────────────────┘
```

---

## config.yaml 示例

```yaml
embedding:
  model: text-embedding-3-small
  dim: 1536

log_level: INFO
```

---

## 实现步骤

### 1. 添加依赖

在 `pyproject.toml` 添加 `pyyaml` 依赖。

### 2. 重构 config.py

```python
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, field_validator

EMBEDDING_MODEL_DIMS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}

VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

class GlobalConfig(BaseModel):
    OPENAI_API_KEY: str | None = None
    OPENAI_BASE_URL: str | None = None

class KBConfig(BaseModel):
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIM: int = 1536
    LOG_LEVEL: str = "INFO"
    
    @classmethod
    def from_yaml(cls, kb_path: Path) -> "KBConfig":
        config_path = kb_path / "config.yaml"
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            # 映射 yaml 字段到配置
            return cls(
                EMBEDDING_MODEL=data.get("embedding", {}).get("model", "text-embedding-3-small"),
                EMBEDDING_DIM=data.get("embedding", {}).get("dim", 1536),
                LOG_LEVEL=data.get("log_level", "INFO"),
            )
        return cls()

class AppContext:
    _instance: "AppContext | None" = None
    
    def __init__(self, kb_path: Path):
        self.kb_path = kb_path.resolve()
        self.kb_config = KBConfig.from_yaml(kb_path)
        self.global_config = GlobalConfig()
    
    @classmethod
    def get(cls) -> "AppContext":
        if cls._instance is None:
            raise RuntimeError("AppContext not initialized. Call init_context() first.")
        return cls._instance
    
    @classmethod
    def init(cls, kb_path: Path) -> "AppContext":
        cls._instance = AppContext(kb_path)
        return cls._instance

def get_kb_config() -> KBConfig:
    return AppContext.get().kb_config

def get_global_config() -> GlobalConfig:
    return AppContext.get().global_config
```

### 3. 修改 main.py

```python
from pathlib import Path

import typer

from duckkb.config import AppContext
from duckkb.logger import setup_logging

app = typer.Typer()

@app.callback()
def main(
    kb_path: Path = typer.Option(
        Path("./knowledge-bases/default"),
        "--kb-path", "-k",
        exists=True,
        help="Path to knowledge base directory"
    )
):
    AppContext.init(kb_path)
    setup_logging()
```

### 4. 修改 db.py

```python
from duckkb.config import AppContext

class DBManager:
    def __init__(self, kb_path: Path):
        self.db_path = kb_path / BUILD_DIR_NAME / DB_FILE_NAME

def get_db_manager() -> DBManager:
    return DBManager(AppContext.get().kb_path)
```

### 5. 修改 schema.py

将 `SYS_SCHEMA_DDL` 改为函数：

```python
def get_sys_schema_ddl(embedding_dim: int) -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {SYS_CACHE_TABLE} (
        content_hash VARCHAR PRIMARY KEY,
        embedding FLOAT[{embedding_dim}],
        last_used TIMESTAMP
    );
    """
```

### 6. 修改 logger.py

```python
def setup_logging(level: str = "INFO"):
    logging.basicConfig(level=level, ...)
```

### 7. 修改 mcp/server.py

移除模块级的 `setup_logging()` 和 `init_schema()` 调用，改为在 CLI 启动时调用。

### 8. 修改 utils/embedding.py

使用 `get_global_config()` 和 `get_kb_config()` 替代 `settings`。

### 9. 更新测试

修改 `conftest.py` 使用新的配置初始化方式。

---

## 文件修改清单

| 文件 | 修改内容 |
|------|----------|
| `pyproject.toml` | 添加 pyyaml 依赖 |
| `config.py` | 重构为 GlobalConfig + KBConfig + AppContext |
| `main.py` | 添加 --kb-path 参数，初始化 AppContext |
| `db.py` | 延迟初始化 DBManager |
| `schema.py` | DDL 改为运行时构建 |
| `logger.py` | setup_logging 接受 level 参数 |
| `mcp/server.py` | 移除模块级初始化 |
| `utils/embedding.py` | 使用新的配置获取方式 |
| `engine/indexer.py` | 使用新的配置获取方式 |
| `engine/searcher.py` | 使用新的配置获取方式 |
| `tests/conftest.py` | 更新测试 fixture |
| `.env.example` | 移除（不再需要） |

---

## 兼容性考虑

- 如果 `config.yaml` 不存在，使用默认配置
- 全局配置（OPENAI_API_KEY）仍可从环境变量读取（可选保留）
