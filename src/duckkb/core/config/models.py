"""核心配置模型定义。

本模块定义核心引擎的配置数据模型。
"""

from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class StorageConfig(BaseModel):
    """存储配置模型。

    定义数据存储相关配置项。

    Attributes:
        data_dir: 数据目录路径，用于存储数据库文件和索引。
        partition_by_date: 是否按日期分区存储数据。
    """

    data_dir: Path
    partition_by_date: bool = True

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


class CoreConfig(BaseModel):
    """核心引擎配置模型。

    定义核心引擎的完整配置，包含存储和嵌入向量配置。

    Attributes:
        storage: 存储配置实例。
        embedding_dim: 嵌入向量维度，默认为 1536。
    """

    storage: StorageConfig
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
