# DuckKB 核心引擎重构计划

## 设计理念

**核心原则**: 职责分离，每个 Mixin 只负责一件事。

* BaseEngine 只定义接口和存储基础路径

* ConfigMixin 负责配置读取和解析

* DBMixin 负责 DuckDB 连接管理

* 其他 Mixin 负责具体业务能力

## 架构设计

```
┌─────────────────────────────────────────────────────────┐
│                    Layer 1: 抽象基类                      │
│                                                         │
│   BaseEngine (ABC)                                      │
│   ├── kb_path: Path (知识库根目录)                       │
│   └── 定义抽象接口 (conn, config, ontology)              │
└─────────────────────────────────────────────────────────┘
                            ▲
                            │ 继承
         ┌──────────────────┼──────────────────┐
         │                  │                  │
┌────────┴────────┐ ┌───────┴───────┐ ┌───────┴───────┐
│   ConfigMixin   │ │    DBMixin    │ │ OntologyMixin │
│                 │ │               │ │               │
│ - config_path   │ │ - conn        │ │ - ontology    │
│ - config        │ │ - initialize  │ │ - sync_schema │
│ - load_config   │ │ - close       │ │ - generate_ddl│
└─────────────────┘ └───────────────┘ └───────────────┘
                            ▲
                            │ 继承
         ┌──────────────────┼──────────────────┐
         │                  │                  │
┌────────┴────────┐ ┌───────┴───────┐ ┌───────┴───────┐
│  StorageMixin   │ │  SearchMixin  │ │ EmbeddingMixin│
│                 │ │               │ │               │
│ - load_table    │ │ - search      │ │ - embed       │
│ - dump_table    │ │ - vector_only │ │ - batch_embed │
└─────────────────┘ └───────────────┘ └───────────────┘
                            ▲
                            │ 多继承聚合
                            │
┌───────────────────────────┴───────────────────────────┐
│                    Layer 3: 使用层                      │
│                                                       │
│   Engine(ConfigMixin, DBMixin, OntologyMixin,         │
│           StorageMixin, SearchMixin, EmbeddingMixin)  │
└───────────────────────────────────────────────────────┘
```

## 详细设计

### Layer 1: BaseEngine (抽象基类)

```python
# src/duckkb/core/base.py
from abc import ABC, abstractmethod

class BaseEngine(ABC):
    """核心引擎抽象基类。
    
    只存储基础路径，定义抽象接口。
    具体实现由各 Mixin 提供。
    """
    
    def __init__(self, kb_path: Path | str):
        self._kb_path = Path(kb_path).resolve()
    
    @property
    def kb_path(self) -> Path:
        """知识库根目录。"""
        return self._kb_path
    
    # 抽象属性，由 Mixin 实现
    @property
    @abstractmethod
    def config(self) -> "CoreConfig":
        """配置对象。"""
        ...
    
    @property
    @abstractmethod
    def conn(self) -> duckdb.DuckDBPyConnection:
        """数据库连接。"""
        ...
    
    @property
    @abstractmethod
    def ontology(self) -> Ontology:
        """本体定义。"""
        ...
```

### Layer 2: 基础设施 Mixin

#### ConfigMixin

```python
# src/duckkb/core/mixins/config.py

class ConfigMixin(BaseEngine):
    """配置管理 Mixin。
    
    负责从文件读取和解析配置。
    """
    
    def __init__(self, *args, config_path: Path | str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._config_path = Path(config_path) if config_path else None
        self._config: CoreConfig | None = None
    
    @property
    def config_path(self) -> Path:
        """配置文件路径，默认为 kb_path/config.yaml。"""
        if self._config_path is None:
            return self.kb_path / "config.yaml"
        return self._config_path
    
    @property
    def config(self) -> CoreConfig:
        """配置对象（懒加载）。"""
        if self._config is None:
            self._config = self._load_config()
        return self._config
    
    def _load_config(self) -> CoreConfig:
        """从文件加载配置。"""
        if not self.config_path.exists():
            return CoreConfig.default(self.kb_path)
        # 读取 YAML 并解析...
```

#### DBMixin

```python
# src/duckkb/core/mixins/db.py

class DBMixin(BaseEngine):
    """数据库连接管理 Mixin。
    
    负责 DuckDB 连接的创建、管理和关闭。
    """
    
    def __init__(self, *args, db_path: Path | str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._db_path = Path(db_path) if db_path else None
        self._conn: duckdb.DuckDBPyConnection | None = None
    
    @property
    def db_path(self) -> Path:
        """数据库文件路径。"""
        if self._db_path is None:
            # 依赖 ConfigMixin 提供的 config
            return self.config.storage.data_dir / "knowledge.db"
        return self._db_path
    
    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        """数据库连接（懒加载）。"""
        if self._conn is None:
            self._conn = self._create_connection()
        return self._conn
    
    def _create_connection(self) -> duckdb.DuckDBPyConnection:
        """创建数据库连接。"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        return duckdb.connect(str(self.db_path))
    
    def close(self) -> None:
        """关闭连接。"""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
```

#### OntologyMixin

```python
# src/duckkb/core/mixins/ontology.py

class OntologyMixin(BaseEngine):
    """本体管理 Mixin。
    
    负责本体定义的加载和 DDL 生成。
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._ontology: Ontology | None = None
    
    @property
    def ontology(self) -> Ontology:
        """本体定义（懒加载，从 config 读取）。"""
        if self._ontology is None:
            self._ontology = self.config.ontology
        return self._ontology
    
    def sync_schema(self) -> None:
        """同步表结构到数据库。"""
        for node_name, node_type in self.ontology.nodes.items():
            ddl = self._generate_node_ddl(node_type)
            self.conn.execute(ddl)
        for edge_name, edge_type in self.ontology.edges.items():
            ddl = self._generate_edge_ddl(edge_name, edge_type)
            self.conn.execute(ddl)
    
    def _generate_node_ddl(self, node_type: NodeType) -> str:
        """生成节点表 DDL。"""
        ...
    
    def _generate_edge_ddl(self, edge_name: str, edge_type: EdgeType) -> str:
        """生成边表 DDL。"""
        ...
```

### Layer 2: 业务能力 Mixin

#### StorageMixin

```python
# src/duckkb/core/mixins/storage.py

class StorageMixin(BaseEngine):
    """存储能力 Mixin。
    
    提供 SQL 驱动的数据加载和导出。
    依赖 conn (DBMixin) 和 ontology (OntologyMixin)。
    """
    
    async def load_table(
        self, 
        table_name: str, 
        path_pattern: str,
        identity_fields: list[str]
    ) -> int:
        """使用 read_json_auto 加载数据。"""
        # 使用 self.conn 执行 SQL
        ...
    
    async def dump_table(
        self,
        table_name: str,
        output_dir: Path,
        partition_by_date: bool = True
    ) -> int:
        """使用 COPY ... PARTITION_BY 导出数据。"""
        ...
    
    async def load_node(self, node_type: str) -> int:
        """加载节点数据。"""
        node_def = self.ontology.nodes.get(node_type)
        path = self.config.storage.data_dir / "nodes" / node_def.table / "**/*.jsonl"
        return await self.load_table(node_def.table, str(path), node_def.identity)
    
    async def dump_node(self, node_type: str) -> int:
        """导出节点数据。"""
        ...
```

#### SearchMixin

```python
# src/duckkb/core/mixins/search.py

class SearchMixin(BaseEngine):
    """检索能力 Mixin。"""
    
    def __init__(self, *args, rrf_k: int = 60, **kwargs):
        super().__init__(*args, **kwargs)
        self._rrf_k = rrf_k
    
    async def search(
        self,
        node_type: str,
        vector_column: str,
        query_vector: list[float],
        fts_columns: list[str],
        query_text: str,
        limit: int = 10
    ) -> list[dict]:
        """RRF 混合检索。"""
        ...
```

### Layer 3: Engine (使用层)

```python
# src/duckkb/core/engine.py

class Engine(
    ConfigMixin,
    DBMixin,
    OntologyMixin,
    StorageMixin,
    SearchMixin,
    EmbeddingMixin,
):
    """知识库引擎。
    
    通过多继承聚合所有能力。
    初始化只需传入知识库路径，其他由各 Mixin 自动处理。
    """
    
    def __init__(
        self, 
        kb_path: Path | str,
        *,
        config_path: Path | str | None = None,
        db_path: Path | str | None = None,
        rrf_k: int = 60,
    ):
        # 按顺序调用各 Mixin 的 __init__
        super().__init__(
            kb_path=kb_path,
            config_path=config_path,
            db_path=db_path,
            rrf_k=rrf_k,
        )
    
    def initialize(self) -> "Engine":
        """初始化引擎。"""
        self.sync_schema()
        return self
    
    def close(self) -> None:
        """关闭引擎。"""
        # DBMixin 的 close
        super().close()
    
    def __enter__(self) -> "Engine":
        self.initialize()
        return self
    
    def __exit__(self, *args) -> None:
        self.close()
```

## 使用示例

```python
from duckkb.core import Engine

# 简单使用
with Engine("/path/to/kb") as engine:
    await engine.load_node("document")
    results = await engine.search("document", "embedding", vector, ["content"], "query")

# 自定义配置
engine = Engine(
    "/path/to/kb",
    config_path="/custom/config.yaml",
    db_path="/custom/data.db",
    rrf_k=100,
)
engine.initialize()
```

## 文件结构

```
src/duckkb/core/
├── __init__.py           # 导出 Engine, BaseEngine, Mixins
├── base.py               # BaseEngine 抽象基类
├── engine.py             # Engine 最终实现
├── config/
│   ├── __init__.py
│   └── models.py         # CoreConfig, StorageConfig
├── mixins/
│   ├── __init__.py
│   ├── config.py         # ConfigMixin
│   ├── db.py             # DBMixin
│   ├── ontology.py       # OntologyMixin
│   ├── storage.py        # StorageMixin
│   ├── search.py         # SearchMixin
│   └── embedding.py      # EmbeddingMixin
```

## MRO (方法解析顺序)

```python
Engine.__mro__ = (
    Engine,
    ConfigMixin,      # 先解析配置
    DBMixin,          # 再建立连接 (可访问 config)
    OntologyMixin,    # 再加载本体 (可访问 config)
    StorageMixin,     # 业务能力 (可访问 conn, ontology)
    SearchMixin,      # 业务能力
    EmbeddingMixin,   # 业务能力
    BaseEngine,       # 基类
    ABC,
    object,
)
```

## 迁移步骤

### Phase 1: 创建基础架构

1. 创建 `base.py` - BaseEngine 抽象基类
2. 创建 `mixins/` 目录
3. 创建 `config.py` - ConfigMixin
4. 创建 `db.py` - DBMixin

### Phase 2: 重构现有功能

1. 创建 `ontology.py` - OntologyMixin (从 manager.py 迁移)
2. 创建 `storage.py` - StorageMixin (合并 loader + persister)
3. 创建 `search.py` - SearchMixin (从 rrf.py 迁移)

### Phase 3: 创建使用层

1. 创建 `engine.py` - Engine 多继承类
2. 更新 `__init__.py` 导出

### Phase 4: 清理

1. 删除旧文件 (loader.py, persister.py, rrf.py, runtime.py, manager.py)
2. 更新测试

## 优势

| 方面    | 改进              |
| ----- | --------------- |
| 职责分离  | 每个 Mixin 只做一件事  |
| 初始化简化 | 只需传路径，配置/连接自动处理 |
| 依赖清晰  | MRO 保证了依赖顺序     |
| 可测试性  | 每个 Mixin 可独立测试  |
| 扩展性   | 新能力只需添加新 Mixin  |

