"""本体模型测试。"""

import pytest

from duckkb.core.models.ontology import (
    EdgeType,
    NodeType,
    Ontology,
    VectorConfig,
    validate_json_by_schema,
)


class TestVectorConfig:
    """向量配置测试。"""

    def test_create_vector_config_success(self):
        """测试创建向量配置成功。"""
        config = VectorConfig(dim=1536, model="text-embedding-3-small", metric="cosine")
        assert config.dim == 1536
        assert config.model == "text-embedding-3-small"
        assert config.metric == "cosine"

    def test_vector_config_default_metric(self):
        """测试向量配置默认度量。"""
        config = VectorConfig(dim=1536, model="text-embedding-3-small")
        assert config.metric == "cosine"

    def test_vector_config_invalid_dim(self):
        """测试无效维度。"""
        with pytest.raises(ValueError, match="dim must be positive"):
            VectorConfig(dim=0, model="text-embedding-3-small")

    def test_vector_config_negative_dim(self):
        """测试负数维度。"""
        with pytest.raises(ValueError, match="dim must be positive"):
            VectorConfig(dim=-100, model="text-embedding-3-small")

    def test_vector_config_invalid_metric(self):
        """测试无效度量。"""
        with pytest.raises(ValueError, match="metric must be one of"):
            VectorConfig(dim=1536, model="text-embedding-3-small", metric="invalid")


class TestNodeType:
    """节点类型测试。"""

    def test_create_node_type_success(self):
        """测试创建节点类型成功。"""
        node = NodeType(
            table="characters",
            identity=["name"],
            json_schema={
                "type": "object",
                "properties": {"name": {"type": "string"}, "bio": {"type": "string"}},
            },
        )
        assert node.table == "characters"
        assert node.identity == ["name"]
        assert node.json_schema is not None

    def test_node_type_with_vectors(self):
        """测试带向量配置的节点类型。"""
        node = NodeType(
            table="documents",
            identity=["doc_id"],
            vectors={
                "content_embedding": VectorConfig(dim=1536, model="text-embedding-3-small")
            },
        )
        assert node.vectors is not None
        assert "content_embedding" in node.vectors

    def test_node_type_empty_identity(self):
        """测试空标识字段。"""
        with pytest.raises(ValueError, match="identity must not be empty"):
            NodeType(table="test", identity=[])

    def test_node_type_empty_table(self):
        """测试空表名。"""
        with pytest.raises(ValueError, match="table name required"):
            NodeType(table="", identity=["id"])

    def test_node_type_whitespace_table(self):
        """测试空白表名。"""
        with pytest.raises(ValueError, match="table name required"):
            NodeType(table="   ", identity=["id"])

    def test_node_type_invalid_schema_type(self):
        """测试无效 Schema 类型。"""
        with pytest.raises(ValueError, match="unsupported schema type"):
            NodeType(
                table="test",
                identity=["id"],
                json_schema={"type": "invalid_type"},
            )

    def test_node_type_extra_fields_forbidden(self):
        """测试禁止额外字段。"""
        with pytest.raises(Exception):
            NodeType(table="test", identity=["id"], unknown_field="value")


class TestEdgeType:
    """边类型测试。"""

    def test_create_edge_type_success(self):
        """测试创建边类型成功。"""
        edge = EdgeType(
            from_="Character",
            to="Document",
            cardinality="N:1",
        )
        assert edge.from_ == "Character"
        assert edge.to == "Document"
        assert edge.cardinality == "N:1"

    def test_edge_type_with_schema(self):
        """测试带 Schema 的边类型。"""
        edge = EdgeType(
            from_="Character",
            to="Document",
            json_schema={
                "type": "object",
                "properties": {"role": {"type": "string"}},
            },
        )
        assert edge.json_schema is not None

    def test_edge_type_invalid_cardinality(self):
        """测试无效基数。"""
        with pytest.raises(ValueError, match="cardinality must be one of"):
            EdgeType(from_="Character", to="Document", cardinality="invalid")

    def test_edge_type_valid_cardinalities(self):
        """测试所有有效基数。"""
        valid_cardinalities = ["1:1", "1:N", "N:1", "N:N"]
        for cardinality in valid_cardinalities:
            edge = EdgeType(from_="A", to="B", cardinality=cardinality)
            assert edge.cardinality == cardinality

    def test_edge_type_from_alias(self):
        """测试 from 别名。"""
        edge = EdgeType(**{"from": "Character", "to": "Document"})
        assert edge.from_ == "Character"


class TestOntology:
    """本体测试。"""

    def test_create_empty_ontology(self):
        """测试创建空本体。"""
        ontology = Ontology()
        assert ontology.nodes == {}
        assert ontology.edges == {}

    def test_ontology_with_nodes(self):
        """测试带节点的本体。"""
        ontology = Ontology(
            nodes={
                "Character": NodeType(table="characters", identity=["name"]),
                "Document": NodeType(table="documents", identity=["doc_id"]),
            }
        )
        assert "Character" in ontology.nodes
        assert "Document" in ontology.nodes

    def test_ontology_with_edges(self):
        """测试带边的本体。"""
        ontology = Ontology(
            nodes={
                "Character": NodeType(table="characters", identity=["name"]),
                "Document": NodeType(table="documents", identity=["doc_id"]),
            },
            edges={
                "authored": EdgeType(from_="Character", to="Document"),
            },
        )
        assert "authored" in ontology.edges

    def test_ontology_edge_reference_invalid_from(self):
        """测试边引用无效起始节点。"""
        with pytest.raises(ValueError, match="references unknown node type"):
            Ontology(
                nodes={"Character": NodeType(table="characters", identity=["name"])},
                edges={"authored": EdgeType(from_="UnknownNode", to="Character")},
            )

    def test_ontology_edge_reference_invalid_to(self):
        """测试边引用无效目标节点。"""
        with pytest.raises(ValueError, match="references unknown node type"):
            Ontology(
                nodes={"Character": NodeType(table="characters", identity=["name"])},
                edges={"knows": EdgeType(from_="Character", to="UnknownNode")},
            )

    def test_ontology_extra_fields_forbidden(self):
        """测试禁止额外字段。"""
        with pytest.raises(Exception):
            Ontology(unknown_field="value")


class TestSchemaValidation:
    """Schema 校验测试。"""

    def test_validate_simple_object(self):
        """测试校验简单对象。"""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        }
        data = {"name": "张明", "age": 28}
        result = validate_json_by_schema(schema, data)
        assert result == data

    def test_validate_missing_required(self):
        """测试缺失必填字段。"""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name", "email"],
        }
        data = {"name": "张明"}
        with pytest.raises(ValueError, match="missing required property"):
            validate_json_by_schema(schema, data)

    def test_validate_type_mismatch(self):
        """测试类型不匹配。"""
        schema = {"type": "object", "properties": {"age": {"type": "integer"}}}
        data = {"age": "not a number"}
        with pytest.raises(ValueError, match="expected"):
            validate_json_by_schema(schema, data)

    def test_validate_array(self):
        """测试校验数组。"""
        schema = {
            "type": "array",
            "items": {"type": "string"},
        }
        data = ["a", "b", "c"]
        result = validate_json_by_schema(schema, data)
        assert result == data

    def test_validate_nested_object(self):
        """测试校验嵌套对象。"""
        schema = {
            "type": "object",
            "properties": {
                "metadata": {
                    "type": "object",
                    "properties": {"department": {"type": "string"}},
                }
            },
        }
        data = {"metadata": {"department": "研发部"}}
        result = validate_json_by_schema(schema, data)
        assert result == data

    def test_validate_datetime_format(self):
        """测试日期时间格式。"""
        schema = {
            "type": "object",
            "properties": {"created_at": {"type": "string", "format": "date-time"}},
        }
        data = {"created_at": "2024-01-20T10:00:00Z"}
        result = validate_json_by_schema(schema, data)
        assert result is not None

    def test_validate_null_type(self):
        """测试 null 类型。"""
        schema = {"type": "null"}
        data = None
        result = validate_json_by_schema(schema, data)
        assert result is None

    def test_validate_no_type(self):
        """测试无类型 Schema。"""
        schema = {}
        data = {"any": "value"}
        result = validate_json_by_schema(schema, data)
        assert result == data


class TestOntologyMixin:
    """本体 Mixin 测试。"""

    def test_generate_node_ddl(self, engine):
        """测试生成节点 DDL。"""
        ddl = engine._generate_node_ddl(engine.ontology.nodes["Character"])
        assert "CREATE TABLE IF NOT EXISTS characters" in ddl
        assert "__id BIGINT PRIMARY KEY" in ddl
        assert "__created_at TIMESTAMP" in ddl
        assert "__updated_at TIMESTAMP" in ddl
        assert "name VARCHAR" in ddl
        assert "bio VARCHAR" in ddl

    def test_generate_edge_ddl(self, engine):
        """测试生成边 DDL。"""
        ddl = engine._generate_edge_ddl("knows", engine.ontology.edges["knows"])
        assert "CREATE TABLE IF NOT EXISTS edge_knows" in ddl
        assert "__id BIGINT PRIMARY KEY" in ddl
        assert "__from_id BIGINT NOT NULL" in ddl
        assert "__to_id BIGINT NOT NULL" in ddl

    def test_get_bundle_schema(self, engine):
        """测试获取知识包 Schema。"""
        result = engine.get_bundle_schema()
        assert "full_bundle_schema" in result
        assert "example_yaml" in result
        assert result["full_bundle_schema"]["type"] == "array"

    def test_json_type_to_duckdb_string(self, engine):
        """测试 JSON 类型到 DuckDB 类型映射。"""
        assert engine._json_type_to_duckdb({"type": "string"}) == "VARCHAR"
        assert engine._json_type_to_duckdb({"type": "integer"}) == "BIGINT"
        assert engine._json_type_to_duckdb({"type": "number"}) == "DOUBLE"
        assert engine._json_type_to_duckdb({"type": "boolean"}) == "BOOLEAN"
        assert engine._json_type_to_duckdb({"type": "array"}) == "JSON"
        assert engine._json_type_to_duckdb({"type": "object"}) == "JSON"

    def test_json_type_to_duckdb_datetime(self, engine):
        """测试日期时间类型映射。"""
        assert engine._json_type_to_duckdb({"type": "string", "format": "date-time"}) == "TIMESTAMP"
        assert engine._json_type_to_duckdb({"type": "string", "format": "date"}) == "DATE"
        assert engine._json_type_to_duckdb({"type": "string", "format": "time"}) == "TIME"

    def test_get_info(self, engine):
        """测试获取知识库介绍。"""
        result = engine.get_info()
        assert "# 知识库介绍" in result
        assert "## 使用说明" in result
        assert "## 导入数据格式" in result
        assert "## 表结构" in result
        assert "## 知识图谱关系" in result

    def test_get_info_contains_node_tables(self, engine):
        """测试知识库介绍包含节点表。"""
        result = engine.get_info()
        assert "### 节点表" in result
        assert "Character (characters)" in result

    def test_get_info_contains_edge_tables(self, engine):
        """测试知识库介绍包含边表。"""
        result = engine.get_info()
        assert "### 边表" in result
        assert "edge_knows" in result

    def test_get_info_contains_system_tables(self, engine):
        """测试知识库介绍包含系统表。"""
        result = engine.get_info()
        assert "### 系统表" in result
        assert "_sys_search_index" in result
        assert "_sys_search_cache" in result

    def test_get_info_contains_relationship_table(self, engine):
        """测试知识库介绍包含关系表格。"""
        result = engine.get_info()
        assert "### 关系详情" in result
        assert "| 边名称 |" in result
        assert "| knows |" in result

    def test_get_info_contains_mermaid_graph(self, engine):
        """测试知识库介绍包含 Mermaid 图。"""
        result = engine.get_info()
        assert "```mermaid" in result
        assert "graph LR" in result
        assert "Character" in result
