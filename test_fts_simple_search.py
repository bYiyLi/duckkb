"""简单测试 FTS 搜索。"""

import asyncio
from pathlib import Path

from duckkb.core.engine import Engine


async def main():
    """测试 FTS 搜索。"""
    kb_path = Path(__file__).parent / ".duckkb" / "default"
    engine = Engine(kb_path=kb_path)
    await engine.async_initialize()

    print("测试 FTS 搜索 '张明':")
    results = await engine.fts_search("张明", limit=5)
    print(f"搜索结果: {len(results)} 条")
    for r in results:
        print(f"  {r}")

    print("\n测试 FTS 搜索 '测试':")
    results = await engine.fts_search("测试", limit=5)
    print(f"搜索结果: {len(results)} 条")
    for r in results:
        print(f"  {r}")

    engine.close()


if __name__ == "__main__":
    asyncio.run(main())
