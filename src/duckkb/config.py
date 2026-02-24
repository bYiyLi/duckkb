"""配置管理模块。

本模块负责管理 DuckKB 的全局配置和知识库配置，包括：
- OpenAI API 配置（全局）
- 嵌入模型配置（知识库级别）
- 日志级别配置
- 应用上下文单例管理
"""

from pathlib import Path

import yaml
from openai import AsyncOpenAI
from pydantic import BaseModel, field_validator

EMBEDDING_MODEL_DIMS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}

VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class GlobalConfig(BaseModel):
    """全局配置模型。

    存储全局级别的配置项，如 OpenAI API 凭证。

    Attributes:
        OPENAI_API_KEY: OpenAI API 密钥，从环境变量读取。
        OPENAI_BASE_URL: OpenAI API 基础 URL，用于自定义端点。
    """

    OPENAI_API_KEY: str | None = None
    OPENAI_BASE_URL: str | None = None


class KBConfig(BaseModel):
    """知识库配置模型。

    存储单个知识库的配置项，包括嵌入模型和日志设置。

    Attributes:
        EMBEDDING_MODEL: 嵌入模型名称，默认为 text-embedding-3-small。
        EMBEDDING_DIM: 嵌入向量维度，必须为 1536 或 3072。
        LOG_LEVEL: 日志级别，默认为 INFO。
    """

    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIM: int = 1536
    LOG_LEVEL: str = "INFO"

    @field_validator("EMBEDDING_DIM")
    @classmethod
    def validate_embedding_dim(cls, v: int) -> int:
        """验证嵌入向量维度。

        Args:
            v: 待验证的维度值。

        Returns:
            验证通过的维度值。

        Raises:
            ValueError: 维度值无效时抛出。
        """
        if v <= 0:
            raise ValueError("EMBEDDING_DIM must be positive")
        if v not in [1536, 3072]:
            raise ValueError("EMBEDDING_DIM must be 1536 or 3072 for OpenAI models")
        return v

    @field_validator("EMBEDDING_MODEL")
    @classmethod
    def validate_embedding_model(cls, v: str) -> str:
        """验证嵌入模型名称。

        Args:
            v: 待验证的模型名称。

        Returns:
            验证通过的模型名称。

        Raises:
            ValueError: 模型名称无效时抛出。
        """
        if v not in EMBEDDING_MODEL_DIMS:
            raise ValueError(f"EMBEDDING_MODEL must be one of: {list(EMBEDDING_MODEL_DIMS.keys())}")
        return v

    @field_validator("LOG_LEVEL")
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
            raise ValueError(f"LOG_LEVEL must be one of: {list(VALID_LOG_LEVELS)}")
        return v_upper

    @classmethod
    def from_yaml(cls, kb_path: Path) -> "KBConfig":
        """从 YAML 配置文件加载知识库配置。

        Args:
            kb_path: 知识库目录路径。

        Returns:
            加载的 KBConfig 实例，若配置文件不存在则返回默认配置。
        """
        config_path = kb_path / "config.yaml"
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            embedding_config = data.get("embedding", {})
            return cls(
                EMBEDDING_MODEL=embedding_config.get("model", "text-embedding-3-small"),
                EMBEDDING_DIM=embedding_config.get("dim", 1536),
                LOG_LEVEL=data.get("log_level", "INFO"),
            )
        return cls()


class AppContext:
    """应用上下文单例类。

    管理整个应用运行时的共享状态，包括配置、数据库连接和外部客户端。
    采用单例模式确保全局唯一实例。

    Attributes:
        kb_path: 知识库目录的绝对路径。
        kb_config: 知识库配置实例。
        global_config: 全局配置实例。
    """

    _instance: "AppContext | None" = None

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
        if cls._instance is None:
            raise RuntimeError("AppContext not initialized. Call AppContext.init() first.")
        return cls._instance

    @classmethod
    def init(cls, kb_path: Path) -> "AppContext":
        """初始化应用上下文单例。

        Args:
            kb_path: 知识库目录路径。

        Returns:
            新创建的 AppContext 实例。
        """
        cls._instance = AppContext(kb_path)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """重置应用上下文单例（主要用于测试）。"""
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
