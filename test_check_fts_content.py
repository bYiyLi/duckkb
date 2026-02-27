"""检查 DuckKB 的 fts_content 字段。"""

import asyncio
from pathlib import Path
from duckkb.core.engine import Engine


async def main():
    kb_path = Path(__file__).parent / ".duckkb" / "default"
    engine = Engine(kb_path=kb_path)
    await engine.async_initialize()

    rows = engine.execute_read(
        "SELECT id, content, fts_content FROM _sys_search_index LIMIT 10"
    )

    print("检查 fts_content 字段:")
    for row in rows:
        id_, content, fts_content = row
        print(f"\nID: {id_}")
        print(f"  content: {content[:80] if content else 'NULL'}")
        print(f"  fts_content: {fts_content[:80] if fts_content else 'NULL'}")
        print(f"  包含空格: {'是' if fts_content and ' ' in fts_content else '否'}")
        if fts_content:
            words = fts_content.split()
            print(f"  分词数量: {len(words)}")
            print(f"  前5个词: {words[:5]}")

    engine.close()


if __name__ == "__main__":
    asyncio.run(main())
