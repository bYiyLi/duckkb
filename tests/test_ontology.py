import pytest

from duckkb.ontology import (
    EdgeType,
    NodeType,
    Ontology,
    OntologyEngine,
    VectorConfig,
    generate_node_ddl,
    generate_nodes_ddl,
)


class TestVectorConfig:
    def test_valid_config(self):
        config = VectorConfig(dim=1536, model="text-embedding-3-small")
        assert config.dim == 1536
        assert config.model == "text-embedding-3-small"
        assert config.metric == "cosine"

    def test_custom_metric(self):
        config = VectorConfig(dim=1536, model="text-embedding-3-small", metric="l2")
        assert config.metric == "l2"

    def test_invalid_dim(self):
        with pytest.raises(ValueError, match="dim"):
            VectorConfig(dim=0, model="text-embedding-3-small")

    def test_invalid_metric(self):
        with pytest.raises(ValueError, match="metric"):
            VectorConfig(dim=1536, model="text-embedding-3-small", metric="invalid")


class TestNodeType:
    def test_valid_node(self):
        node = NodeType(
            table="characters",
            identity=["id"],
            schema={
                "type": "object",
                "properties": {"id": {"type": "string"}, "name": {"type": "string"}},
            },
        )
        assert node.table == "characters"
        assert node.identity == ["id"]

    def test_missing_identity(self):
        with pytest.raises(ValueError, match="identity"):
            NodeType(table="characters", identity=[])

    def test_missing_table(self):
        with pytest.raises(ValueError, match="table"):
            NodeType(table="", identity=["id"])

    def test_with_vectors(self):
        node = NodeType(
            table="characters",
            identity=["id"],
            vectors={
                "description_embedding": VectorConfig(dim=1536, model="text-embedding-3-small")
            },
        )
        assert node.vectors is not None
        assert "description_embedding" in node.vectors

    def test_invalid_json_schema_type(self):
        with pytest.raises(ValueError, match="unsupported schema type"):
            NodeType(
                table="characters",
                identity=["id"],
                schema={"type": "invalid_type"},
            )

    def test_valid_json_schema(self):
        node = NodeType(
            table="characters",
            identity=["id"],
            schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
            },
        )
        assert node.json_schema is not None


class TestEdgeType:
    def test_valid_edge(self):
        edge = EdgeType(from_="Character", to="Location")
        assert edge.from_ == "Character"
        assert edge.to == "Location"

    def test_edge_with_cardinality(self):
        edge = EdgeType(from_="Character", to="Location", cardinality="N:1")
        assert edge.cardinality == "N:1"

    def test_invalid_cardinality(self):
        with pytest.raises(ValueError, match="cardinality"):
            EdgeType(from_="Character", to="Location", cardinality="invalid")

    def test_edge_with_schema(self):
        edge = EdgeType(
            from_="Character",
            to="Location",
            schema={
                "type": "object",
                "properties": {"since": {"type": "string", "format": "date-time"}},
            },
        )
        assert edge.json_schema is not None

    def test_invalid_edge_schema_type(self):
        with pytest.raises(ValueError, match="unsupported schema type"):
            EdgeType(
                from_="Character",
                to="Location",
                schema={"type": "invalid_type"},
            )


class TestOntology:
    def test_empty_ontology(self):
        ontology = Ontology()
        assert ontology.nodes == {}
        assert ontology.edges == {}

    def test_ontology_with_nodes(self):
        ontology = Ontology(
            nodes={
                "Character": NodeType(
                    table="characters",
                    identity=["id"],
                    schema={"type": "object", "properties": {"id": {"type": "string"}}},
                )
            }
        )
        assert "Character" in ontology.nodes
        assert ontology.nodes["Character"].table == "characters"

    def test_ontology_with_edges(self):
        ontology = Ontology(
            nodes={
                "Character": NodeType(table="characters", identity=["id"]),
                "Location": NodeType(table="locations", identity=["id"]),
            },
            edges={"located_at": EdgeType(from_="Character", to="Location", cardinality="N:1")},
        )
        assert "located_at" in ontology.edges
        assert ontology.edges["located_at"].from_ == "Character"

    def test_edge_references_unknown_from_node(self):
        with pytest.raises(ValueError, match="references unknown node type"):
            Ontology(
                nodes={
                    "Character": NodeType(table="characters", identity=["id"]),
                },
                edges={"located_at": EdgeType(from_="Character", to="Location")},
            )

    def test_edge_references_unknown_to_node(self):
        with pytest.raises(ValueError, match="references unknown node type"):
            Ontology(
                nodes={
                    "Location": NodeType(table="locations", identity=["id"]),
                },
                edges={"located_at": EdgeType(from_="Character", to="Location")},
            )


class TestDDLGeneration:
    def test_generate_node_ddl_simple(self):
        node = NodeType(
            table="characters",
            identity=["id"],
            schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "level": {"type": "integer"},
                },
            },
        )
        ddl = generate_node_ddl("Character", node)
        assert "CREATE TABLE IF NOT EXISTS characters" in ddl
        assert "id VARCHAR" in ddl
        assert "name VARCHAR" in ddl
        assert "level INTEGER" in ddl
        assert "PRIMARY KEY (id)" in ddl

    def test_generate_node_ddl_datetime(self):
        node = NodeType(
            table="events",
            identity=["id"],
            schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "created_at": {"type": "string", "format": "date-time"},
                },
            },
        )
        ddl = generate_node_ddl("Event", node)
        assert "created_at TIMESTAMP" in ddl

    def test_generate_nodes_ddl_multiple(self):
        ontology = Ontology(
            nodes={
                "Character": NodeType(
                    table="characters",
                    identity=["id"],
                    schema={"type": "object", "properties": {"id": {"type": "string"}}},
                ),
                "Location": NodeType(
                    table="locations",
                    identity=["id"],
                    schema={"type": "object", "properties": {"id": {"type": "string"}}},
                ),
            }
        )
        ddl = generate_nodes_ddl(ontology)
        assert "CREATE TABLE IF NOT EXISTS characters" in ddl
        assert "CREATE TABLE IF NOT EXISTS locations" in ddl

    def test_generate_nodes_ddl_empty(self):
        ontology = Ontology()
        ddl = generate_nodes_ddl(ontology)
        assert ddl == ""


class TestOntologyEngine:
    def test_get_node_tables(self):
        ontology = Ontology(
            nodes={
                "Character": NodeType(table="characters", identity=["id"]),
                "Location": NodeType(table="locations", identity=["id"]),
            }
        )
        engine = OntologyEngine(ontology)
        tables = engine.get_node_tables()
        assert tables["Character"] == "characters"
        assert tables["Location"] == "locations"

    def test_get_node_by_table(self):
        ontology = Ontology(
            nodes={
                "Character": NodeType(
                    table="characters",
                    identity=["id"],
                    schema={"type": "object", "properties": {"id": {"type": "string"}}},
                )
            }
        )
        engine = OntologyEngine(ontology)
        node = engine.get_node_by_table("characters")
        assert node is not None
        assert node.table == "characters"

        node = engine.get_node_by_table("nonexistent")
        assert node is None

    def test_has_vectors(self):
        ontology_no_vectors = Ontology(
            nodes={"Character": NodeType(table="characters", identity=["id"])}
        )
        engine = OntologyEngine(ontology_no_vectors)
        assert engine.has_vectors() is False

        ontology_with_vectors = Ontology(
            nodes={
                "Character": NodeType(
                    table="characters",
                    identity=["id"],
                    vectors={
                        "desc_embedding": VectorConfig(dim=1536, model="text-embedding-3-small")
                    },
                )
            }
        )
        engine = OntologyEngine(ontology_with_vectors)
        assert engine.has_vectors() is True
