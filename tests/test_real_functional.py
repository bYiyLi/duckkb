"""DuckKB 真实功能测试。

使用真实数据和嵌入 API 进行全面的功能测试。
"""

from pathlib import Path

import pytest

DEFAULT_KB_PATH = Path(__file__).parent.parent / ".duckkb" / "default"
TEST_DATA_PATH = Path(__file__).parent / "test_data_real.yaml"


@pytest.fixture
def real_engine():
    """创建真实引擎实例。"""
    from duckkb.core.engine import Engine

    eng = Engine(DEFAULT_KB_PATH)
    eng.initialize()
    yield eng
    eng.close()


@pytest.fixture
async def real_async_engine():
    """创建异步引擎实例。"""
    from duckkb.core.engine import Engine

    eng = Engine(DEFAULT_KB_PATH)
    await eng.async_initialize()
    yield eng
    eng.close()


class TestInfo:
    """知识库信息测试。"""

    def test_get_info(self, real_engine):
        """测试获取知识库信息。"""
        result = real_engine.get_info()
        assert "# 知识库介绍" in result
        assert "## 使用说明" in result
        assert "## 导入数据格式" in result
        assert "## 表结构" in result
        assert "## 知识图谱关系" in result

    def test_get_info_contains_node_types(self, real_engine):
        """测试知识库信息包含节点类型。"""
        result = real_engine.get_info()
        assert "Character" in result
        assert "Document" in result
        assert "Product" in result

    def test_get_info_contains_edge_types(self, real_engine):
        """测试知识库信息包含边类型。"""
        result = real_engine.get_info()
        assert "knows" in result
        assert "authored" in result
        assert "mentions" in result


class TestNodeCRUD:
    """节点 CRUD 测试。"""

    @pytest.mark.asyncio
    async def test_import_characters(self, real_async_engine, tmp_path):
        """N-01: 创建 Character。"""
        yaml_content = """
- type: Character
  name: 测试角色_N01
  age: 25
  bio: 这是一个测试角色用于验证创建功能。
"""
        yaml_file = tmp_path / "test_n01.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        result = await real_async_engine.import_knowledge_bundle(str(yaml_file))
        assert result["status"] == "success"
        assert "Character" in result["nodes"]["upserted"]

    @pytest.mark.asyncio
    async def test_import_documents(self, real_async_engine, tmp_path):
        """N-02: 创建 Document。"""
        yaml_content = """
- type: Document
  doc_id: DOC-TEST-001
  title: 测试文档_N02
  content: 这是测试文档内容，用于验证文档创建功能。
  category: 测试
  word_count: 20
"""
        yaml_file = tmp_path / "test_n02.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        result = await real_async_engine.import_knowledge_bundle(str(yaml_file))
        assert result["status"] == "success"
        assert "Document" in result["nodes"]["upserted"]

    @pytest.mark.asyncio
    async def test_import_products(self, real_async_engine, tmp_path):
        """N-03: 创建 Product。"""
        yaml_content = """
- type: Product
  sku: SKU-TEST-001
  name: 测试产品_N03
  description: 这是测试产品描述。
  price: 99.99
  stock: 10
  active: true
"""
        yaml_file = tmp_path / "test_n03.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        result = await real_async_engine.import_knowledge_bundle(str(yaml_file))
        assert result["status"] == "success"
        assert "Product" in result["nodes"]["upserted"]

    @pytest.mark.asyncio
    async def test_batch_import_nodes(self, real_async_engine, tmp_path):
        """N-04: 批量创建节点。"""
        yaml_content = """
- type: Character
  name: 批量角色1_N04
  bio: 批量测试角色1
- type: Character
  name: 批量角色2_N04
  bio: 批量测试角色2
- type: Document
  doc_id: DOC-BATCH-001
  title: 批量文档_N04
  content: 批量测试文档
"""
        yaml_file = tmp_path / "test_n04.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        result = await real_async_engine.import_knowledge_bundle(str(yaml_file))
        assert result["status"] == "success"
        assert result["nodes"]["upserted"]["Character"] >= 2
        assert result["nodes"]["upserted"]["Document"] >= 1

    @pytest.mark.asyncio
    async def test_update_character_bio(self, real_async_engine, tmp_path):
        """N-05: 更新 Character bio。"""
        yaml_content1 = """
- type: Character
  name: 更新测试角色_N05
  bio: 原始简介
"""
        yaml_file1 = tmp_path / "test_n05_1.yaml"
        yaml_file1.write_text(yaml_content1, encoding="utf-8")
        await real_async_engine.import_knowledge_bundle(str(yaml_file1))

        yaml_content2 = """
- type: Character
  name: 更新测试角色_N05
  bio: 更新后的简介_N05
"""
        yaml_file2 = tmp_path / "test_n05_2.yaml"
        yaml_file2.write_text(yaml_content2, encoding="utf-8")
        result = await real_async_engine.import_knowledge_bundle(str(yaml_file2))

        assert result["status"] == "success"

        row = real_async_engine.execute_read(
            "SELECT bio FROM characters WHERE name = ?", ["更新测试角色_N05"]
        )[0]
        assert row[0] == "更新后的简介_N05"

    @pytest.mark.asyncio
    async def test_update_document_content(self, real_async_engine, tmp_path):
        """N-06: 更新 Document 内容。"""
        yaml_content1 = """
- type: Document
  doc_id: DOC-UPDATE-001
  title: 更新测试文档_N06
  content: 原始内容
"""
        yaml_file1 = tmp_path / "test_n06_1.yaml"
        yaml_file1.write_text(yaml_content1, encoding="utf-8")
        await real_async_engine.import_knowledge_bundle(str(yaml_file1))

        yaml_content2 = """
- type: Document
  doc_id: DOC-UPDATE-001
  title: 更新测试文档_N06
  content: 更新后的内容_N06
"""
        yaml_file2 = tmp_path / "test_n06_2.yaml"
        yaml_file2.write_text(yaml_content2, encoding="utf-8")
        result = await real_async_engine.import_knowledge_bundle(str(yaml_file2))

        assert result["status"] == "success"

        row = real_async_engine.execute_read(
            "SELECT content FROM documents WHERE doc_id = ?", ["DOC-UPDATE-001"]
        )[0]
        assert row[0] == "更新后的内容_N06"

    @pytest.mark.asyncio
    async def test_update_product_price(self, real_async_engine, tmp_path):
        """N-07: 更新 Product 价格。"""
        yaml_content1 = """
- type: Product
  sku: SKU-UPDATE-001
  name: 更新测试产品_N07
  price: 100.00
"""
        yaml_file1 = tmp_path / "test_n07_1.yaml"
        yaml_file1.write_text(yaml_content1, encoding="utf-8")
        await real_async_engine.import_knowledge_bundle(str(yaml_file1))

        yaml_content2 = """
- type: Product
  sku: SKU-UPDATE-001
  name: 更新测试产品_N07
  price: 199.99
"""
        yaml_file2 = tmp_path / "test_n07_2.yaml"
        yaml_file2.write_text(yaml_content2, encoding="utf-8")
        result = await real_async_engine.import_knowledge_bundle(str(yaml_file2))

        assert result["status"] == "success"

        row = real_async_engine.execute_read(
            "SELECT price FROM products WHERE sku = ?", ["SKU-UPDATE-001"]
        )[0]
        assert row[0] == 199.99

    @pytest.mark.asyncio
    async def test_delete_node(self, real_async_engine, tmp_path):
        """N-08: 删除节点。"""
        yaml_content1 = """
- type: Character
  name: 待删除角色_N08
  bio: 这个角色将被删除
"""
        yaml_file1 = tmp_path / "test_n08_1.yaml"
        yaml_file1.write_text(yaml_content1, encoding="utf-8")
        await real_async_engine.import_knowledge_bundle(str(yaml_file1))

        yaml_content2 = """
- type: Character
  action: delete
  name: 待删除角色_N08
"""
        yaml_file2 = tmp_path / "test_n08_2.yaml"
        yaml_file2.write_text(yaml_content2, encoding="utf-8")
        result = await real_async_engine.import_knowledge_bundle(str(yaml_file2))

        assert result["status"] == "success"
        assert "Character" in result["nodes"]["deleted"]

        rows = real_async_engine.execute_read(
            "SELECT * FROM characters WHERE name = ?", ["待删除角色_N08"]
        )
        assert len(rows) == 0


class TestEdgeCRUD:
    """边 CRUD 测试。"""

    @pytest.mark.asyncio
    async def test_create_knows_edge(self, real_async_engine, tmp_path):
        """E-01: 创建 knows 边。"""
        yaml_content = """
- type: Character
  name: 边测试角色A_E01
  bio: 测试角色A
- type: Character
  name: 边测试角色B_E01
  bio: 测试角色B
- type: knows
  source: {name: 边测试角色A_E01}
  target: {name: 边测试角色B_E01}
  since: "2024-01-01"
  closeness: 0.8
"""
        yaml_file = tmp_path / "test_e01.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        result = await real_async_engine.import_knowledge_bundle(str(yaml_file))
        assert result["status"] == "success"
        assert "knows" in result["edges"]["upserted"]

    @pytest.mark.asyncio
    async def test_create_authored_edge(self, real_async_engine, tmp_path):
        """E-02: 创建 authored 边。"""
        yaml_content = """
- type: Character
  name: 作者角色_E02
  bio: 测试作者
- type: Document
  doc_id: DOC-E02
  title: 作者文档_E02
  content: 测试文档内容
- type: authored
  source: {name: 作者角色_E02}
  target: {doc_id: DOC-E02}
  role: 主要作者
"""
        yaml_file = tmp_path / "test_e02.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        result = await real_async_engine.import_knowledge_bundle(str(yaml_file))
        assert result["status"] == "success"
        assert "authored" in result["edges"]["upserted"]

    @pytest.mark.asyncio
    async def test_create_mentions_edge(self, real_async_engine, tmp_path):
        """E-03: 创建 mentions 边。"""
        yaml_content = """
- type: Document
  doc_id: DOC-E03
  title: 提及文档_E03
  content: 测试文档内容
- type: Product
  sku: SKU-E03
  name: 被提及产品_E03
  description: 测试产品
- type: mentions
  source: {doc_id: DOC-E03}
  target: {sku: SKU-E03}
  context: 文档中提及此产品
  relevance: 0.9
"""
        yaml_file = tmp_path / "test_e03.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        result = await real_async_engine.import_knowledge_bundle(str(yaml_file))
        assert result["status"] == "success"
        assert "mentions" in result["edges"]["upserted"]

    @pytest.mark.asyncio
    async def test_invalid_source_node(self, real_async_engine, tmp_path):
        """E-04: 无效源节点。"""
        yaml_content = """
- type: knows
  source: {name: 不存在的角色_E04}
  target: {name: 张明}
"""
        yaml_file = tmp_path / "test_e04.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        with pytest.raises(Exception):
            await real_async_engine.import_knowledge_bundle(str(yaml_file))

    @pytest.mark.asyncio
    async def test_invalid_target_node(self, real_async_engine, tmp_path):
        """E-05: 无效目标节点。"""
        yaml_content = """
- type: knows
  source: {name: 张明}
  target: {name: 不存在的角色_E05}
"""
        yaml_file = tmp_path / "test_e05.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        with pytest.raises(Exception):
            await real_async_engine.import_knowledge_bundle(str(yaml_file))

    @pytest.mark.asyncio
    async def test_delete_edge(self, real_async_engine, tmp_path):
        """E-06: 删除边。"""
        yaml_content1 = """
- type: Character
  name: 边删除测试A_E06
  bio: 测试
- type: Character
  name: 边删除测试B_E06
  bio: 测试
- type: knows
  source: {name: 边删除测试A_E06}
  target: {name: 边删除测试B_E06}
  since: "2024-01-01"
"""
        yaml_file1 = tmp_path / "test_e06_1.yaml"
        yaml_file1.write_text(yaml_content1, encoding="utf-8")
        await real_async_engine.import_knowledge_bundle(str(yaml_file1))

        yaml_content2 = """
- type: knows
  action: delete
  source: {name: 边删除测试A_E06}
  target: {name: 边删除测试B_E06}
"""
        yaml_file2 = tmp_path / "test_e06_2.yaml"
        yaml_file2.write_text(yaml_content2, encoding="utf-8")
        result = await real_async_engine.import_knowledge_bundle(str(yaml_file2))

        assert result["status"] == "success"
        assert "knows" in result["edges"]["deleted"]


class TestSQLQuery:
    """SQL 查询测试。"""

    @pytest.mark.asyncio
    async def test_basic_query(self, real_async_engine):
        """Q-01: 基础查询。"""
        results = await real_async_engine.query_raw_sql("SELECT name, age FROM characters LIMIT 5")
        assert len(results) <= 5
        if len(results) > 0:
            assert "name" in results[0]

    @pytest.mark.asyncio
    async def test_conditional_query(self, real_async_engine):
        """Q-02: 条件查询。"""
        results = await real_async_engine.query_raw_sql(
            "SELECT sku, name, price FROM products WHERE price > 1000"
        )
        for row in results:
            assert row["price"] > 1000

    @pytest.mark.asyncio
    async def test_order_query(self, real_async_engine):
        """Q-03: 排序查询。"""
        results = await real_async_engine.query_raw_sql(
            "SELECT doc_id, title, word_count FROM documents WHERE word_count IS NOT NULL ORDER BY word_count DESC LIMIT 10"
        )
        if len(results) > 1:
            for i in range(len(results) - 1):
                if (
                    results[i]["word_count"] is not None
                    and results[i + 1]["word_count"] is not None
                ):
                    assert results[i]["word_count"] >= results[i + 1]["word_count"]

    @pytest.mark.asyncio
    async def test_aggregate_query(self, real_async_engine):
        """Q-04: 聚合查询。"""
        results = await real_async_engine.query_raw_sql(
            "SELECT category, COUNT(*) as cnt FROM documents GROUP BY category"
        )
        assert len(results) >= 0
        for row in results:
            assert "category" in row
            assert "cnt" in row

    @pytest.mark.asyncio
    async def test_join_query(self, real_async_engine):
        """Q-05: 连接查询。"""
        results = await real_async_engine.query_raw_sql("""
            SELECT c.name, d.title
            FROM characters c
            JOIN edge_authored e ON c.__id = e.__from_id
            JOIN documents d ON e.__to_id = d.__id
            LIMIT 10
        """)
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_security_check_insert(self, real_async_engine):
        """Q-06: 安全检查 - INSERT 应被拒绝。"""
        with pytest.raises(Exception):
            await real_async_engine.query_raw_sql("INSERT INTO characters (name) VALUES ('test')")

    @pytest.mark.asyncio
    async def test_security_check_update(self, real_async_engine):
        """Q-06: 安全检查 - UPDATE 应被拒绝。"""
        with pytest.raises(Exception):
            await real_async_engine.query_raw_sql(
                "UPDATE characters SET bio = 'test' WHERE name = '张明'"
            )

    @pytest.mark.asyncio
    async def test_auto_limit(self, real_async_engine):
        """Q-07: LIMIT 自动添加。"""
        results = await real_async_engine.query_raw_sql("SELECT name FROM characters")
        assert len(results) <= 1000


class TestSearch:
    """搜索功能测试。"""

    @pytest.mark.asyncio
    async def test_search_semantic(self, real_async_engine):
        """S-01: 语义搜索。"""
        results = await real_async_engine.search("知识图谱技术专家", limit=5)
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_keyword(self, real_async_engine):
        """S-02: 关键词搜索。"""
        results = await real_async_engine.search("DuckDB", limit=5)
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_hybrid(self, real_async_engine):
        """S-03: 混合搜索。"""
        results = await real_async_engine.search("向量检索优化", limit=5)
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_with_node_type_filter(self, real_async_engine):
        """S-04: 类型过滤搜索。"""
        results = await real_async_engine.search("技术", node_type="Document", limit=5)
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_with_alpha(self, real_async_engine):
        """S-05: 权重调节搜索。"""
        results1 = await real_async_engine.search("知识库", alpha=0.2, limit=5)
        results2 = await real_async_engine.search("知识库", alpha=0.8, limit=5)
        assert isinstance(results1, list)
        assert isinstance(results2, list)

    @pytest.mark.asyncio
    async def test_vector_search(self, real_async_engine):
        """S-06: 向量搜索。"""
        results = await real_async_engine.vector_search("机器学习算法", limit=5)
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_vector_search_concept(self, real_async_engine):
        """S-07: 概念搜索。"""
        results = await real_async_engine.vector_search("前端开发框架", limit=5)
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_fts_search_exact(self, real_async_engine):
        """S-08: 全文精确匹配。"""
        try:
            results = await real_async_engine.fts_search("DuckKB 企业版", limit=5)
            assert isinstance(results, list)
        except Exception as e:
            from duckkb.exceptions import FTSError

            if isinstance(e, FTSError):
                pytest.skip("FTS extension not available")
            raise

    @pytest.mark.asyncio
    async def test_fts_search_chinese(self, real_async_engine):
        """S-09: 中文分词搜索。"""
        try:
            results = await real_async_engine.fts_search("知识库 解决方案", limit=5)
            assert isinstance(results, list)
        except Exception as e:
            from duckkb.exceptions import FTSError

            if isinstance(e, FTSError):
                pytest.skip("FTS extension not available")
            raise

    @pytest.mark.asyncio
    async def test_get_source_record(self, real_async_engine):
        """S-10: 获取源记录。"""
        results = await real_async_engine.search("张明", limit=1)
        if len(results) > 0:
            record = await real_async_engine.get_source_record(
                results[0]["source_table"], results[0]["source_id"]
            )
            assert record is not None
            assert "name" in record


class TestGraph:
    """图谱功能测试。"""

    @pytest.fixture(autouse=True)
    async def setup_graph_data(self, real_async_engine, tmp_path):
        """在每个测试前导入图谱测试数据。"""
        yaml_content = """
- type: Character
  name: 张明
  age: 28
  bio: 张明是一名资深软件工程师，专注于向量数据库和知识图谱技术。
- type: Character
  name: 李婷
  age: 32
  bio: 李婷是产品经理，负责知识库产品规划。
- type: Character
  name: 王强
  age: 35
  bio: 王强是架构师，负责系统架构设计。
- type: Character
  name: 张三
  age: 25
  bio: 张三是新入职的开发工程师。
- type: Document
  doc_id: DOC-001
  title: 技术架构设计文档
  content: DuckKB 是一个基于 DuckDB 构建的知识库引擎。
- type: Product
  sku: SKU-001
  name: DuckKB 企业版
  description: 面向企业用户的知识库解决方案。
  price: 99999.00
  stock: 100
  active: true
- type: knows
  source:
    name: 张明
  target:
    name: 李婷
  since: "2023-06-01"
- type: knows
  source:
    name: 李婷
  target:
    name: 王强
  since: "2023-08-15"
- type: authored
  source:
    name: 张明
  target:
    doc_id: DOC-001
- type: mentions
  source:
    doc_id: DOC-001
  target:
    sku: SKU-001
"""
        yaml_file = tmp_path / "graph_setup.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")
        await real_async_engine.import_knowledge_bundle(str(yaml_file))

    @pytest.mark.asyncio
    async def test_get_neighbors_out(self, real_async_engine):
        """G-01: 出边邻居。"""
        result = await real_async_engine.get_neighbors(
            node_type="Character",
            node_id="张明",
            direction="out",
            limit=10,
        )
        assert "neighbors" in result

    @pytest.mark.asyncio
    async def test_get_neighbors_in(self, real_async_engine):
        """G-02: 入边邻居。"""
        result = await real_async_engine.get_neighbors(
            node_type="Character",
            node_id="李婷",
            direction="in",
            limit=10,
        )
        assert "neighbors" in result

    @pytest.mark.asyncio
    async def test_get_neighbors_both(self, real_async_engine):
        """G-03: 双向邻居。"""
        result = await real_async_engine.get_neighbors(
            node_type="Character",
            node_id="张明",
            direction="both",
            limit=10,
        )
        assert "neighbors" in result

    @pytest.mark.asyncio
    async def test_get_neighbors_with_edge_filter(self, real_async_engine):
        """G-04: 边类型过滤。"""
        result = await real_async_engine.get_neighbors(
            node_type="Character",
            node_id="张明",
            edge_types=["knows"],
            direction="out",
            limit=10,
        )
        assert "neighbors" in result

    @pytest.mark.asyncio
    async def test_get_neighbors_with_limit(self, real_async_engine):
        """G-05: 数量限制。"""
        result = await real_async_engine.get_neighbors(
            node_type="Character",
            node_id="张明",
            direction="both",
            limit=2,
        )
        assert "neighbors" in result

    @pytest.mark.asyncio
    async def test_traverse_single_hop(self, real_async_engine):
        """G-06: 单跳遍历。"""
        results = await real_async_engine.traverse(
            node_type="Character",
            node_id="张明",
            max_depth=1,
            limit=100,
        )
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_traverse_multi_hop(self, real_async_engine):
        """G-07: 多跳遍历。"""
        results = await real_async_engine.traverse(
            node_type="Character",
            node_id="张明",
            max_depth=3,
            limit=100,
        )
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_traverse_with_paths(self, real_async_engine):
        """G-08: 路径返回。"""
        results = await real_async_engine.traverse(
            node_type="Character",
            node_id="张明",
            max_depth=2,
            return_paths=True,
            limit=100,
        )
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_traverse_direction(self, real_async_engine):
        """G-09: 方向控制。"""
        results_out = await real_async_engine.traverse(
            node_type="Character",
            node_id="张明",
            direction="out",
            max_depth=1,
            limit=100,
        )
        results_in = await real_async_engine.traverse(
            node_type="Character",
            node_id="张明",
            direction="in",
            max_depth=1,
            limit=100,
        )
        assert isinstance(results_out, list)
        assert isinstance(results_in, list)

    @pytest.mark.asyncio
    async def test_graph_search(self, real_async_engine):
        """G-10: 图谱搜索。"""
        results = await real_async_engine.graph_search(
            query="知识图谱",
            traverse_depth=1,
            search_limit=3,
            neighbor_limit=5,
        )
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_graph_search_depth(self, real_async_engine):
        """G-11: 遍历深度。"""
        results = await real_async_engine.graph_search(
            query="技术",
            traverse_depth=2,
            search_limit=3,
            neighbor_limit=5,
        )
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_extract_subgraph(self, real_async_engine):
        """G-13: 提取子图。"""
        result = await real_async_engine.extract_subgraph(
            node_type="Character",
            node_id="张明",
            max_depth=2,
            node_limit=50,
            edge_limit=100,
        )
        assert "center_node" in result
        assert "nodes" in result
        assert "edges" in result

    @pytest.mark.asyncio
    async def test_extract_subgraph_depth(self, real_async_engine):
        """G-14: 深度控制。"""
        result = await real_async_engine.extract_subgraph(
            node_type="Character",
            node_id="张明",
            max_depth=1,
            node_limit=50,
            edge_limit=100,
        )
        assert "nodes" in result

    @pytest.mark.asyncio
    async def test_find_paths_direct(self, real_async_engine):
        """G-16: 直接路径。"""
        results = await real_async_engine.find_paths(
            from_node=("Character", "张明"),
            to_node=("Character", "李婷"),
            max_depth=3,
            limit=5,
        )
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_find_paths_multi_hop(self, real_async_engine):
        """G-17: 多跳路径。"""
        results = await real_async_engine.find_paths(
            from_node=("Character", "张明"),
            to_node=("Product", "SKU-001"),
            max_depth=5,
            limit=10,
        )
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_find_paths_no_path(self, real_async_engine):
        """G-19: 无路径情况 - 使用不连通但存在的节点。"""
        results = await real_async_engine.find_paths(
            from_node=("Character", "张三"),
            to_node=("Character", "王强"),
            max_depth=1,
            limit=5,
        )
        assert isinstance(results, list)


class TestImportValidation:
    """导入校验测试。"""

    @pytest.mark.asyncio
    async def test_valid_yaml(self, real_async_engine, tmp_path):
        """I-01: 有效 YAML。"""
        yaml_content = """
- type: Character
  name: 有效测试角色_I01
  bio: 这是一个有效的测试角色。
"""
        yaml_file = tmp_path / "test_i01.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        result = await real_async_engine.import_knowledge_bundle(str(yaml_file))
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_invalid_yaml(self, real_async_engine, tmp_path):
        """I-02: 无效 YAML。"""
        yaml_file = tmp_path / "test_i02.yaml"
        yaml_file.write_text("invalid: [unclosed", encoding="utf-8")

        with pytest.raises(Exception):
            await real_async_engine.import_knowledge_bundle(str(yaml_file))

    @pytest.mark.asyncio
    async def test_non_array_root(self, real_async_engine, tmp_path):
        """I-03: 非数组根。"""
        yaml_file = tmp_path / "test_i03.yaml"
        yaml_file.write_text("key: value", encoding="utf-8")

        with pytest.raises(ValueError, match="must contain an array"):
            await real_async_engine.import_knowledge_bundle(str(yaml_file))

    @pytest.mark.asyncio
    async def test_missing_type(self, real_async_engine, tmp_path):
        """I-04: 缺失类型。"""
        yaml_content = """
- name: 无类型角色_I04
  bio: 没有类型字段
"""
        yaml_file = tmp_path / "test_i04.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        with pytest.raises(Exception):
            await real_async_engine.import_knowledge_bundle(str(yaml_file))

    @pytest.mark.asyncio
    async def test_unknown_type(self, real_async_engine, tmp_path):
        """I-05: 未知类型。"""
        yaml_content = """
- type: UnknownType
  id: test
"""
        yaml_file = tmp_path / "test_i05.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        with pytest.raises(Exception):
            await real_async_engine.import_knowledge_bundle(str(yaml_file))

    @pytest.mark.asyncio
    async def test_schema_validation_type_mismatch(self, real_async_engine, tmp_path):
        """I-06: Schema 校验 - 类型不匹配。"""
        yaml_content = """
- type: Character
  name: 类型不匹配测试_I06
  age: 不是数字
"""
        yaml_file = tmp_path / "test_i06.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        with pytest.raises(Exception):
            await real_async_engine.import_knowledge_bundle(str(yaml_file))

    @pytest.mark.asyncio
    async def test_missing_required_field(self, real_async_engine, tmp_path):
        """I-07: 缺失必填字段。"""
        yaml_content = """
- type: Character
  bio: 没有name字段
"""
        yaml_file = tmp_path / "test_i07.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        with pytest.raises(Exception):
            await real_async_engine.import_knowledge_bundle(str(yaml_file))

    @pytest.mark.asyncio
    async def test_file_not_found(self, real_async_engine, tmp_path):
        """测试文件不存在。"""
        with pytest.raises(FileNotFoundError):
            await real_async_engine.import_knowledge_bundle(str(tmp_path / "nonexistent.yaml"))


class TestImportRealData:
    """导入真实测试数据。"""

    @pytest.mark.asyncio
    async def test_import_all_test_data(self, real_async_engine):
        """导入完整的测试数据集。"""
        if not TEST_DATA_PATH.exists():
            pytest.skip("测试数据文件不存在")

        result = await real_async_engine.import_knowledge_bundle(str(TEST_DATA_PATH))
        assert result["status"] == "success"

        assert result["nodes"]["upserted"]["Character"] >= 2
        assert result["nodes"]["upserted"]["Document"] >= 2
        assert result["nodes"]["upserted"]["Product"] >= 2
        assert result["edges"]["upserted"]["knows"] >= 2
        assert result["edges"]["upserted"]["authored"] >= 2
        assert result["edges"]["upserted"]["mentions"] >= 2
