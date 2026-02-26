"""核心配置模型定义。

本模块定义核心引擎的配置数据模型。
"""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class DatabaseConfig(BaseModel):
    """数据库配置模型。

    定义数据库连接相关配置项。

    Attributes:
        mode: 数据库模式，file（文件）或 memory（内存）。
        temp_dir: 临时文件目录，None 表示使用系统默认临时目录。
        keep_temp_on_exit: 退出时是否保留临时文件（用于调试）。
    """

    mode: Literal["memory", "file"] = "file"
    temp_dir: Path | None = None
    keep_temp_on_exit: bool = False

    @field_validator("temp_dir", mode="before")
    @classmethod
    def validate_temp_dir(cls, v: str | Path | None) -> Path | None:
        """验证并转换临时目录路径。

        Args:
            v: 待验证的路径值。

        Returns:
            转换后的 Path 对象或 None。
        """
        if v is None:
            return None
        if isinstance(v, str):
            return Path(v)
        return v


class StorageConfig(BaseModel):
    """存储配置模型。

    定义数据存储相关配置项。

    Attributes:
        data_dir: 数据目录路径，用于存储数据库文件和索引。
        partition_by_date: 是否按日期分区存储数据。
        max_rows_per_file: 每个文件最大行数，用于分片导出。
    """

    data_dir: Path
    partition_by_date: bool = True
    max_rows_per_file: int = Field(default=1000, ge=100, le=10000)

    @field_validator("data_dir", mode="before")
    @classmethod
    def validate_data_dir(cls, v: str | Path) -> Path:
        """验证并转换数据目录路径。

        Args:
            v: 待验证的路径值，支持字符串或 Path 对象。

        Returns:
            转换后的 Path 对象。
        """
        if isinstance(v, str):
            return Path(v)
        return v


class GlobalConfig(BaseModel):
    """全局配置模型。

    定义全局配置项，从 config.yaml 读取。

    Attributes:
        chunk_size: 文本切片长度，默认 800 字符。
        tokenizer: 分词器类型。
    """

    chunk_size: int = Field(default=800, ge=100, le=8000)
    tokenizer: str = "jieba"


class CoreConfig(BaseModel):
    """核心引擎配置模型。

    定义核心引擎的完整配置，包含存储、嵌入向量和全局配置。

    Attributes:
        storage: 存储配置实例。
        global_config: 全局配置实例。
        database: 数据库配置实例。
        embedding_dim: 嵌入向量维度，默认为 1536。
    """

    storage: StorageConfig
    global_config: GlobalConfig = Field(default_factory=GlobalConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    embedding_dim: int = Field(default=1536, ge=1, le=4096)

    @field_validator("embedding_dim")
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
            raise ValueError("embedding_dim must be positive")
        if v > 4096:
            raise ValueError("embedding_dim must not exceed 4096")
        return v
