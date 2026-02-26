# FTS 扩展在只读连接中加载问题修复方案

## 问题分析

### 当前行为

```
┌─────────────────────────────────────────────────────────────┐
│                    当前实现                                   │
├─────────────────────────────────────────────────────────────┤
│  _create_write_connection():                                 │
│    INSTALL fts → LOAD fts (成功)                             │
│                                                             │
│  _create_read_connection():                                 │
│    LOAD fts (静默失败) ← 问题所在！                           │
└─────────────────────────────────────────────────────────────┘
```

### 问题根源

1. **DuckDB FTS 扩展机制**：
   - `INSTALL fts`：下载并安装扩展到 DuckDB 全局目录（需要写权限）
   - `LOAD fts`：加载已安装的扩展到当前连接

2. **时序问题**：
   - 只读连接可能在写连接之前创建（如初始化时读取数据）
   - 如果 FTS 扩展未预先安装，只读连接的 `LOAD fts` 会失败

3. **当前后果**：
   - 混合搜索静默回退到纯向量搜索（用户体验下降）
   - 纯全文检索直接抛出异常（功能不可用）

### 场景分析

| 场景 | FTS 状态 | 只读连接行为 |
|------|---------|-------------|
| 首次使用，写操作先执行 | 已安装 | ✅ 正常加载 |
| 首次使用，读操作先执行 | 未安装 | ❌ 加载失败 |
| 后续使用（扩展已全局安装） | 已安装 | ✅ 正常加载 |

---

## 解决方案

### 推荐方案：初始化时确保 FTS 扩展已安装

**核心思路**：在引擎初始化阶段，通过临时写连接确保 FTS 扩展已安装，然后再进行其他操作。

```
┌─────────────────────────────────────────────────────────────┐
│                    修复后实现                                 │
├─────────────────────────────────────────────────────────────┤
│  initialize() / async_initialize():                         │
│    _ensure_fts_installed() ← 新增：确保 FTS 扩展已安装        │
│    sync_schema()                                            │
│    create_index_tables()                                    │
│                                                             │
│  _ensure_fts_installed():                                   │
│    创建临时写连接 → INSTALL fts → 关闭连接                    │
│                                                             │
│  _create_read_connection():                                 │
│    LOAD fts (现在应该成功)                                   │
└─────────────────────────────────────────────────────────────┘
```

### 方案优势

1. **时序正确**：确保在任何只读连接创建之前，FTS 扩展已安装
2. **一次安装**：只在初始化时安装一次，后续连接创建无需重复检查
3. **逻辑清晰**：职责明确，初始化负责准备工作
4. **向后兼容**：不改变现有 API 和使用方式
5. **明确失败**：安装失败时立即抛出异常，避免后续静默降级带来的困惑

---

## 实现计划

### 1. 修改 `DBMixin` 类

**文件**: `src/duckkb/core/mixins/db.py`

添加 `_ensure_fts_installed()` 方法：

```python
def _ensure_fts_installed(self) -> None:
    """确保 FTS 扩展已安装。

    通过临时写连接安装 FTS 扩展。
    如果扩展已安装，此操作是幂等的（不会重复下载）。

    Raises:
        DatabaseError: FTS 扩展安装失败时抛出。
    """
    conn = duckdb.connect(str(self.db_path), read_only=False)
    try:
        conn.execute("INSTALL fts")
        logger.debug("FTS extension installed successfully")
    except Exception as e:
        logger.error(f"Failed to install FTS extension: {e}")
        raise DatabaseError(f"Failed to install FTS extension: {e}") from e
    finally:
        conn.close()
```

### 2. 修改 `Engine` 类

**文件**: `src/duckkb/core/engine.py`

在 `initialize()` 和 `async_initialize()` 中调用：

```python
def initialize(self) -> Self:
    """初始化引擎。"""
    self._ensure_fts_installed()  # 新增：确保 FTS 扩展已安装
    self.sync_schema()
    self.create_index_tables()
    # ...

async def async_initialize(self) -> Self:
    """异步初始化引擎。"""
    self._ensure_fts_installed()  # 新增：确保 FTS 扩展已安装
    self.sync_schema()
    self.create_index_tables()
    # ...
```

### 3. 改进只读连接的错误处理

**文件**: `src/duckkb/core/mixins/db.py`

改进 `_create_read_connection()` 的日志记录：

```python
def _create_read_connection(self) -> duckdb.DuckDBPyConnection:
    """创建只读连接。"""
    conn = duckdb.connect(str(self.db_path), read_only=True)
    try:
        conn.execute("LOAD fts")
    except Exception as e:
        logger.debug(f"Failed to load FTS extension in read-only connection: {e}")
    return conn
```

---

## 边界情况处理

### 1. FTS 安装失败（网络问题）

- **行为**：`_ensure_fts_installed()` 记录错误日志并抛出 `DatabaseError`
- **后果**：引擎初始化失败，用户需要检查网络或 DuckDB 配置
- **评估**：明确失败原因，避免后续静默降级带来的困惑

### 2. 用户未调用 initialize()

- **行为**：FTS 扩展可能未安装，只读连接加载失败
- **后果**：同当前行为
- **评估**：这是用户错误使用，文档应说明必须调用 `initialize()` 或使用上下文管理器

### 3. 多个 Engine 实例

- **行为**：DuckDB 扩展是全局安装的，第一个实例安装后，后续实例无需重复安装
- **评估**：无问题

---

## 测试计划

### 单元测试

1. **测试 `_ensure_fts_installed()` 方法**
   - 首次安装成功
   - 重复安装（幂等性）
   - 安装失败时抛出 `DatabaseError`

2. **测试只读连接创建**
   - FTS 已安装时加载成功
   - FTS 未安装时加载失败（但不抛出异常）

### 集成测试

1. **测试初始化流程**
   - `initialize()` 后只读连接可以加载 FTS
   - `async_initialize()` 后只读连接可以加载 FTS

2. **测试混合搜索**
   - FTS 可用时执行混合搜索
   - FTS 不可用时回退到纯向量搜索

---

## 变更文件清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `src/duckkb/core/mixins/db.py` | 修改 | 添加 `_ensure_fts_installed()` 方法，改进日志 |
| `src/duckkb/core/engine.py` | 修改 | 在初始化方法中调用 `_ensure_fts_installed()` |

---

## 风险评估

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|-------|------|---------|
| 网络问题导致安装失败 | 低 | 高 | 明确错误信息，用户可重试 |
| 用户未调用 initialize() | 低 | 低 | 文档说明，上下文管理器 |
| DuckDB 版本兼容性 | 低 | 高 | 测试覆盖 |

---

## 总结

此方案通过在引擎初始化阶段确保 FTS 扩展已安装，解决了只读连接无法加载 FTS 的问题。方案简单、清晰、向后兼容，安装失败时立即抛出异常，避免后续静默降级带来的困惑。
