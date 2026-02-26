# DuckKB 并发安全改造任务列表

## 阶段一：基础设施

### 1.1 公平读写锁实现
- [ ] 创建 `src/duckkb/utils/rwlock.py` 文件
- [ ] 实现 `FairReadWriteLock` 类
- [ ] 添加单元测试 `tests/test_rwlock.py`

### 1.2 配置模型更新
- [ ] 在 `src/duckkb/core/config/models.py` 添加 `DatabaseConfig`
- [ ] 更新 `GlobalConfig` 包含数据库配置

---

## 阶段二：核心改造

### 2.1 DBMixin 重构
- [ ] 修改 `src/duckkb/core/mixins/db.py`
  - [ ] 添加临时数据库文件路径管理
  - [ ] 集成 `FairReadWriteLock`
  - [ ] 实现 `execute_read()` 方法
  - [ ] 实现 `execute_write()` 方法
  - [ ] 实现 `execute_write_with_result()` 方法
  - [ ] 实现 `write_transaction()` 上下文管理器
  - [ ] 添加 `close()` 清理逻辑
  - [ ] 移除 `conn` 属性

### 2.2 SearchMixin 适配
- [ ] 修改 `src/duckkb/core/mixins/search.py`
  - [ ] 将 `self.conn.execute()` 改为 `self.execute_read()`
  - [ ] 移除 `_execute_query()` 方法

### 2.3 StorageMixin 适配
- [ ] 修改 `src/duckkb/core/mixins/storage.py`
  - [ ] 将事务逻辑改为使用 `write_transaction()`
  - [ ] 将简单写入改为 `execute_write()`

### 2.4 IndexMixin 适配
- [ ] 修改 `src/duckkb/core/mixins/index.py`
  - [ ] 将读操作改为 `execute_read()`
  - [ ] 将写操作改为 `execute_write()`

### 2.5 OntologyMixin 适配
- [ ] 修改 `src/duckkb/core/mixins/ontology.py`
  - [ ] 将 `self.conn.execute()` 改为对应方法

---

## 阶段三：测试验证

### 3.1 单元测试
- [ ] 添加 `tests/test_rwlock.py` - 读写锁测试
- [ ] 更新 `tests/test_duckdb_concurrency.py` - 集成测试

### 3.2 并发测试
- [ ] 测试多读并发
- [ ] 测试写操作独占
- [ ] 测试写操作不饥饿
- [ ] 测试临时文件清理

### 3.3 回归测试
- [ ] 运行现有测试套件确保无破坏性变更

---

## 阶段四：文档更新

- [ ] 更新 `README.md` 说明新的并发模型
- [ ] 添加迁移指南文档
