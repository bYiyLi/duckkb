"""FTS 简单测试。"""

import duckdb

conn = duckdb.connect(":memory:")
conn.execute("INSTALL fts")
conn.execute("LOAD fts")

conn.execute("""
CREATE TABLE test_fts (
    id INTEGER PRIMARY KEY,
    content VARCHAR,
    fts_content VARCHAR
)
""")

conn.execute("""
INSERT INTO test_fts VALUES 
    (1, '张明是一名工程师', '张明 是 一名 工程师'),
    (2, '李婷是产品经理', '李婷 是 产品 经理'),
    (3, '王强是架构师', '王强 是 架构师')
""")

print("测试数据:")
rows = conn.execute("SELECT * FROM test_fts").fetchall()
for row in rows:
    print(f"  {row}")

print("\n创建 FTS 索引...")
conn.execute("PRAGMA create_fts_index('test_fts', 'id', 'fts_content')")
print("FTS 索引创建成功")

print("\n测试 FTS 查询 (不带参数):")
sql = """
SELECT id, content, fts_main_test_fts.match_bm25(id, '张明') as score
FROM test_fts
WHERE fts_content IS NOT NULL
"""
rows = conn.execute(sql).fetchall()
print(f"结果: {len(rows)} 条")
for row in rows:
    print(f"  {row}")

print("\n测试 FTS 查询 (带参数):")
sql = """
SELECT id, content, fts_main_test_fts.match_bm25(id, ?) as score
FROM test_fts
WHERE fts_content IS NOT NULL
"""
rows = conn.execute(sql, ["张明"]).fetchall()
print(f"结果: {len(rows)} 条")
for row in rows:
    print(f"  {row}")

print("\n测试 FTS 查询 (过滤 NULL score):")
sql = """
SELECT id, content, fts_main_test_fts.match_bm25(id, ?) as score
FROM test_fts
WHERE fts_content IS NOT NULL
  AND fts_main_test_fts.match_bm25(id, ?) IS NOT NULL
ORDER BY score DESC
"""
rows = conn.execute(sql, ["张明", "张明"]).fetchall()
print(f"结果: {len(rows)} 条")
for row in rows:
    print(f"  {row}")

conn.close()
