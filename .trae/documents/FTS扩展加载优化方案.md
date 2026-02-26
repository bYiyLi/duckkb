# FTS 扩展加载问题优化方案

## 问题分析

当前实现存在问题：
1. DuckDB FTS 扩展需要在写连接中安装（`INSTALL fts`），然后才能加载（`LOAD fts`）
2. 只读连接无法安装扩展，只能加载已安装的扩展
3. 当前代码在只读连接中尝试加载 FTS 失败后静默忽略，导致混合搜索回退到纯向量搜索

## 解决方案对比

### 方案 A：初始化时预安装 FTS 扩展 ✅ 推荐

**实现思路：**
1. 在 `sync_schema()` 方法中添加 FTS 扩展安装逻辑
2. FTS 扩展安装后持久化到数据库文件中
3. 只读连接可以直接 `LOAD fts` 加载已安装的扩展

**优点：**
- 干净，不需要回退逻辑
- 符合 DuckDB 最佳实践
- 保持完整的混合搜索功能

**缺点：**
- 需要确保初始化时已安装

**代码修改：**
```python
# ontology.py - sync_schema() 方法
def sync_schema(self) -> None:
    # 首先安装 FTS 扩展
    self._ensure_fts_extension()
    # 然后创建表...
    
def _ensure_fts_extension(self) -> None:
    """确保 FTS 扩展已安装。"""
    conn = self._create_write_connection()
    try:
        conn.execute("INSTALL fts")
        conn.execute("LOAD fts")
    finally:
        conn.close()
```

```python
# db.py - _create_read_connection() 方法
def _create_read_connection(self) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(str(self.db_path), read_only=True)
    conn.execute("LOAD fts")  # 现在应该成功
    return conn
```

---

### 方案 B：使用 DuckDB 内置字符串匹配

**实现思路：**
- 不使用 FTS 扩展，使用 `LIKE`、`GLOB` 或正则表达式
- 在 `fts_content` 字段上进行模糊匹配

**优点：**
- 无外部依赖
- 所有连接模式都可用

**缺点：**
- 功能较弱，无 BM25 排序
- 性能较差

---

### 方案 C：保持回退但优化提示

**实现思路：**
- 保持当前的回退逻辑
- 添加明确的警告日志
- 在配置中添加 FTS 可用状态标记

**优点：**
- 健壮，不会因扩展问题导致搜索失败

**缺点：**
- 功能降级
- 用户体验不佳

---

## 推荐方案：A + C 组合

1. **主要策略**：在初始化时预安装 FTS 扩展（方案 A）
2. **兜底策略**：如果 FTS 仍然不可用，优雅降级（方案 C）

### 具体修改

#### 1. 修改 `ontology.py`

```python
def sync_schema(self) -> None:
    """同步表结构到数据库。"""
    # 首先确保 FTS 扩展已安装
    self._ensure_fts_extension()
    
    # 创建节点表
    for _node_name, node_type in self.ontology.nodes.items():
        ddl = self._generate_node_ddl(node_type)
        self.execute_write(ddl)
    
    # 创建边表
    for edge_name, edge_type in self.ontology.edges.items():
        table_name = f"edge_{edge_name}"
        ddl = self._generate_edge_ddl(edge_name, edge_type)
        self.execute_write(ddl)
    
    logger.info(f"Schema synced: {len(self.ontology.nodes)} nodes, {len(self.ontology.edges)} edges")

def _ensure_fts_extension(self) -> None:
    """确保 FTS 扩展已安装并可用。"""
    try:
        conn = duckdb.connect(str(self.db_path), read_only=False)
        try:
            conn.execute("INSTALL fts")
            conn.execute("LOAD fts")
            logger.debug("FTS extension installed and loaded")
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"Failed to install FTS extension: {e}. Full-text search may not be available.")
```

#### 2. 修改 `db.py`

```python
def _create_read_connection(self) -> duckdb.DuckDBPyConnection:
    """创建只读连接。"""
    conn = duckdb.connect(str(self.db_path), read_only=True)
    try:
        conn.execute("LOAD fts")
    except Exception as e:
        logger.debug(f"FTS extension not available in read-only mode: {e}")
    return conn
```

#### 3. 修改 `search.py`

保持当前的回退逻辑，但优化日志级别：

```python
except Exception as e:
    if "fts_match" in str(e):
        logger.info("FTS not available, using vector-only search")
        # 回退到纯向量搜索
    else:
        logger.error(f"Hybrid search failed: {e}")
        raise DatabaseError(f"Hybrid search failed: {e}") from e
```

### 测试验证

1. 验证 FTS 扩展在初始化后可用
2. 验证只读连接可以加载 FTS
3. 验证混合搜索正常工作
4. 验证回退逻辑仍然有效
