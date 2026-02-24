# 模块结构修正计划 (Phase 3)

用户指出 `src/duckkb/engine/ontology/` 位置不对。根据上下文，用户之前的意图是将 `engine` 移入 `database`，并将 `ontology` 放入 `engine`。

由于 `engine` 已经被移动到了 `database/engine`，因此 `ontology` 也应该跟随进入该目录，而不是留在根目录下的空 `engine` 包中。

## 目标结构

```text
duckkb/
├── database/
│   ├── engine/              # 执行引擎
│   │   ├── ontology/        # [MOVED] 本体定义 (原 duckkb/engine/ontology)
│   │   ├── manager.py
│   │   ├── search.py
│   │   ├── ...
│   ├── connection.py
│   ├── schema.py
│   └── ...
├── engine/                  # [REMOVED] 将被删除
├── mcp/
└── ...
```

## 变更详情

### 1. 移动 `duckkb.engine.ontology` -> `duckkb.database.engine.ontology`

将本体定义模块移动到新的引擎位置。

-   **源路径**: `src/duckkb/engine/ontology/`
-   **目标路径**: `src/duckkb/database/engine/ontology/`

### 2. 清理

-   删除空的 `src/duckkb/engine/` 目录。

### 3. 更新引用

将所有引用从 `duckkb.engine.ontology` 更新为 `duckkb.database.engine.ontology`。

-   **涉及文件**:
    -   `src/duckkb/config.py`
    -   `src/duckkb/database/schema.py`
    -   `src/duckkb/database/engine/manager.py`
    -   `src/duckkb/database/engine/loader.py`
    -   `src/duckkb/database/engine/migration.py`
    -   `src/duckkb/database/engine/ontology/__init__.py` (内部引用修正)
    -   `tests/*`

## 执行步骤

1.  **移动文件**:
    -   `mv src/duckkb/engine/ontology src/duckkb/database/engine/ontology`
    -   `rmdir src/duckkb/engine`

2.  **更新代码**:
    -   全局替换 `from duckkb.engine.ontology` -> `from duckkb.database.engine.ontology`
    -   全局替换 `import duckkb.engine.ontology` -> `import duckkb.database.engine.ontology`

3.  **验证**:
    -   运行 `uv run pytest`。
