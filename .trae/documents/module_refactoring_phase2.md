# 模块结构重构计划 (Phase 2)

根据用户指示，我们将进一步调整 `duckkb` 的模块结构，将执行引擎归入数据库层，并将本体定义归入引擎层。

## 目标结构

```text
duckkb/
├── database/
│   ├── connection.py
│   ├── schema.py
│   ├── persister.py
│   ├── engine/              # [MOVED] 原 duckkb/engine (执行层)
│   │   ├── __init__.py
│   │   ├── manager.py
│   │   ├── search.py
│   │   ├── loader.py
│   │   ├── ...
├── engine/                  # [RECREATED] 新的引擎层 (定义层)
│   ├── ontology/            # [MOVED] 原 duckkb/ontology
│   │   ├── __init__.py
│   │   ├── engine.py
│   │   ├── ...
├── mcp/
└── ...
```

## 变更详情

### 1. 移动 `duckkb.engine` -> `duckkb.database.engine`

将负责数据操作的核心模块移动到 `database` 包下，作为数据库的执行引擎。

-   **源路径**: `src/duckkb/engine/`
-   **目标路径**: `src/duckkb/database/engine/`
-   **涉及模块**:
    -   `manager.py`
    -   `loader.py`
    -   `search.py`
    -   `backup.py`
    -   `cache.py`
    -   `migration.py`

### 2. 移动 `duckkb.ontology` -> `duckkb.engine.ontology`

将本体定义模块移动到 `engine` 包下（注意：这里的 `engine` 是在步骤 1 移走旧 `engine` 后重新创建的包）。

-   **源路径**: `src/duckkb/ontology/`
-   **目标路径**: `src/duckkb/engine/ontology/`
-   **涉及模块**:
    -   `_models.py`, `_schema.py`, `_validator.py`
    -   `engine.py` (OntologyEngine)

## 执行步骤

1.  **文件移动**:
    -   `mkdir -p src/duckkb/database/engine`
    -   `mv src/duckkb/engine/* src/duckkb/database/engine/`
    -   `rm -rf src/duckkb/engine` (确保清理干净)
    -   `mkdir -p src/duckkb/engine`
    -   `mv src/duckkb/ontology src/duckkb/engine/ontology`

2.  **代码修正 (Search & Replace)**:
    -   **Imports 更新**:
        -   `duckkb.engine` -> `duckkb.database.engine`
        -   `duckkb.ontology` -> `duckkb.engine.ontology`
    -   **特殊处理**:
        -   检查 `duckkb/database/engine/__init__.py` 中的相对引用。
        -   检查 `duckkb/engine/ontology/__init__.py` 中的相对引用。

3.  **验证**:
    -   运行 `uv run pytest` 确保重构后系统功能正常。

## 影响范围

-   `mcp/server.py`: 主要入口，需大量修改 imports。
-   `config.py`: 引用了 Ontology。
-   `database/schema.py`: 引用了 OntologyEngine。
-   `database/engine/migration.py`: 引用了 Ontology。
-   `tests/*`: 测试文件中的所有引用。
