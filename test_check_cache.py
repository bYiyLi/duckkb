"""检查缓存表。"""

import asyncio
from pathlib import Path

from duckkb.core.engine import Engine


async def main():
    """检查缓存。"""
    kb_path = Path(__file__).parent / ".duckkb" / "default"
    engine = Engine(kb_path=kb_path)
    await engine.async_initialize()

    print("检查缓存表:")
    rows = engine.execute_read(
        "SELECT content_hash, fts_content FROM _sys_search_cache LIMIT 10"
    )
    print(f"  共 {len(rows)} 条缓存")
    for row in rows:
        print(f"    hash: {row[0][:16]}...")
        print(f"    fts_content: {row[1][:60] if row[1] else 'NULL'}")
        print(f"    包含空格: {'是' if row[1] and ' ' in row[1] else '否'}")
        print()

    print("\n清理缓存...")
    engine.execute_write("DELETE FROM _sys_search_cache")
    print("缓存清理完成")

    print("\n重建索引...")
    await engine.build_index()
    print("索引重建完成")

    print("\n再次检查缓存表:")
    rows = engine.execute_read(
        "SELECT content_hash, fts_content FROM _sys_search_cache LIMIT 10"
    )
    print(f"  共 {len(rows)} 条缓存")
    for row in rows:
        print(f"    hash: {row[0][:16]}...")
        print(f"    fts_content: {row[1][:60] if row[1] else 'NULL'}")
        print(f"    包含空格: {'是' if row[1] and ' ' in row[1] else '否'}")
        if row[1] and ' ' in row[1]:
            words = row[1].split()
            print(f"    分词数量: {len(words)}, 前5个词: {words[:5]}")
        print()

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
