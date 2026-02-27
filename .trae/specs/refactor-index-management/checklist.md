# Checklist

- [x] `_rebuild_index_from_cache` 方法已移动到 `IndexMixin`
- [x] `import_.py` 中已删除 `_rebuild_index_from_cache` 方法
- [x] `import_.py` 中保留 `_chunk_text_sync` 和 `_compute_hash_sync` 方法（被其他方法使用）
- [x] `IndexMixin` 复用已有的 `_chunk_text` 和 `_compute_hash` 方法
- [x] `engine.py` 中的调用仍然有效（通过 Mixin 继承）
- [x] 启动测试通过：`uv run duckkb serve` 正常启动
- [x] 启动时间优化：从 7 秒减少到 4 秒（批量查询缓存生效）
