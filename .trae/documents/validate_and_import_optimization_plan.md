# validate_and_import 优化方案

## 1. 现状分析

当前的 `validate_and_import` 实现存在以下问题：
1.  **内存占用高**：一次性读取整个文件到内存，对于大文件会导致 OOM。
2.  **性能瓶颈**：
    *   单次调用 `add_documents` 处理所有数据，虽然 `add_documents` 内部有批处理，但缺乏对大文件的流式支持。
    *   `add_documents` 默认每次调用都会触发 `sync_db_to_file`，如果改为批处理调用，会导致频繁的磁盘 I/O。
3.  **验证不足**：仅验证了 `id` 字段，未利用 Ontology 定义的 Schema 进行字段校验。
4.  **健壮性**：临时文件清理逻辑在异常发生时可能被跳过。

## 2. 优化目标

1.  **流式处理**：使用异步生成器按行读取文件，降低内存占用。
2.  **批量写入**：分批次解析和验证数据，分批次调用 `add_documents`，减少峰值内存。
3.  **Schema 校验**：结合 Ontology 配置，对数据进行结构校验。
4.  **I/O 优化**：控制 `sync_db_to_file` 的调用时机，仅在所有批次完成后统一回写文件。
5.  **健壮性提升**：完善错误处理和资源清理机制。

## 3. 详细计划

### 3.1 基础设施增强

*   **修改 `duckkb/utils/file_ops.py`**：
    *   新增 `read_file_lines` 函数，返回异步生成器，用于流式读取文件。
*   **修改 `duckkb/engine/crud.py`**：
    *   修改 `add_documents` 函数签名，增加 `sync_file: bool = True` 参数。
    *   在函数末尾根据 `sync_file` 参数决定是否调用 `sync_db_to_file`。

### 3.2 业务逻辑重构

*   **重构 `duckkb/mcp/server.py` 中的 `validate_and_import`**：
    *   引入 `BATCH_SIZE` 常量（如 100）。
    *   使用 `try...finally` 块确保临时文件清理。
    *   获取当前表的 Schema (从 `AppContext.get().kb_config.ontology`)。
    *   实现流式处理循环：
        *   逐行读取 JSONL。
        *   解析 JSON。
        *   **校验逻辑**：
            *   基础校验：是否为对象，是否有 `id`。
            *   Schema 校验：如果存在 Ontology 定义，校验字段类型和必要性。
        *   收集有效记录到 buffer。
        *   当 buffer 达到 `BATCH_SIZE` 时：
            *   调用 `add_documents(..., sync_file=False)`。
            *   清空 buffer。
            *   记录成功/失败数量。
    *   处理剩余 buffer。
    *   循环结束后，显式调用 `sync_db_to_file`。
    *   返回包含详细统计（处理总数、成功数、失败数、错误采样）的 JSON 结果。

## 4. 验证计划

1.  **单元测试**：
    *   构造包含 1000+ 条数据的大文件进行导入测试。
    *   构造包含非法格式、缺失字段、类型错误的数据进行校验测试。
2.  **集成测试**：
    *   验证导入后数据是否能被搜索到。
    *   验证数据文件是否正确落地。
