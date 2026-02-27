"""FTS 调试脚本。"""

import asyncio
from pathlib import Path

from duckkb.core.engine import Engine


async def main():
    """测试 FTS 功能。"""
    kb_path = Path(__file__).parent / ".duckkb" / "default"

    engine = Engine(kb_path=kb_path)
    await engine.async_initialize()

    rows = engine.execute_read(
        "SELECT id, source_table, source_field, content, fts_content FROM _sys_search_index LIMIT 5"
    )
    print(f"索引表数据 (共 {len(rows)} 条):")
    for row in rows:
        print(f"  ID: {row[0]}")
        print(f"  source_table: {row[1]}")
        print(f"  source_field: {row[2]}")
        print(f"  content: {row[3][:80] if row[3] else 'NULL'}")
        print(f"  fts_content: {row[4][:80] if row[4] else 'NULL'}")
        print(f"  fts_content 是否包含空格: {' ' in (row[4] or '')}")
        print()

    fts_count = engine.execute_read(
        "SELECT COUNT(*) FROM _sys_search_index WHERE fts_content IS NOT NULL"
    )
    print(f"fts_content 非空的记录数: {fts_count[0][0]}")

    try:
        rows = engine.execute_read(
            "SELECT * FROM duckdb_fts() WHERE table_name = '_sys_search_index'"
        )
        print(f"\nFTS 索引信息: {rows}")
    except Exception as e:
        print(f"\n获取 FTS 索引信息失败: {e}")

    try:
        print("\n尝试手动创建 FTS 索引...")
        engine.rebuild_fts_index()
        print("FTS 索引创建成功")
    except Exception as e:
        print(f"FTS 索引创建失败: {e}")
        import traceback
        traceback.print_exc()

    try:
        print("\n测试简单的 FTS 查询...")
        sql = """
        SELECT 
            id, source_table, content, fts_content,
            fts_main__sys_search_index.match_bm25(id, '张明') as score
        FROM _sys_search_index
        WHERE fts_content IS NOT NULL
        LIMIT 5
        """
        rows = engine.execute_read(sql)
        print(f"简单 FTS 查询结果: {len(rows)} 条")
        for row in rows:
            print(f"  ID: {row[0]}, score: {row[4]}")
    except Exception as e:
        print(f"简单 FTS 查询失败: {e}")
        import traceback
        traceback.print_exc()

    try:
        print("\n测试带参数的 FTS 查询...")
        sql = """
        SELECT 
            id, source_table, content, fts_content,
            fts_main__sys_search_index.match_bm25(id, ?) as score
        FROM _sys_search_index
        WHERE fts_content IS NOT NULL
        LIMIT 5
        """
        rows = engine.execute_read(sql, ["张明"])
        print(f"带参数 FTS 查询结果: {len(rows)} 条")
        for row in rows:
            print(f"  ID: {row[0]}, score: {row[4]}")
    except Exception as e:
        print(f"带参数 FTS 查询失败: {e}")
        import traceback
        traceback.print_exc()

    try:
        print("\n测试 FTS 搜索...")
        results = await engine.fts_search("张明", limit=5)
        print(f"FTS 搜索结果: {results}")
    except Exception as e:
        print(f"FTS 搜索失败: {e}")
        import traceback
        traceback.print_exc()

    try:
        print("\n测试原始 SQL...")
        sql = """
        SELECT 
            source_table, source_id, source_field, chunk_seq, content,
            fts_main__sys_search_index.match_bm25(id, ?) as score
        FROM _sys_search_index
        WHERE fts_content IS NOT NULL
          AND fts_main__sys_search_index.match_bm25(id, ?) IS NOT NULL
        ORDER BY score DESC
        LIMIT ?
        """
        rows = engine.execute_read(sql, ["张明", "张明", 5])
        print(f"原始 SQL 结果: {rows}")
    except Exception as e:
        print(f"原始 SQL 失败: {e}")
        import traceback
        traceback.print_exc()

    engine.close()


if __name__ == "__main__":
    asyncio.run(main())
