"""图谱功能测试。"""

import pytest


class TestGraphBasic:
    """图谱基础功能测试。"""

    @pytest.mark.asyncio
    async def test_get_neighbors_empty_graph(self, async_engine):
        """测试空图邻居查询。"""
        from duckkb.exceptions import NodeNotFoundError

        with pytest.raises(NodeNotFoundError):
            await async_engine.get_neighbors("Character", 1)

    @pytest.mark.asyncio
    async def test_get_neighbors_invalid_node_type(self, async_engine):
        """测试无效节点类型。"""
        with pytest.raises(ValueError, match="Unknown node type"):
            await async_engine.get_neighbors("InvalidType", 1)

    @pytest.mark.asyncio
    async def test_get_neighbors_with_data(self, async_engine, tmp_path):
        """测试有数据时的邻居查询。"""
        yaml_content = """
- type: Character
  name: 角色A
  bio: 测试角色A
- type: Character
  name: 角色B
  bio: 测试角色B
- type: knows
  source:
    name: 角色A
  target:
    name: 角色B
  since: "2024-01-01"
"""
        yaml_file = tmp_path / "test_neighbors.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        await async_engine.import_knowledge_bundle(str(yaml_file))

        rows = async_engine.execute_read("SELECT __id FROM characters WHERE name = ?", ["角色A"])
        if rows:
            result = await async_engine.get_neighbors("Character", rows[0][0])
            assert isinstance(result, dict)
            assert "node" in result
            assert "neighbors" in result


class TestGraphTraverse:
    """图遍历测试。"""

    @pytest.mark.asyncio
    async def test_traverse_empty_graph(self, async_engine):
        """测试空图遍历。"""
        from duckkb.exceptions import NodeNotFoundError

        with pytest.raises(NodeNotFoundError):
            await async_engine.traverse("Character", 1, max_depth=2)

    @pytest.mark.asyncio
    async def test_traverse_invalid_node_type(self, async_engine):
        """测试无效节点类型。"""
        with pytest.raises(ValueError, match="Unknown node type"):
            await async_engine.traverse("InvalidType", 1, max_depth=2)

    @pytest.mark.asyncio
    async def test_traverse_max_depth_limit(self, async_engine, tmp_path):
        """测试遍历深度限制。"""
        yaml_content = """
- type: Character
  name: 深度测试角色
  bio: 测试遍历深度限制
"""
        yaml_file = tmp_path / "test_depth.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        await async_engine.import_knowledge_bundle(str(yaml_file))

        rows = async_engine.execute_read(
            "SELECT __id FROM characters WHERE name = ?", ["深度测试角色"]
        )
        if rows:
            result = await async_engine.traverse("Character", rows[0][0], max_depth=1)
            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_traverse_with_edge_types_filter(self, async_engine, tmp_path):
        """测试边类型过滤。"""
        yaml_content = """
- type: Character
  name: 边类型测试角色
  bio: 测试边类型过滤
"""
        yaml_file = tmp_path / "test_edge_filter.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        await async_engine.import_knowledge_bundle(str(yaml_file))

        rows = async_engine.execute_read(
            "SELECT __id FROM characters WHERE name = ?", ["边类型测试角色"]
        )
        if rows:
            result = await async_engine.traverse(
                "Character", rows[0][0], max_depth=2, edge_types=["knows"]
            )
            assert isinstance(result, list)


class TestFindPaths:
    """路径查找测试。"""

    @pytest.mark.asyncio
    async def test_find_paths_no_path_exists(self, async_engine, tmp_path):
        """测试不存在路径的情况。"""
        yaml_content = """
- type: Character
  name: 孤立角色A
  bio: 测试孤立角色
- type: Character
  name: 孤立角色B
  bio: 测试孤立角色
"""
        yaml_file = tmp_path / "test_no_path.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        await async_engine.import_knowledge_bundle(str(yaml_file))

        rows = async_engine.execute_read("SELECT __id FROM characters")
        if len(rows) >= 2:
            paths = await async_engine.find_paths(
                ("Character", rows[0][0]), ("Character", rows[1][0]), max_depth=2
            )
            assert isinstance(paths, list)
            assert len(paths) == 0

    @pytest.mark.asyncio
    async def test_find_paths_invalid_node_type(self, async_engine):
        """测试无效节点类型。"""
        with pytest.raises(ValueError, match="Unknown node type"):
            await async_engine.find_paths(("InvalidType", 1), ("Character", 2), max_depth=2)


class TestExtractSubgraph:
    """子图提取测试。"""

    @pytest.mark.asyncio
    async def test_extract_subgraph_empty(self, async_engine):
        """测试空子图提取。"""
        from duckkb.exceptions import NodeNotFoundError

        with pytest.raises(NodeNotFoundError):
            await async_engine.extract_subgraph("Character", 1)

    @pytest.mark.asyncio
    async def test_extract_subgraph_invalid_node_type(self, async_engine):
        """测试无效节点类型。"""
        with pytest.raises(ValueError, match="Unknown node type"):
            await async_engine.extract_subgraph("InvalidType", 1)

    @pytest.mark.asyncio
    async def test_extract_subgraph_with_data(self, async_engine, tmp_path):
        """测试有数据时的子图提取。"""
        yaml_content = """
- type: Character
  name: 子图测试角色A
  bio: 测试子图提取
- type: Character
  name: 子图测试角色B
  bio: 测试子图提取
- type: knows
  source:
    name: 子图测试角色A
  target:
    name: 子图测试角色B
"""
        yaml_file = tmp_path / "test_subgraph.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        await async_engine.import_knowledge_bundle(str(yaml_file))

        rows = async_engine.execute_read(
            "SELECT __id FROM characters WHERE name = ?", ["子图测试角色A"]
        )
        if rows:
            result = await async_engine.extract_subgraph("Character", rows[0][0])
            assert isinstance(result, dict)
            assert "nodes" in result
            assert "edges" in result


class TestGraphSearch:
    """图谱搜索测试。"""

    @pytest.mark.asyncio
    async def test_graph_search_with_empty_results(self, async_engine, tmp_path):
        """测试空结果的图谱搜索。"""
        yaml_content = """
- type: Character
  name: 空结果测试角色
  bio: 测试空结果的图谱搜索
"""
        yaml_file = tmp_path / "empty_graph_search.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")
        await async_engine.import_knowledge_bundle(str(yaml_file))

        from unittest.mock import patch

        with patch("duckkb.core.mixins.embedding.EmbeddingMixin.embed_single") as mock:
            mock.return_value = [0.1] * 1536
            result = await async_engine.graph_search("不存在的实体xyz123", traverse_depth=1)
            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_graph_search_with_data(self, async_engine, tmp_path):
        """测试有数据时的图谱搜索。"""
        yaml_content = """
- type: Character
  name: 图谱搜索测试角色
  bio: 测试图谱搜索功能
"""
        yaml_file = tmp_path / "test_graph_search.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        await async_engine.import_knowledge_bundle(str(yaml_file))

        from unittest.mock import patch

        with patch("duckkb.core.mixins.embedding.EmbeddingMixin.embed_single") as mock:
            mock.return_value = [0.1] * 1536
            result = await async_engine.graph_search("图谱搜索", traverse_depth=1)
            assert isinstance(result, list)


class TestGraphEdgeCases:
    """图谱边界条件测试。"""

    @pytest.mark.asyncio
    async def test_traverse_with_zero_depth(self, async_engine, tmp_path):
        """测试深度为 0 的遍历。"""
        yaml_content = """
- type: Character
  name: 零深度测试角色
  bio: 测试零深度遍历
"""
        yaml_file = tmp_path / "test_zero_depth.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        await async_engine.import_knowledge_bundle(str(yaml_file))

        rows = async_engine.execute_read(
            "SELECT __id FROM characters WHERE name = ?", ["零深度测试角色"]
        )
        if rows:
            with pytest.raises(ValueError, match="max_depth 必须 >= 1"):
                await async_engine.traverse("Character", rows[0][0], max_depth=0)

    @pytest.mark.asyncio
    async def test_get_neighbors_with_edge_type_filter(self, async_engine, tmp_path):
        """测试带边类型过滤的邻居查询。"""
        yaml_content = """
- type: Character
  name: 边类型过滤测试角色
  bio: 测试边类型过滤
"""
        yaml_file = tmp_path / "test_edge_type_filter.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        await async_engine.import_knowledge_bundle(str(yaml_file))

        rows = async_engine.execute_read(
            "SELECT __id FROM characters WHERE name = ?", ["边类型过滤测试角色"]
        )
        if rows:
            result = await async_engine.get_neighbors(
                "Character", rows[0][0], edge_types=["knows"]
            )
            assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_find_paths_with_edge_type_filter(self, async_engine, tmp_path):
        """测试带边类型过滤的路径查找。"""
        yaml_content = """
- type: Character
  name: 路径过滤测试角色A
  bio: 测试路径过滤
- type: Character
  name: 路径过滤测试角色B
  bio: 测试路径过滤
"""
        yaml_file = tmp_path / "test_path_filter.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        await async_engine.import_knowledge_bundle(str(yaml_file))

        rows = async_engine.execute_read("SELECT __id FROM characters")
        if len(rows) >= 2:
            paths = await async_engine.find_paths(
                ("Character", rows[0][0]),
                ("Character", rows[1][0]),
                max_depth=2,
                edge_types=["knows"],
            )
            assert isinstance(paths, list)

    @pytest.mark.asyncio
    async def test_extract_subgraph_with_nonexistent_node(self, async_engine):
        """测试不存在的节点子图提取。"""
        from duckkb.exceptions import NodeNotFoundError

        with pytest.raises(NodeNotFoundError):
            await async_engine.extract_subgraph("Character", 999999)

    @pytest.mark.asyncio
    async def test_get_neighbors_with_direction(self, async_engine, tmp_path):
        """测试带方向过滤的邻居查询。"""
        yaml_content = """
- type: Character
  name: 方向过滤测试角色
  bio: 测试方向过滤
"""
        yaml_file = tmp_path / "test_direction.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        await async_engine.import_knowledge_bundle(str(yaml_file))

        rows = async_engine.execute_read(
            "SELECT __id FROM characters WHERE name = ?", ["方向过滤测试角色"]
        )
        if rows:
            result_out = await async_engine.get_neighbors(
                "Character", rows[0][0], direction="out"
            )
            result_in = await async_engine.get_neighbors(
                "Character", rows[0][0], direction="in"
            )
            assert isinstance(result_out, dict)
            assert isinstance(result_in, dict)
