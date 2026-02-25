"""配置管理模块。

本模块负责管理 DuckKB 的全局配置和知识库配置，包括：
- OpenAI API 配置（全局）
- 嵌入模型配置（知识库级别）
- 日志级别配置
- 本体定义配置
- 应用上下文单例管理
"""

import threading
from pathlib import Path

import yaml
from openai import AsyncOpenAI
from pydantic import BaseModel, Field, field_validator

from duckkb.constants import (
    CONFIG_FILE_NAME,
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_LOG_LEVEL,
    EMBEDDING_MODEL_DIMS,
    VALID_EMBEDDING_DIMS,
    VALID_LOG_LEVELS,
)
from duckkb.core.models.ontology import Ontology


class GlobalConfig(BaseModel):
    """全局配置模型。

    存储全局级别的配置项，如 OpenAI API 凭证。

    Attributes:
        OPENAI_API_KEY: OpenAI API 密钥，从环境变量读取。
        OPENAI_BASE_URL: OpenAI API 基础 URL，用于自定义端点。
    """

    OPENAI_API_KEY: str | None = None
    OPENAI_BASE_URL: str | None = None


class EmbeddingConfig(BaseModel):
    """嵌入模型配置。

    存储嵌入模型相关配置。

    Attributes:
        model: 嵌入模型名称，默认为 text-embedding-3-small。
        dim: 嵌入向量维度，必须为 1536 或 3072。
    """

    model: str = DEFAULT_EMBEDDING_MODEL
    dim: int = DEFAULT_EMBEDDING_DIM

    @field_validator("dim")
    @classmethod
    def validate_dim(cls, v: int) -> int:
        """验证嵌入向量维度。

        Args:
            v: 待验证的维度值。

        Returns:
            验证通过的维度值。

        Raises:
            ValueError: 维度值无效时抛出。
        """
        if v <= 0:
            raise ValueError("dim must be positive")
        if v not in VALID_EMBEDDING_DIMS:
            raise ValueError(f"dim must be one of {list(VALID_EMBEDDING_DIMS)} for OpenAI models")
        return v

    @field_validator("model")
    @classmethod
    def validate_model(cls, v: str) -> str:
        """验证嵌入模型名称。

        Args:
            v: 待验证的模型名称。

        Returns:
            验证通过的模型名称。

        Raises:
            ValueError: 模型名称无效时抛出。
        """
        if v not in EMBEDDING_MODEL_DIMS:
            raise ValueError(f"model must be one of: {list(EMBEDDING_MODEL_DIMS.keys())}")
        return v


class KBConfig(BaseModel):
    """知识库配置模型。

    存储单个知识库的配置项，包括嵌入模型、日志设置和本体定义。

    Attributes:
        embedding: 嵌入模型配置。
        log_level: 日志级别，默认为 INFO。
        ontology: 本体定义。
    """

    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    log_level: str = DEFAULT_LOG_LEVEL
    ontology: Ontology = Field(default_factory=Ontology)
    usage_instructions: str | None = None

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """验证日志级别。

        Args:
            v: 待验证的日志级别字符串。

        Returns:
            验证通过的大写日志级别。

        Raises:
            ValueError: 日志级别无效时抛出。
        """
        v_upper = v.upper()
        if v_upper not in VALID_LOG_LEVELS:
            raise ValueError(f"log_level must be one of: {list(VALID_LOG_LEVELS)}")
        return v_upper

    @classmethod
    def from_yaml(cls, kb_path: Path) -> "KBConfig":
        """从 YAML 配置文件加载知识库配置。

        Args:
            kb_path: 知识库目录路径。

        Returns:
            加载的 KBConfig 实例，若配置文件不存在则返回默认配置。
        """
        config_path = kb_path / CONFIG_FILE_NAME
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            embedding_config = data.get("embedding", {})
            ontology_config = data.get("ontology", {})
            return cls(
                embedding=EmbeddingConfig(
                    model=embedding_config.get("model", DEFAULT_EMBEDDING_MODEL),
                    dim=embedding_config.get("dim", DEFAULT_EMBEDDING_DIM),
                ),
                log_level=data.get("log_level", DEFAULT_LOG_LEVEL),
                ontology=Ontology(**ontology_config) if ontology_config else Ontology(),
                usage_instructions=data.get("usage_instructions"),
            )
        return cls()

    @property
    def EMBEDDING_MODEL(self) -> str:
        """兼容旧代码的嵌入模型名称属性。"""
        return self.embedding.model

    @property
    def EMBEDDING_DIM(self) -> int:
        """兼容旧代码的嵌入维度属性。"""
        return self.embedding.dim

    @property
    def LOG_LEVEL(self) -> str:
        """兼容旧代码的日志级别属性。"""
        return self.log_level


class AppContext:
    """应用上下文单例类。

    管理整个应用运行时的共享状态，包括配置、数据库连接和外部客户端。
    采用单例模式确保全局唯一实例，使用线程锁保证线程安全。

    Attributes:
        kb_path: 知识库目录的绝对路径。
        kb_config: 知识库配置实例。
        global_config: 全局配置实例。
    """

    _instance: "AppContext | None" = None
    _lock: threading.Lock = threading.Lock()

    def __init__(self, kb_path: Path):
        """初始化应用上下文。

        Args:
            kb_path: 知识库目录路径。
        """
        self.kb_path = kb_path.resolve()
        self.kb_config = KBConfig.from_yaml(kb_path)
        self.global_config = GlobalConfig()
        self._openai_client: AsyncOpenAI | None = None
        self._jieba_initialized = False

    @property
    def openai_client(self) -> AsyncOpenAI:
        """获取 OpenAI 异步客户端（懒加载）。

        Returns:
            AsyncOpenAI 客户端实例。
        """
        if self._openai_client is None:
            self._openai_client = AsyncOpenAI(
                api_key=self.global_config.OPENAI_API_KEY,
                base_url=self.global_config.OPENAI_BASE_URL,
            )
        return self._openai_client

    @property
    def jieba_initialized(self) -> bool:
        """获取 jieba 分词器初始化状态。"""
        return self._jieba_initialized

    @jieba_initialized.setter
    def jieba_initialized(self, value: bool) -> None:
        """设置 jieba 分词器初始化状态。"""
        self._jieba_initialized = value

    @classmethod
    def get(cls) -> "AppContext":
        """获取应用上下文单例实例。

        Returns:
            AppContext 单例实例。

        Raises:
            RuntimeError: 若未初始化则抛出异常。
        """
        with cls._lock:
            if cls._instance is None:
                raise RuntimeError("AppContext not initialized. Call AppContext.init() first.")
            return cls._instance

    @classmethod
    def init(cls, kb_path: Path) -> "AppContext":
        """初始化应用上下文单例。

        使用双重检查锁定模式确保线程安全。

        Args:
            kb_path: 知识库目录路径。

        Returns:
            新创建或已存在的 AppContext 实例。
        """
        if cls._instance is not None:
            return cls._instance

        with cls._lock:
            if cls._instance is None:
                cls._instance = AppContext(kb_path)
            return cls._instance

    @classmethod
    def reset(cls) -> None:
        """重置应用上下文单例（主要用于测试）。"""
        with cls._lock:
            cls._instance = None


def get_kb_config() -> KBConfig:
    """获取当前知识库配置。

    Returns:
        当前知识库的 KBConfig 实例。
    """
    return AppContext.get().kb_config


def get_global_config() -> GlobalConfig:
    """获取全局配置。

    Returns:
        全局 GlobalConfig 实例。
    """
    return AppContext.get().global_config


def get_openai_client() -> AsyncOpenAI:
    """获取 OpenAI 异步客户端。

    Returns:
        AsyncOpenAI 客户端实例。
    """
    return AppContext.get().openai_client
