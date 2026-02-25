"""核心配置模块。

本模块定义核心引擎的配置模型，包括：
- 存储配置
- 核心引擎配置
"""

from duckkb.core.config.models import CoreConfig, StorageConfig

__all__ = [
    "CoreConfig",
    "StorageConfig",
]
