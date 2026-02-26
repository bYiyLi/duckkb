import pytest

from duckkb.config import (
    EMBEDDING_MODEL_DIMS,
    AppContext,
    EmbeddingConfig,
    GlobalConfig,
    KBConfig,
)
from duckkb.core.models.ontology import Ontology


def test_default_kb_config():
    config = KBConfig()
    assert config.log_level == "INFO"
    assert config.embedding.model == "text-embedding-3-small"
    assert config.embedding.dim == 1536
    assert config.EMBEDDING_MODEL == "text-embedding-3-small"
    assert config.EMBEDDING_DIM == 1536
    assert config.LOG_LEVEL == "INFO"


def test_kb_config_from_yaml(tmp_path):
    config_content = """
embedding:
  model: text-embedding-3-large
  dim: 3072
log_level: DEBUG
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_content)

    config = KBConfig.from_yaml(tmp_path)
    assert config.embedding.model == "text-embedding-3-large"
    assert config.embedding.dim == 3072
    assert config.log_level == "DEBUG"
    assert config.EMBEDDING_MODEL == "text-embedding-3-large"
    assert config.EMBEDDING_DIM == 3072
    assert config.LOG_LEVEL == "DEBUG"


def test_kb_config_from_yaml_missing_file(tmp_path):
    config = KBConfig.from_yaml(tmp_path)
    assert config.embedding.model == "text-embedding-3-small"
    assert config.embedding.dim == 1536
    assert config.log_level == "INFO"


def test_kb_config_with_ontology(tmp_path):
    config_content = """
embedding:
  model: text-embedding-3-small
  dim: 1536
log_level: INFO
ontology:
  nodes:
    Character:
      table: characters
      identity: [id]
      schema:
        type: object
        properties:
          id:
            type: string
          name:
            type: string
        required: [id, name]
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_content)

    config = KBConfig.from_yaml(tmp_path)
    assert "Character" in config.ontology.nodes
    assert config.ontology.nodes["Character"].table == "characters"


def test_global_config():
    config = GlobalConfig(OPENAI_API_KEY="test-key", OPENAI_BASE_URL="https://api.example.com")
    assert config.OPENAI_API_KEY == "test-key"
    assert config.OPENAI_BASE_URL == "https://api.example.com"


def test_app_context(tmp_path):
    AppContext.reset()
    ctx = AppContext.init(tmp_path)
    assert ctx.kb_path == tmp_path.resolve()
    assert ctx.kb_config.embedding.model == "text-embedding-3-small"
    AppContext.reset()


def test_app_context_get():
    AppContext.reset()
    with pytest.raises(RuntimeError, match="not initialized"):
        AppContext.get()


def test_embedding_model_dims_mapping():
    assert EMBEDDING_MODEL_DIMS["text-embedding-3-small"] == 1536
    assert EMBEDDING_MODEL_DIMS["text-embedding-3-large"] == 3072


def test_embedding_config_validation_invalid_dim():
    with pytest.raises(ValueError, match="dim"):
        EmbeddingConfig(dim=512)


def test_embedding_config_validation_invalid_model():
    with pytest.raises(ValueError, match="model"):
        EmbeddingConfig(model="invalid-model")


def test_kb_config_validation_invalid_log_level():
    with pytest.raises(ValueError, match="log_level"):
        KBConfig(log_level="INVALID")


def test_ontology_default():
    ontology = Ontology()
    assert ontology.nodes == {}
    assert ontology.edges == {}
