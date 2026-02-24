# DuckKB 后续优化计划

## 当前状态

已完成第一轮代码坏味道修复：

* ✅ `print()` 改为 `logging`

* ✅ 版本号动态读取

* ✅ 裸异常捕获修复

* ✅ 魔法值提取到 `constants.py`

* ✅ 占位符代码删除

* ✅ 测试反模式修复（使用 `monkeypatch`）

* ✅ 哈希计算提取为工具函数

* ✅ 类型标注完善

**当前测试覆盖率**: 58%（目标 80%）

***

## 待优化项目

### 🔴 高优先级

#### 1. 全局状态统一管理

**问题**: 多处仍使用旧的全局变量模式

| 文件                                                                                          | 当前状态                                  | 问题              |
| ------------------------------------------------------------------------------------------- | ------------------------------------- | --------------- |
| [text.py:5](file:///c:/Users/baiyihuan/code/duckkb/src/duckkb/utils/text.py#L5)             | `from duckkb.config import settings`  | 使用旧的全局 settings |
| [text.py:8](file:///c:/Users/baiyihuan/code/duckkb/src/duckkb/utils/text.py#L8)             | `_jieba_initialized = False`          | 模块级全局状态         |
| [embedding.py:12](file:///c:/Users/baiyihuan/code/duckkb/src/duckkb/utils/embedding.py#L12) | `_client: AsyncOpenAI \| None = None` | 模块级全局状态         |
| [db.py:20](file:///c:/Users/baiyihuan/code/duckkb/src/duckkb/db.py#L20)                     | `db_manager = DBManager()`            | 模块级全局实例         |

**解决方案**: 统一使用 `AppContext` 管理所有全局资源

```python
class AppContext:
    def __init__(self, kb_path: Path):
        self.kb_path = kb_path.resolve()
        self.kb_config = KBConfig.from_yaml(kb_path)
        self.global_config = GlobalConfig()
        self._openai_client: AsyncOpenAI | None = None
        self._jieba_initialized = False
        self._db_manager: DBManager | None = None
    
    @property
    def openai_client(self) -> AsyncOpenAI:
        if self._openai_client is None:
            self._openai_client = AsyncOpenAI(...)
        return self._openai_client
    
    @property
    def db_manager(self) -> DBManager:
        if self._db_manager is None:
            self._db_manager = DBManager(self.kb_path)
        return self._db_manager
```

***

#### 2. 提升测试覆盖率至 80%

**当前未覆盖模块**:

| 模块              | 当前覆盖率 | 主要缺失         |
| --------------- | ----- | ------------ |
| `exceptions.py` | 0%    | 完全未测试        |
| `main.py`       | 0%    | CLI 入口未测试    |
| `mcp/server.py` | 0%    | MCP 服务未测试    |
| `schema.py`     | 13%   | Schema 初始化逻辑 |
| `searcher.py`   | 68%   | 搜索回退逻辑       |
| `embedding.py`  | 67%   | OpenAI 调用逻辑  |

**需要新增测试**:

* `test_exceptions.py`: 测试异常类继承和消息

* `test_main.py`: 测试 CLI 命令

* `test_schema.py`: 测试 schema 初始化

* 补充 `test_searcher.py`: 测试混合搜索和回退逻辑

***

### 🟠 中优先级

#### 3. 模块职责拆分

**问题**: [indexer.py](file:///c:/Users/baiyihuan/code/duckkb/src/duckkb/engine/indexer.py) 包含 289 行，职责过多

**拆分方案**:

```
src/duckkb/engine/
├── __init__.py
├── sync.py          # sync_knowledge_base, _process_file, _read_records
├── importer.py      # validate_and_import
├── cache.py         # clean_cache, _execute_gc
├── searcher.py      # (保持不变)
└── indexer.py       # 仅保留 _bulk_insert (或删除)
```

***

#### 4. SQL 模板提取

**问题**: [searcher.py:57-101](file:///c:/Users/baiyihuan/code/duckkb/src/duckkb/engine/searcher.py#L57-L101) SQL 通过 f-string 拼接

**解决方案**: 将 SQL 模板提取为常量

```python
VECTOR_SEARCH_CTE = """
vector_search AS (
    SELECT 
        s.rowid, 
        array_cosine_similarity(c.embedding, ?::FLOAT[{dim}]) as score
    FROM _sys_search s
    JOIN _sys_cache c ON s.embedding_id = c.content_hash
    WHERE 1=1 {filter_clause}
    ORDER BY score DESC LIMIT ?
)
"""
```

***

### 🟡 低优先级

#### 5. 日志规范化

**问题**: 日志消息格式不一致

| 位置              | 当前                                             | 建议    |
| --------------- | ---------------------------------------------- | ----- |
| indexer.py:29   | `f"Data directory {data_dir} does not exist."` | 保持一致  |
| indexer.py:51   | `f"Syncing table {table_name}..."`             | ✅     |
| searcher.py:127 | `f"Hybrid search failed, falling back..."`     | 添加上下文 |

***

## 实施计划

### Phase 1: 全局状态统一 (预计修改 5 个文件)

1. 扩展 `AppContext` 类
2. 重构 `text.py` 使用 `AppContext`
3. 重构 `embedding.py` 使用 `AppContext`
4. 重构 `db.py` 使用 `AppContext`
5. 更新所有调用点

### Phase 2: 测试覆盖率提升 (预计新增 3 个测试文件)

1. 创建 `test_exceptions.py`
2. 创建 `test_main.py`
3. 扩展 `test_schema.py`
4. 扩展 `test_searcher.py`

### Phase 3: 模块拆分 (预计修改 4 个文件)

1. 创建 `engine/sync.py`
2. 创建 `engine/importer.py`
3. 创建 `engine/cache.py`
4. 更新 `__init__.py` 导出

### Phase 4: SQL 模板提取 (预计修改 1 个文件)

1. 提取 SQL 常量到 `searcher.py` 顶部

***

## 风险评估

| 风险     | 影响       | 缓解措施                  |
| ------ | -------- | --------------------- |
| 全局状态重构 | 可能影响现有测试 | 先写测试再重构               |
| 模块拆分   | 导入路径变更   | 保持 `__init__.py` 兼容导出 |
| 测试覆盖率  | 需要模拟外部依赖 | 使用 mock 隔离 OpenAI API |

***

## 验收标准

* [ ] 所有测试通过 (`uv run pytest tests -v`)

* [ ] 测试覆盖率 ≥ 80%

* [ ] Ruff 检查通过 (`uv run ruff check src tests`)

* [ ] 无全局模块级可变状态

* [ ] 模块职责单一，每个文件 < 200 行

