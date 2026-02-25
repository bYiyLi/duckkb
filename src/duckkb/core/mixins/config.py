"""配置管理 Mixin。"""

from pathlib import Path

import yaml

from duckkb.config import KBConfig
from duckkb.constants import CONFIG_FILE_NAME
from duckkb.core.base import BaseEngine
from duckkb.core.config import CoreConfig, StorageConfig


class ConfigMixin(BaseEngine):
    """配置管理 Mixin。

    负责从文件读取和解析配置。

    Attributes:
        config_path: 配置文件路径。
        config: 配置对象。
    """

    def __init__(
        self, *args, config_path: Path | str | None = None, **kwargs
    ) -> None:
        """初始化配置 Mixin。

        Args:
            config_path: 配置文件路径，默认为 kb_path/config.yaml。
        """
        super().__init__(*args, **kwargs)
        self._config_path = Path(config_path) if config_path else None
        self._config: CoreConfig | None = None
        self._kb_config: KBConfig | None = None

    @property
    def config_path(self) -> Path:
        """配置文件路径，默认为 kb_path/config.yaml。"""
        if self._config_path is None:
            return self.kb_path / CONFIG_FILE_NAME
        return self._config_path

    @property
    def config(self) -> CoreConfig:
        """配置对象（懒加载）。"""
        if self._config is None:
            self._config = self._load_config()
        return self._config

    @property
    def kb_config(self) -> KBConfig:
        """知识库配置对象（懒加载）。"""
        if self._kb_config is None:
            self._kb_config = self._load_kb_config()
        return self._kb_config

    def _load_config(self) -> CoreConfig:
        """从文件加载核心配置。

        Returns:
            核心配置实例。
        """
        kb_config = self.kb_config
        data_dir = self.kb_path / "data"

        if self.config_path.exists():
            with open(self.config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            storage_config = data.get("storage", {})
            if storage_config and "data_dir" in storage_config:
                data_dir = Path(storage_config["data_dir"])

        return CoreConfig(
            storage=StorageConfig(
                data_dir=data_dir,
                partition_by_date=True,
            ),
            embedding_dim=kb_config.embedding.dim,
        )

    def _load_kb_config(self) -> KBConfig:
        """从文件加载知识库配置。

        Returns:
            知识库配置实例。
        """
        return KBConfig.from_yaml(self.kb_path)
