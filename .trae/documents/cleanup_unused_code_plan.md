# 项目无用代码清理计划

## 概述

本计划旨在清理 DuckKB 项目中的无用代码，包括未被使用的模块、常量和异常类。

---

## 待清理项目

### 1. 删除 `duckkb/utils/` 整个目录

**原因：** 该目录下的代码未被项目源代码使用，仅有测试文件在使用。

**涉及文件：**
- `src/duckkb/utils/__init__.py` - 几乎是空的，仅有文档字符串
- `src/duckkb/utils/text.py` - 包含 `segment_text` 和 `compute_text_hash` 函数，未被调用
- `src/duckkb/utils/file_ops.py` - 包含多个异步文件操作函数，未被调用

**验证方式：**
```bash
grep -r "from duckkb.utils" src/
grep -r "import duckkb.utils" src/
# 无匹配结果
```

---

### 2. 删除测试文件

**原因：** 对应的是未被使用的 utils 模块

**涉及文件：**
- `tests/test_text_segment.py` - 测试 `utils/text.py` 中的函数
- `tests/test_file_ops.py` - 测试 `utils/file_ops.py` 中的函数

---

### 3. 清理 `duckkb/constants.py` 中的无用常量

**原因：** 定义了但从未被使用

| 常量名称 | 用途 |
|---------|------|
| `DEFAULT_KB_DIR_NAME` | 未使用 |
| `DATA_DIR_NAME` | 未使用 |
| `DB_FILE_NAME` | 未使用 |
| `SCHEMA_FILE_NAME` | 未使用 |
| `SYS_SEARCH_TABLE` | 未使用 |
| `SYS_CACHE_TABLE` | 未使用 |
| `BACKUP_DIR_NAME` | 未使用 |
| `MAX_BACKUPS` | 未使用 |
| `SYNC_STATE_FILE` | 未使用 |
| `CACHE_EXPIRE_DAYS` | 未使用 |
| `MAX_ERROR_FEEDBACK` | 未使用 |
| `PREFETCH_MULTIPLIER` | 未使用 |
| `VALID_CARDINALITIES` | 未使用 |

**验证方式：**
```bash
grep -r "DEFAULT_KB_DIR_NAME\|DATA_DIR_NAME\|..." src/
# 仅在 constants.py 中出现定义
```

---

### 4. 清理 `duckkb/exceptions.py` 中的无用异常类

**原因：** 定义了但从未被抛出或捕获

| 异常类名称 | 用途 |
|-----------|------|
| `SyncError` | 未被 raise 或 except |
| `TableNotFoundError` | 未被 raise 或 except |
| `RecordNotFoundError` | 未被 raise 或 except |

**验证方式：**
```bash
grep -r "SyncError\|TableNotFoundError\|RecordNotFoundError" src/
# 仅在 exceptions.py 中出现定义
```

---

## 实施步骤

1. **删除 utils 模块**
   - 删除 `src/duckkb/utils/` 目录

2. **删除测试文件**
   - 删除 `tests/test_text_segment.py`
   - 删除 `tests/test_file_ops.py`

3. **清理 constants.py**
   - 移除 13 个无用常量

4. **清理 exceptions.py**
   - 移除 3 个无用异常类

5. **验证**
   - 运行 `ruff check src/` 确保无错误
   - 运行测试确保功能正常

---

## 风险评估

- **低风险**：删除的代码均为"死代码"，不会影响现有功能
- **注意事项**：需确认 pyproject.toml 中无对已删除模块的特殊配置
