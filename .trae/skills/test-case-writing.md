# 测试用例编写技能

## 核心原则

1. **真实数据优先**：所有测试用例必须使用真实数据进行测试
2. **Mock 限制**：仅向量/大模型调用可使用 mock，其他任何组件禁止 mock
3. **覆盖率目标**：项目代码覆盖率 80% 以上

## 测试数据规范

### 真实数据要求

- 使用有意义的中文/英文数据
- 数据应反映真实业务场景
- 避免使用 "test", "foo", "bar", "xxx" 等无意义数据
- 测试数据应具有代表性，覆盖各种边界情况

### Mock 规则

| 组件 | 是否允许 Mock | 说明 |
|-----|-------------|------|
| OpenAI Embedding API | ✅ 允许 | 外部付费服务，需要 mock |
| 大模型 API 调用 | ✅ 允许 | 外部付费服务，需要 mock |
| 数据库操作 | ❌ 禁止 | 使用真实的 DuckDB 内存模式 |
| 文件系统操作 | ❌ 禁止 | 使用 pytest 的 tmp_path |
| 分词器 | ❌ 禁止 | 使用真实的 jieba 分词 |
| 配置加载 | ❌ 禁止 | 使用真实的配置文件 |
| 文本切片 | ❌ 禁止 | 使用真实的切片逻辑 |

### Mock 实现示例

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.fixture
def mock_embedding():
    """Mock 向量嵌入 API 调用。"""
    with patch("duckkb.core.mixins.embedding.EmbeddingMixin.embed") as mock:
        mock.return_value = [[0.1] * 1536]
        yield mock

@pytest.fixture
def mock_embedding_single():
    """Mock 单个文本向量嵌入。"""
    with patch("duckkb.core.mixins.embedding.EmbeddingMixin.embed_single") as mock:
        mock.return_value = [0.1] * 1536
        yield mock
```

## 测试场景覆盖

### 功能测试

- **正常流程测试**：验证功能在正常输入下的行为
- **边界条件测试**：验证功能在边界值下的行为
- **异常处理测试**：验证功能在异常输入下的错误处理
- **并发安全测试**：验证功能在并发场景下的正确性

### 数据类型测试

| 数据类型 | 测试场景 |
|---------|---------|
| 字符串 | 空字符串、长字符串、特殊字符、Unicode |
| 整数 | 正数、负数、零、边界值 |
| 浮点数 | 正数、负数、零、精度问题 |
| 布尔 | true、false |
| 数组 | 空数组、单元素、多元素、嵌套数组 |
| 对象 | 空对象、嵌套对象 |
| 日期时间 | 有效格式、无效格式、时区处理 |
| 空值 | None、null、缺失字段 |

### 搜索测试

- **精确匹配**：查询词与内容完全匹配
- **模糊匹配**：查询词与内容部分匹配
- **语义相似**：查询词与内容语义相关但词汇不同
- **混合检索**：验证 RRF 融合算法
- **空查询**：验证空查询的处理
- **特殊字符**：验证特殊字符的转义处理

## 测试文件组织

```
tests/
├── conftest.py          # 共享 fixtures
├── test_config.py       # 配置测试
├── test_ontology.py     # 本体测试
├── test_engine.py       # 引擎测试
├── test_storage.py      # 存储测试
├── test_import.py       # 导入测试
├── test_search.py       # 搜索测试
├── test_chunking.py     # 切片测试
├── test_tokenizer.py    # 分词测试
├── test_embedding.py    # 向量测试
├── test_cli.py          # CLI 测试
└── test_mcp.py          # MCP 测试
```

## Fixtures 设计

### 知识库 Fixtures

```python
@pytest.fixture
def kb_path(tmp_path):
    """创建临时知识库目录。"""
    kb_dir = tmp_path / "test_kb"
    kb_dir.mkdir(parents=True)
    
    config_content = """
embedding:
  model: text-embedding-3-small
  dim: 1536

ontology:
  nodes:
    Character:
      table: characters
      identity: [name]
      schema:
        type: object
        properties:
          name: {type: string}
          bio: {type: string}
      search:
        full_text: [name, bio]
        vectors: [bio]
"""
    (kb_dir / "config.yaml").write_text(config_content)
    return kb_dir

@pytest.fixture
def engine(kb_path):
    """创建引擎实例。"""
    from duckkb.core.engine import Engine
    eng = Engine(kb_path)
    eng.initialize()
    yield eng
    eng.close()

@pytest.fixture
async def async_engine(kb_path):
    """创建异步引擎实例。"""
    from duckkb.core.engine import Engine
    eng = Engine(kb_path)
    await eng.async_initialize()
    yield eng
    eng.close()
```

### 测试数据 Fixtures

```python
@pytest.fixture
def sample_characters():
    """示例角色数据。"""
    return [
        {"type": "Character", "name": "张明", "bio": "软件工程师，专注于向量数据库技术。"},
        {"type": "Character", "name": "李婷", "bio": "产品经理，负责知识库产品规划。"},
    ]

@pytest.fixture
def sample_yaml_content():
    """示例 YAML 知识包内容。"""
    return """
- type: Character
  name: 张明
  bio: 软件工程师，专注于向量数据库技术。
- type: Character
  name: 李婷
  bio: 产品经理，负责知识库产品规划。
"""
```

## 测试命名规范

### 测试函数命名

```python
def test_<功能>_<场景>_<预期结果>():
    """测试描述。"""
    pass

# 示例
def test_import_node_upsert_success():
    """测试节点 upsert 操作成功。"""
    pass

def test_import_node_delete_not_found():
    """测试删除不存在的节点。"""
    pass

def test_search_hybrid_with_alpha():
    """测试混合搜索使用 alpha 参数。"""
    pass
```

### 测试类命名

```python
class Test<模块名>:
    """模块测试类。"""
    
    def test_<功能>_<场景>(self):
        pass

# 示例
class TestEngine:
    """引擎测试类。"""
    
    def test_initialize_success(self):
        pass
    
    def test_close_cleanup(self):
        pass
```

## 断言规范

### 使用明确的断言

```python
# 推荐
assert result["status"] == "success"
assert len(results) == 10
assert "error" in result

# 不推荐
assert result
assert not error
```

### 异常断言

```python
import pytest

def test_invalid_config():
    """测试无效配置抛出异常。"""
    with pytest.raises(ValueError, match="invalid model"):
        EmbeddingConfig(model="invalid-model")

def test_missing_required_field():
    """测试缺失必填字段抛出异常。"""
    with pytest.raises(ValidationError):
        NodeType(table="test", identity=[])
```

## 异步测试规范

```python
import pytest

@pytest.mark.asyncio
async def test_async_search():
    """测试异步搜索。"""
    results = await engine.search("测试查询")
    assert len(results) > 0

@pytest.mark.asyncio
async def test_async_import():
    """测试异步导入。"""
    result = await engine.import_knowledge_bundle(yaml_path)
    assert result["status"] == "success"
```

## 覆盖率检查

### 运行覆盖率测试

```bash
pytest --cov=duckkb --cov-branch --cov-report=term-missing --cov-report=html
```

### 覆盖率目标

- 总体覆盖率：80% 以上
- 核心模块覆盖率：90% 以上
- 边缘模块覆盖率：70% 以上

### 排除项

以下代码可以排除在覆盖率统计之外：

- `__init__.py` 文件
- 类型定义文件
- 日志配置代码
- CLI 入口函数

## 测试最佳实践

### 1. 测试独立性

每个测试应该独立运行，不依赖其他测试的结果：

```python
# 推荐
def test_case_a(kb_path):
    engine = Engine(kb_path)
    engine.initialize()
    # 测试逻辑
    engine.close()

def test_case_b(kb_path):
    engine = Engine(kb_path)
    engine.initialize()
    # 测试逻辑
    engine.close()
```

### 2. 测试可读性

使用 Given-When-Then 模式组织测试：

```python
def test_import_knowledge_bundle():
    # Given: 准备测试数据
    yaml_content = """
- type: Character
  name: 张明
  bio: 软件工程师
"""
    
    # When: 执行测试操作
    result = await engine.import_knowledge_bundle(yaml_path)
    
    # Then: 验证结果
    assert result["status"] == "success"
    assert result["nodes"]["upserted"]["Character"] == 1
```

### 3. 测试数据隔离

使用 pytest 的 tmp_path fixture 创建临时目录：

```python
def test_with_temp_files(tmp_path):
    """使用临时文件进行测试。"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("...")
    # 测试逻辑
```

### 4. 清理资源

使用 yield fixture 确保资源清理：

```python
@pytest.fixture
def engine(kb_path):
    eng = Engine(kb_path)
    eng.initialize()
    yield eng
    eng.close()  # 确保清理
```

## 常见测试模式

### 测试 CRUD 操作

```python
class TestNodeCRUD:
    """节点 CRUD 操作测试。"""
    
    @pytest.mark.asyncio
    async def test_create_node(self, async_engine):
        """测试创建节点。"""
        pass
    
    @pytest.mark.asyncio
    async def test_update_node(self, async_engine):
        """测试更新节点。"""
        pass
    
    @pytest.mark.asyncio
    async def test_delete_node(self, async_engine):
        """测试删除节点。"""
        pass
    
    @pytest.mark.asyncio
    async def test_read_node(self, async_engine):
        """测试读取节点。"""
        pass
```

### 测试搜索功能

```python
class TestSearch:
    """搜索功能测试。"""
    
    @pytest.mark.asyncio
    async def test_vector_search(self, async_engine, mock_embedding_single):
        """测试向量搜索。"""
        pass
    
    @pytest.mark.asyncio
    async def test_fts_search(self, async_engine):
        """测试全文搜索。"""
        pass
    
    @pytest.mark.asyncio
    async def test_hybrid_search(self, async_engine, mock_embedding_single):
        """测试混合搜索。"""
        pass
```

### 测试错误处理

```python
class TestErrorHandling:
    """错误处理测试。"""
    
    def test_invalid_yaml(self, engine):
        """测试无效 YAML 格式。"""
        with pytest.raises(ValueError, match="YAML"):
            # 测试逻辑
            pass
    
    def test_schema_validation_error(self, engine):
        """测试 Schema 校验错误。"""
        with pytest.raises(ValidationError):
            # 测试逻辑
            pass
```
