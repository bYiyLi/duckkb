"""测试 FTS 修复效果。"""

import asyncio
import tempfile
from pathlib import Path

from duckkb.core.engine import Engine


async def main():
    """测试 FTS 功能。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        kb_path = Path(tmpdir) / "test_kb"
        kb_path.mkdir(parents=True, exist_ok=True)

        config_path = Path(__file__).parent / ".duckkb" / "default" / "config.yaml"
        engine = Engine(kb_path=kb_path, config_path=config_path)
        await engine.async_initialize()

        yaml_file = Path(__file__).parent / "tests" / "test_data_real.yaml"

        result = await engine.import_knowledge_bundle(str(yaml_file))
        print(f"导入结果: {result}")

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
