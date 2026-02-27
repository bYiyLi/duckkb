# Checklist

## 搜索功能修复

- [x] 混合搜索返回结果字段映射正确（source_table 为表名、source_id 为整数、source_field 为字段名、chunk_seq 为整数、content 为字符串）
- [x] 全文搜索能够返回匹配结果（非空数组）
- [x] 向量搜索功能正常工作

## 图遍历功能修复

- [x] `get_neighbors` 返回的邻居节点包含正确的字段名（无 col_2, col_3 等）
- [x] `direction="both"` 时邻居节点不重复
- [x] `extract_subgraph` 返回的边信息包含完整属性
- [x] `traverse` 返回的节点包含正确字段名
- [x] `find_paths` 返回的节点包含正确字段名

## 原始记录获取修复

- [x] `get_source_record` 能正确返回包含 datetime 字段的记录
- [x] datetime 字段序列化为 ISO 格式字符串

## SQL 查询功能修复

- [x] UPDATE 语句被正确拦截并返回明确错误提示
- [x] DELETE 语句被正确拦截并返回明确错误提示
- [x] INSERT 语句被正确拦截并返回明确错误提示
- [x] SELECT 语句正常执行

## 参数校验修复

- [x] 负数 limit 参数在参数校验阶段被拦截
- [x] 负数 max_depth 参数在参数校验阶段被拦截
- [x] 无效 direction 参数返回明确错误提示

## 测试覆盖

- [x] 所有修复项有对应的测试用例
- [x] 测试用例通过 `uv run pytest tests/ -v` 验证
