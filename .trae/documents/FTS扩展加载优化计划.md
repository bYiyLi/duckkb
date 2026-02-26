# FTS 扩展加载优化计划

## 问题背景

当前 DuckKB 的 FTS（全文搜索）扩展在只读连接中无法加载，导致混合搜索回退到纯向量搜索。这是因为：

1. DuckDB FTS 扩展需要先 `INSTALL fts`（需要写权限），然后才能 `LOAD fts`
2. 只读连接无法安装扩展
3. 当前代码在只读连接中静默忽略加载失败

## 解决方案

采用 **方案 A + C 组合**：预安装 FTS + 优雅降级

### 修改文件

1. **`src/duckkb/core/mixins/ontology.py`**

   * 在 `sync_schema()` 方法中添加 `_ensure_fts_extension()` 调用

   * 新增 `_ensure_fts_extension()` 方法，在写连接中安装 FTS 扩展

2. **`src/duckkb/core/mixins/db.py`**

   * `_create_read_connection()` 保持尝试加载 FTS，失败时记录调试日志

3. **`src/duckkb/core/mixins/search.py`**

   * 保持当前的回退逻辑

   * 优化日志级别（从 debug 改为 info）

### 实施步骤

1. 修改 `ontology.py` 添加 FTS 预安装逻辑
2. 修改 `search.py` 优化日志级别
3. 运行测试验证功能正常

### 预期结果

* FTS 扩展在数据库初始化时安装

* 只读连接可以成功加载 FTS

* 混合搜索正常工作

* 即使 FTS 不可用，仍可优雅降级到纯向量搜索

