"""检查数据库中的实际数据。"""

import asyncio
from pathlib import Path

from duckkb.core.engine import Engine


async def main():
    """检查数据。"""
    kb_path = Path(__file__).parent / ".duckkb" / "default"
    engine = Engine(kb_path=kb_path)
    await engine.async_initialize()

    print("检查 characters 表:")
    rows = engine.execute_read("SELECT __id, name, bio FROM characters")
    for row in rows:
        print(f"  ID: {row[0]}, name: {row[1]}, bio: {row[2][:50] if row[2] else 'NULL'}")

    print("\n检查 documents 表:")
    rows = engine.execute_read("SELECT __id, title, content FROM documents")
    for row in rows:
        print(f"  ID: {row[0]}, title: {row[1]}, content: {row[2][:50] if row[2] else 'NULL'}")

    print("\n检查 products 表:")
    rows = engine.execute_read("SELECT __id, name, description FROM products")
    for row in rows:
        print(f"  ID: {row[0]}, name: {row[1]}, description: {row[2][:50] if row[2] else 'NULL'}")

    print("\n检查索引表中包含 '工程师' 的记录:")
    rows = engine.execute_read(
        "SELECT id, content, fts_content FROM _sys_search_index WHERE content LIKE '%工程师%'"
    )
    print(f"  找到 {len(rows)} 条")
    for row in rows:
        print(f"    ID: {row[0]}, content: {row[1][:50]}")

    print("\n检查索引表中包含 '产品' 的记录:")
    rows = engine.execute_read(
        "SELECT id, content, fts_content FROM _sys_search_index WHERE content LIKE '%产品%'"
    )
    print(f"  找到 {len(rows)} 条")
    for row in rows:
        print(f"    ID: {row[0]}, content: {row[1][:50]}")

    engine.close()


if __name__ == "__main__":
    asyncio.run(main())
