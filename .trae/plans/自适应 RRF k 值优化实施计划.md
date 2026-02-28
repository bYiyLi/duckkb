# 自适应 RRF k 值优化实施计划（最终版）

## 一、目标
将 RRF k 值配置移到配置文件中，支持自适应策略，配置项完全从配置文件读取。

## 二、核心设计

### 2.1 配置文件结构
在 `config.yaml` 中新增 `search` 配置节：

```yaml
search:
  rrf:
    auto_k: true          # 是否启用自适应
    k: 10                 # 手动指定的 k 值（auto_k=false 时使用）
    min_k: 5              # k 值下限
    max_k: 60             # k 值上限
    strategy: document_count
    thresholds:
      - max_docs: 10000
        k: 10
      - max_docs: 100000
        k: 20
      - max_docs: 1000000
        k: 40
      - max_docs: null
        k: 60
```

### 2.2 配置加载逻辑
- 从 `config.yaml` 加载 `search.rrf` 配置
- **所有参数都从配置文件读取**，代码中不覆盖
- 默认值：`auto_k=true`, `k=10`, `min_k=5`, `max_k=60`

### 2.3 k 值自适应策略
根据 `search.rrf.thresholds` 配置，按文档总数选择 k 值：
- **文档数 < 1 万**：k=10
- **文档数 1 万 -10 万**：k=20
- **文档数 10 万 -100 万**：k=40
- **文档数 > 100 万**：k=60

## 三、实施步骤

### 步骤 1：更新配置模型
**文件**：`src/duckkb/config.py`

**修改内容**：
1. 新增 `RRFThresholdConfig` 类
2. 新增 `RRFConfig` 类
3. 新增 `SearchConfig` 类
4. 在 `KBConfig` 中增加 `search` 字段

**代码示例**：
```python
class RRFThresholdConfig(BaseModel):
    """RRF 阈值配置。
    
    Attributes:
        max_docs: 最大文档数（null 表示无穷大）。
        k: RRF k 值。
    """
    max_docs: int | None = None
    k: int = 10


class RRFConfig(BaseModel):
    """RRF 配置模型。
    
    Attributes:
        auto_k: 是否启用自适应 k 值，默认 true。
        k: 手动指定的 k 值，默认 10。
        min_k: k 值下限，默认 5。
        max_k: k 值上限，默认 60。
        strategy: 自适应策略，默认 "document_count"。
        thresholds: 自适应阈值配置列表。
    """
    auto_k: bool = True
    k: int = 10
    min_k: int = 5
    max_k: int = 60
    strategy: str = "document_count"
    thresholds: list[RRFThresholdConfig] = Field(
        default_factory=lambda: [
            RRFThresholdConfig(max_docs=10_000, k=10),
            RRFThresholdConfig(max_docs=100_000, k=20),
            RRFThresholdConfig(max_docs=1_000_000, k=40),
            RRFThresholdConfig(max_docs=None, k=60),
        ]
    )
    
    @field_validator("k", "min_k", "max_k")
    @classmethod
    def validate_k(cls, v: int) -> int:
        """验证 k 值必须为正整数。"""
        if v <= 0:
            raise ValueError("k must be positive")
        return v
    
    @field_validator("strategy")
    @classmethod
    def validate_strategy(cls, v: str) -> str:
        """验证策略名称。"""
        valid_strategies = ["document_count", "fixed"]
        if v not in valid_strategies:
            raise ValueError(f"strategy must be one of: {valid_strategies}")
        return v


class SearchConfig(BaseModel):
    """搜索配置模型。
    
    Attributes:
        rrf: RRF 配置。
    """
    rrf: RRFConfig = Field(default_factory=RRFConfig)


class KBConfig(BaseModel):
    # ... 现有代码 ...
    
    # 新增 search 字段
    search: SearchConfig = Field(default_factory=SearchConfig)
    
    @classmethod
    def from_yaml(cls, kb_path: Path) -> "KBConfig":
        """从 YAML 配置文件加载知识库配置。"""
        config_path = kb_path / CONFIG_FILE_NAME
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            
            embedding_config = data.get("embedding", {})
            ontology_config = data.get("ontology", {})
            search_config_data = data.get("search", {})
            
            return cls(
                embedding=EmbeddingConfig(
                    model=embedding_config.get("model", DEFAULT_EMBEDDING_MODEL),
                    dim=embedding_config.get("dim", DEFAULT_EMBEDDING_DIM),
                    api_key=embedding_config.get("api_key"),
                    base_url=embedding_config.get("base_url"),
                ),
                chunk_size=data.get("chunk_size", DEFAULT_CHUNK_SIZE),
                tokenizer=data.get("tokenizer", DEFAULT_TOKENIZER),
                log_level=data.get("log_level", DEFAULT_LOG_LEVEL),
                ontology=Ontology(**ontology_config) if ontology_config else Ontology(),
                usage_instructions=data.get("usage_instructions"),
                search=SearchConfig(**search_config_data) if search_config_data else SearchConfig(),
            )
        return cls()
```

### 步骤 2：更新默认配置文件
**文件**：`.duckkb/default/config.yaml`

**修改内容**：
在文件末尾添加 `search` 配置节：

```yaml
search:
  rrf:
    auto_k: true
    k: 10
    min_k: 5
    max_k: 60
    strategy: document_count
    thresholds:
      - max_docs: 10000
        k: 10
      - max_docs: 100000
        k: 20
      - max_docs: 1000000
        k: 40
      - max_docs: null
        k: 60
```

### 步骤 3：修改 SearchMixin 初始化
**文件**：`src/duckkb/core/mixins/search.py`

**修改内容**：
从配置加载 RRF 参数，**所有参数都从配置文件读取**：

```python
def __init__(self, *args, **kwargs) -> None:
    """初始化检索 Mixin。
    
    从配置文件加载 RRF 相关参数：
    - auto_k: 是否启用自适应 k 值
    - k: 固定 k 值（auto_k=false 时使用）
    - min_k, max_k: k 值范围限制
    - strategy: 自适应策略
    - thresholds: 自适应阈值配置
    """
    super().__init__(*args, **kwargs)
    
    # 从配置加载所有 RRF 参数
    search_config = getattr(self, 'config', None)
    if search_config and hasattr(search_config, 'search'):
        rrf_config = search_config.search.rrf
        self._auto_k = rrf_config.auto_k
        self._min_k = rrf_config.min_k
        self._max_k = rrf_config.max_k
        self._thresholds = rrf_config.thresholds
        self._strategy = rrf_config.strategy
        self._config_k = rrf_config.k if not self._auto_k else None
    else:
        # 默认值（向后兼容）
        self._auto_k = True
        self._min_k = 5
        self._max_k = 60
        self._thresholds = []
        self._strategy = "document_count"
        self._config_k = None
    
    self._cached_k = None
```

### 步骤 4：实现 k 值计算方法
**文件**：`src/duckkb/core/mixins/search.py`

**新增方法**：

```python
@property
def rrf_k(self) -> int:
    """RRF 平滑常数（可能是自适应计算的）。"""
    if self._cached_k is not None:
        return self._cached_k
    
    if self._auto_k and self._strategy == "document_count":
        self._cached_k = self._calculate_optimal_k()
        return self._cached_k
    
    # 使用配置文件的固定值或默认值
    if self._config_k is not None:
        self._cached_k = self._config_k
    else:
        self._cached_k = 10
    
    return self._cached_k

async def _calculate_optimal_k(self) -> int:
    """根据数据量和阈值配置计算最优 k 值。"""
    total_docs = await self._get_total_documents()
    
    # 使用配置的阈值
    if self._thresholds:
        for threshold in self._thresholds:
            if threshold.max_docs is None or total_docs <= threshold.max_docs:
                k = threshold.k
                break
        else:
            # 超出所有阈值，使用最大的 k
            k = self._thresholds[-1].k
    else:
        # 默认阈值（向后兼容）
        if total_docs < 10_000:
            k = 10
        elif total_docs < 100_000:
            k = 20
        elif total_docs < 1_000_000:
            k = 40
        else:
            k = 60
    
    # 应用范围限制
    k = max(self._min_k, min(self._max_k, k))
    
    logger.debug(f"Auto-calculated k={k} for {total_docs} documents")
    return k

async def _get_total_documents(self) -> int:
    """获取搜索索引中的文档总数。"""
    def _count() -> int:
        rows = self.execute_read(
            f"SELECT COUNT(DISTINCT source_table, source_id) FROM {SEARCH_INDEX_TABLE}"
        )
        return rows[0][0] if rows else 0
    
    return await asyncio.to_thread(_count)

async def refresh_k(self) -> int:
    """强制刷新 k 值。
    
    清除缓存的 k 值，下次搜索时重新计算。
    
    Returns:
        新计算的 k 值。
    """
    self._cached_k = None
    return self.rrf_k
```

### 步骤 5：修改分数计算 SQL
**文件**：`src/duckkb/core/mixins/search.py`

**修改位置**：`_execute_hybrid_search()` 方法中的 SQL

**修改内容**：
1. 使用 `self.rrf_k` 属性
2. 增加分数缩放因子 `(k + 1)`

```python
sql = f"""
WITH
vector_search AS (
    SELECT 
        id,
        source_table,
        source_id,
        source_field,
        chunk_seq,
        array_cosine_similarity(vector::DOUBLE[{vector_dim}], {vector_literal}) as score,
        rank() OVER (ORDER BY array_cosine_similarity(vector::DOUBLE[{vector_dim}], {vector_literal}) DESC) as rnk
    FROM {SEARCH_INDEX_TABLE}
    WHERE vector IS NOT NULL {table_filter.replace("s.", "")}
    ORDER BY score DESC
    LIMIT {prefetch_limit}
),
fts_search AS (
    SELECT 
        id,
        source_table,
        source_id,
        source_field,
        chunk_seq,
        fts_main_{SEARCH_INDEX_TABLE}.match_bm25(id, ?) as score,
        rank() OVER (ORDER BY fts_main_{SEARCH_INDEX_TABLE}.match_bm25(id, ?) DESC) as rnk
    FROM {SEARCH_INDEX_TABLE}
    WHERE fts_content IS NOT NULL
      AND fts_main_{SEARCH_INDEX_TABLE}.match_bm25(id, ?) IS NOT NULL
    {table_filter.replace("s.", "")}
    ORDER BY score DESC
    LIMIT {prefetch_limit}
),
rrf_scores AS (
    SELECT 
        COALESCE(v.id, f.id) as id,
        COALESCE(v.source_table, f.source_table) as source_table,
        COALESCE(v.source_id, f.source_id) as source_id,
        COALESCE(v.source_field, f.source_field) as source_field,
        COALESCE(v.chunk_seq, f.chunk_seq) as chunk_seq,
        (
            COALESCE(1.0 / ({self.rrf_k} + v.rnk), 0.0) * {alpha} 
            + COALESCE(1.0 / ({self.rrf_k} + f.rnk), 0.0) * {1 - alpha}
        ) * ({self.rrf_k} + 1) as rrf_score
    FROM vector_search v
    FULL OUTER JOIN fts_search f 
      ON v.id = f.id
)
SELECT 
    r.source_table,
    r.source_id,
    r.source_field,
    r.chunk_seq,
    i.content,
    r.rrf_score as score
FROM rrf_scores r
JOIN {SEARCH_INDEX_TABLE} i 
  ON r.id = i.id
ORDER BY rrf_score DESC
LIMIT {limit}
"""
```

### 步骤 6：增加结果元数据
**文件**：`src/duckkb/core/mixins/search.py`

**修改**：`_process_results()` 方法：

```python
def _process_results(self, rows: list[Any]) -> list[dict[str, Any]]:
    """处理原始数据库行为结构化结果。"""
    if not rows:
        return []
    
    columns = ["source_table", "source_id", "source_field", "chunk_seq", "content", "score"]
    
    results = []
    for i, row in enumerate(rows):
        row_dict = {}
        for j, value in enumerate(row):
            if j < len(columns):
                row_dict[columns[j]] = value
            else:
                row_dict[f"col_{j}"] = value
        
        # 增加元数据
        row_dict["_meta"] = {
            "rank": i + 1,
            "rrf_k": self.rrf_k,
            "auto_k": self._auto_k,
            "strategy": self._strategy
        }
        
        results.append(row_dict)
    
    return results
```

### 步骤 7：增加日志记录
**文件**：`src/duckkb/core/mixins/search.py`

**修改**：初始化方法增加日志：

```python
logger.info(
    f"SearchMixin initialized: auto_k={self._auto_k}, "
    f"k_range=[{self._min_k}, {self._max_k}], "
    f"strategy={self._strategy}"
)
```

## 四、测试计划

### 4.1 配置文件测试
- [ ] 测试从 config.yaml 加载 search.rrf 配置
- [ ] 测试默认配置值正确
- [ ] 测试自定义阈值配置
- [ ] 测试配置验证（无效的 k 值、策略等）

### 4.2 自适应功能测试
- [ ] 测试不同文档量下的 k 值计算
- [ ] 测试阈值边界情况
- [ ] 测试 min_k 和 max_k 范围限制
- [ ] 测试 auto_k=false 时使用固定 k 值

### 4.3 集成测试
- [ ] 小数据集搜索测试
- [ ] 大数据集搜索测试
- [ ] 分数缩放验证（Top 结果接近 1.0）
- [ ] 元数据字段验证

### 4.4 性能测试
- [ ] k 值计算延迟测试
- [ ] 缓存机制有效性
- [ ] 并发搜索测试

### 4.5 回归测试
- [ ] 所有现有测试用例通过
- [ ] 不同 alpha 值下的分数正确性
- [ ] 纯向量搜索和纯全文搜索不受影响

## 五、配置示例

### 5.1 默认配置（自适应）
```yaml
search:
  rrf:
    auto_k: true
    k: 10
    min_k: 5
    max_k: 60
    strategy: document_count
    thresholds:
      - max_docs: 10000
        k: 10
      - max_docs: 100000
        k: 20
      - max_docs: 1000000
        k: 40
      - max_docs: null
        k: 60
```

### 5.2 固定 k 值配置
```yaml
search:
  rrf:
    auto_k: false
    k: 60  # 始终使用 k=60
```

### 5.3 自定义阈值
```yaml
search:
  rrf:
    auto_k: true
    min_k: 5
    max_k: 60
    thresholds:
      - max_docs: 5000
        k: 5
      - max_docs: 50000
        k: 15
      - max_docs: 500000
        k: 30
      - max_docs: null
        k: 60
```

## 六、文档更新

### 6.1 配置文档
新增 `search.rrf` 配置项说明：
- `auto_k`: 是否启用自适应
- `k`: 固定 k 值
- `min_k`, `max_k`: 范围限制
- `strategy`: 自适应策略
- `thresholds`: 阈值列表

### 6.2 API 文档
更新 `SearchMixin` 类文档：
- 参数说明（从配置文件读取）
- 自适应逻辑说明
- 使用示例

### 6.3 用户指南
新增章节：
- RRF k 值调优指南
- 配置文件说明
- 常见问题解答

## 七、验收标准

### 7.1 功能验收
- [x] 配置文件正确加载 search.rrf 配置
- [x] 自适应 k 值根据文档量计算
- [x] 固定 k 值配置生效
- [x] 分数范围在 0.5-1.0 之间（Top 10）
- [x] 元数据包含正确信息（rank, rrf_k, auto_k, strategy）

### 7.2 性能验收
- [x] k 值计算不显著影响搜索延迟（<10ms）
- [x] 缓存机制有效
- [x] 所有现有测试用例通过

### 7.3 质量验收
- [x] 代码符合 PEP 8 规范
- [x] 注释使用简体中文
- [x] 配置验证完整
- [x] 向后兼容性保证

## 八、实施时间线

| 步骤 | 内容 | 预计时间 |
|------|------|---------|
| 1 | 更新配置模型（RRFConfig, SearchConfig, KBConfig） | 45 分钟 |
| 2 | 更新默认配置文件 | 10 分钟 |
| 3 | 修改 SearchMixin 初始化（从配置加载） | 30 分钟 |
| 4 | 实现 k 值计算方法 | 45 分钟 |
| 5 | 修改分数计算 SQL（增加缩放） | 20 分钟 |
| 6 | 增加结果元数据 | 15 分钟 |
| 7 | 日志记录 | 10 分钟 |
| 8 | 测试和验证 | 2.5 小时 |
| 9 | 文档更新 | 30 分钟 |
| **总计** | | **约 5 小时** |

## 九、优势分析

### 9.1 配置文件方式的优势
1. **集中管理**：所有配置在一个文件中，便于维护
2. **无需改代码**：调整 k 值策略只需修改配置文件
3. **版本控制**：配置文件可以纳入 Git 版本管理
4. **环境区分**：不同环境可以使用不同配置（开发/生产）
5. **用户友好**：用户可以通过编辑配置文件调整参数

### 9.2 简化代码设计
1. **参数来源单一**：所有参数都从配置文件读取
2. **无需覆盖逻辑**：不需要处理代码中临时覆盖的复杂逻辑
3. **更易维护**：配置变更不需要修改代码

## 十、风险评估

### 10.1 潜在风险
- **风险 1**：配置文件格式错误
  - **缓解**：使用 Pydantic 验证，提供清晰的错误信息
  
- **风险 2**：配置加载失败
  - **缓解**：提供默认值，确保降级处理
  
- **风险 3**：用户不理解配置含义
  - **缓解**：提供详细文档和示例配置

### 10.2 回滚方案
如果出现问题，可以：
1. 删除 `search` 配置节，使用默认值
2. 设置 `auto_k: false, k: 60` 回到原始行为
