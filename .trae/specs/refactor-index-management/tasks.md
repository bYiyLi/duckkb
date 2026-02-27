# Tasks

- [x] Task 1: 分析 import_.py 中需要移动的方法
  - [x] 识别 `_rebuild_index_from_cache` 及其依赖的辅助方法
  - [x] 确认 `_chunk_text_sync` 和 `_compute_hash_sync` 是否已在 index.py 中有对应方法
  - [x] 列出完整的方法移动清单
  
  **分析结果**：
  - `_rebuild_index_from_cache` 需要移动到 index.py
  - `_chunk_text_sync` 和 `_compute_hash_sync` 被 import_.py 中其他方法使用，需保留
  - index.py 已有 `_chunk_text` 和 `_compute_hash` 方法，可直接复用

- [x] Task 2: 将索引重建方法移动到 index.py
  - [x] 将 `_rebuild_index_from_cache` 移动到 `IndexMixin`
  - [x] 重命名为 `rebuild_index_from_cache`（去掉下划线前缀，表示可被外部调用）
  - [x] 复用 index.py 中已有的 `_chunk_text` 和 `_compute_hash` 方法
  - [x] 更新方法注释

- [x] Task 3: 从 import_.py 中移除已移动的方法
  - [x] 删除 `_rebuild_index_from_cache` 方法
  - [x] 删除不再使用的 `_chunk_text_sync` 和 `_compute_hash_sync` 方法
  - [x] 确保没有其他方法依赖这些被删除的方法

- [x] Task 4: 更新 engine.py 中的调用
  - [x] 确认 `await self._rebuild_index_from_cache()` 调用仍然有效（通过 Mixin 继承）
  - [x] 如果需要，更新方法名

- [x] Task 5: 验证重构正确性
  - [x] 运行 `uv run duckkb serve` 确认启动正常
  - [x] 运行测试确认功能正常

# Task Dependencies
- Task 2 依赖 Task 1
- Task 3 依赖 Task 2
- Task 4 依赖 Task 3
- Task 5 依赖 Task 4
