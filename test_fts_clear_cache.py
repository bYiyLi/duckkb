"""测试 FTS 修复效果 - 清理缓存后重建索引。"""

import asyncio
from pathlib import Path

from duckkb.core.engine import Engine


async def main():
    """测试 FTS 功能。"""
    kb_path = Path(__file__).parent / ".duckkb" / "default"
    engine = Engine(kb_path=kb_path)
    await engine.async_initialize()

    print("清理缓存...")
    engine.execute_write("DELETE FROM _sys_search_cache")
    print("缓存清理完成")

    print("\n重建索引...")
    await engine.build_index()
    print("索引重建完成")

    rows = engine.execute_read(
        "SELECT id, source_table, source_field, content, fts_content FROM _sys_search_index LIMIT 10"
    )
    print(f"\n索引表数据 (共 {len(rows)} 条):")
    for row in rows:
        print(f"  ID: {row[0]}")
        print(f"  source_table: {row[1]}")
        print(f"  source_field: {row[2]}")
        print(f"  content: {row[3][:60] if row[3] else 'NULL'}")
        print(f"  fts_content: {row[4][:60] if row[4] else 'NULL'}")
        print(f"  包含空格: {'是' if row[4] and ' ' in row[4] else '否'}")
        if row[4]:
            words = row[4].split()
            print(f"  分词数量: {len(words)}, 前5个词: {words[:5]}")
        print()

    print("\n测试 FTS 搜索 '张明':")
    results = await engine.fts_search("张明", limit=5)
    print(f"搜索结果: {len(results)} 条")
    for r in results:
        print(f"  {r}")

    print("\n测试 FTS 搜索 '工程师':")
    results = await engine.fts_search("工程师", limit=5)
    print(f"搜索结果: {len(results)} 条")
    for r in results:
        print(f"  {r}")

    print("\n测试 FTS 搜索 '产品':")
    results = await engine.fts_search("产品", limit=5)
    print(f"搜索结果: {len(results)} 条")
    for r in results:
        print(f"  {r}")

    engine.close()


if __name__ == "__main__":
    asyncio.run(main())
