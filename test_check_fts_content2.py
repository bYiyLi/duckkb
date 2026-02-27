"""检查包含关键词的记录的 fts_content。"""

import asyncio
from pathlib import Path

from duckkb.core.engine import Engine


async def main():
    """检查数据。"""
    kb_path = Path(__file__).parent / ".duckkb" / "default"
    engine = Engine(kb_path=kb_path)
    await engine.async_initialize()

    print("检查索引表中包含 '工程师' 的记录:")
    rows = engine.execute_read(
        "SELECT id, content, fts_content FROM _sys_search_index WHERE content LIKE '%工程师%'"
    )
    print(f"  找到 {len(rows)} 条")
    for row in rows:
        print(f"    ID: {row[0]}")
        print(f"      content: {row[1][:60]}")
        print(f"      fts_content: {row[2][:60] if row[2] else 'NULL'}")
        print(f"      包含空格: {'是' if row[2] and ' ' in row[2] else '否'}")
        if row[2]:
            words = row[2].split()
            print(f"      分词数量: {len(words)}, 前10个词: {words[:10]}")
        print()

    print("\n检查索引表中包含 '产品' 的记录:")
    rows = engine.execute_read(
        "SELECT id, content, fts_content FROM _sys_search_index WHERE content LIKE '%产品%'"
    )
    print(f"  找到 {len(rows)} 条")
    for row in rows:
        print(f"    ID: {row[0]}")
        print(f"      content: {row[1][:60]}")
        print(f"      fts_content: {row[2][:60] if row[2] else 'NULL'}")
        print(f"      包含空格: {'是' if row[2] and ' ' in row[2] else '否'}")
        if row[2]:
            words = row[2].split()
            print(f"      分词数量: {len(words)}, 前10个词: {words[:10]}")
        print()

    engine.close()


if __name__ == "__main__":
    asyncio.run(main())
