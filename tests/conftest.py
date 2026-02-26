"""测试配置和共享 fixtures。"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from duckkb.config import AppContext


@pytest.fixture
def mock_kb_path(tmp_path):
    """创建临时知识库目录。"""
    try:
        AppContext.init(tmp_path)
        yield tmp_path
    finally:
        AppContext.reset()


@pytest.fixture
def test_kb_path(tmp_path):
    """创建完整的测试知识库目录结构。"""
    kb_dir = tmp_path / "test_kb"
    kb_dir.mkdir(parents=True)

    config_content = """
embedding:
  model: text-embedding-3-small
  dim: 1536

log_level: INFO

global:
  chunk_size: 800
  embedding_model: text-embedding-3-small
  tokenizer: jieba

ontology:
  nodes:
    Character:
      table: characters
      identity: [name]
      schema:
        type: object
        properties:
          name:
            type: string
          age:
            type: integer
          email:
            type: string
          bio:
            type: string
          status:
            type: string
          tags:
            type: array
            items:
              type: string
          metadata:
            type: object
        required: [name]
      search:
        full_text: [name, bio]
        vectors: [bio]

    Document:
      table: documents
      identity: [doc_id]
      schema:
        type: object
        properties:
          doc_id:
            type: string
          title:
            type: string
          content:
            type: string
          category:
            type: string
          word_count:
            type: integer
          created_at:
            type: string
        required: [doc_id, title]
      search:
        full_text: [title, content]
        vectors: [content]

    Product:
      table: products
      identity: [sku]
      schema:
        type: object
        properties:
          sku:
            type: string
          name:
            type: string
          description:
            type: string
          price:
            type: number
          stock:
            type: integer
          active:
            type: boolean
          rating:
            type: number
          categories:
            type: array
            items:
              type: string
        required: [sku, name]
      search:
        full_text: [name, description]
        vectors: [description]

  edges:
    knows:
      from: Character
      to: Character
      cardinality: N:N
      schema:
        type: object
        properties:
          since:
            type: string
          closeness:
            type: number

    authored:
      from: Character
      to: Document
      cardinality: N:1
      schema:
        type: object
        properties:
          role:
            type: string

    mentions:
      from: Document
      to: Product
      cardinality: N:N
      schema:
        type: object
        properties:
          context:
            type: string
          relevance:
            type: number
"""
    (kb_dir / "config.yaml").write_text(config_content, encoding="utf-8")

    data_dir = kb_dir / "data"
    data_dir.mkdir(parents=True)

    nodes_dir = data_dir / "nodes"
    nodes_dir.mkdir(parents=True)
    (nodes_dir / "characters").mkdir(parents=True)
    (nodes_dir / "documents").mkdir(parents=True)
    (nodes_dir / "products").mkdir(parents=True)

    edges_dir = data_dir / "edges"
    edges_dir.mkdir(parents=True)
    (edges_dir / "knows").mkdir(parents=True)
    (edges_dir / "authored").mkdir(parents=True)
    (edges_dir / "mentions").mkdir(parents=True)

    cache_dir = data_dir / "cache"
    cache_dir.mkdir(parents=True)

    try:
        AppContext.init(kb_dir)
    except Exception:
        pass

    return kb_dir


@pytest.fixture
def engine(test_kb_path):
    """创建同步引擎实例。"""
    from duckkb.core.engine import Engine

    eng = Engine(test_kb_path)
    eng.initialize()
    yield eng
    eng.close()


@pytest.fixture
async def async_engine(test_kb_path):
    """创建异步引擎实例。"""
    from duckkb.core.engine import Engine

    eng = Engine(test_kb_path)
    await eng.async_initialize()
    yield eng
    eng.close()


@pytest.fixture
def mock_embedding():
    """Mock 向量嵌入 API 批量调用。"""
    with patch("duckkb.core.mixins.embedding.EmbeddingMixin.embed") as mock:
        mock.return_value = [[0.1] * 1536]
        yield mock


@pytest.fixture
def mock_embedding_single():
    """Mock 单个文本向量嵌入。"""
    with patch("duckkb.core.mixins.embedding.EmbeddingMixin.embed_single") as mock:
        async_mock = AsyncMock(return_value=[0.1] * 1536)
        mock.side_effect = async_mock
        yield mock


@pytest.fixture
def sample_characters():
    """示例角色数据。"""
    return [
        {
            "type": "Character",
            "name": "张明",
            "age": 28,
            "email": "zhangming@example.com",
            "bio": "张明是一名资深软件工程师，专注于向量数据库和知识图谱技术。",
            "status": "active",
            "tags": ["工程师", "向量数据库"],
            "metadata": {"department": "研发部"},
        },
        {
            "type": "Character",
            "name": "李婷",
            "age": 32,
            "email": "liting@example.com",
            "bio": "李婷是产品经理，负责知识库产品规划。",
            "status": "active",
            "tags": ["产品经理"],
            "metadata": {"department": "产品部"},
        },
        {
            "type": "Character",
            "name": "王强",
            "age": 35,
            "email": "wangqiang@example.com",
            "bio": "王强是架构师，负责系统架构设计。",
            "status": "active",
            "tags": ["架构师"],
            "metadata": {"department": "架构组"},
        },
    ]


@pytest.fixture
def sample_documents():
    """示例文档数据。"""
    return [
        {
            "type": "Document",
            "doc_id": "DOC-001",
            "title": "技术架构设计文档",
            "content": "DuckKB 是一个基于 DuckDB 构建的知识库引擎，专为 AI Agent 提供持久化记忆层。",
            "category": "技术文档",
            "word_count": 100,
            "created_at": "2024-01-20T10:00:00Z",
        },
        {
            "type": "Document",
            "doc_id": "DOC-002",
            "title": "快速入门指南",
            "content": "本指南帮助您快速上手 DuckKB，包括安装、配置和基本使用。",
            "category": "入门指南",
            "word_count": 50,
            "created_at": "2024-01-21T14:00:00Z",
        },
    ]


@pytest.fixture
def sample_products():
    """示例产品数据。"""
    return [
        {
            "type": "Product",
            "sku": "SKU-001",
            "name": "DuckKB 企业版",
            "description": "面向企业用户的知识库解决方案。",
            "price": 99999.00,
            "stock": 100,
            "active": True,
            "rating": 4.8,
            "categories": ["企业软件", "知识库"],
        },
        {
            "type": "Product",
            "sku": "SKU-002",
            "name": "DuckKB 开发者版",
            "description": "专为个人开发者设计的知识库工具。",
            "price": 0.0,
            "stock": 9999,
            "active": True,
            "rating": 4.5,
            "categories": ["开发工具"],
        },
    ]


@pytest.fixture
def sample_edges():
    """示例边数据。"""
    return [
        {
            "type": "knows",
            "source": {"name": "张明"},
            "target": {"name": "李婷"},
            "since": "2023-06-01",
            "closeness": 0.9,
        },
        {
            "type": "authored",
            "source": {"name": "张明"},
            "target": {"doc_id": "DOC-001"},
            "role": "author",
        },
        {
            "type": "mentions",
            "source": {"doc_id": "DOC-001"},
            "target": {"sku": "SKU-001"},
            "context": "技术文档中提及企业版",
            "relevance": 0.95,
        },
    ]


@pytest.fixture
def sample_yaml_content(sample_characters, sample_documents, sample_products, sample_edges):
    """示例 YAML 知识包内容。"""
    data = sample_characters + sample_documents + sample_products + sample_edges
    return yaml.dump(data, allow_unicode=True, default_flow_style=False)


@pytest.fixture
def sample_yaml_file(tmp_path, sample_yaml_content):
    """创建示例 YAML 文件。"""
    yaml_file = tmp_path / "test_bundle.yaml"
    yaml_file.write_text(sample_yaml_content, encoding="utf-8")
    return yaml_file


@pytest.fixture
def long_text():
    """长文本用于测试切片功能。"""
    return """
DuckKB 是一个基于 DuckDB 构建的知识库引擎，专为 AI Agent 提供持久化记忆层。
本文档详细介绍了 DuckKB 的技术架构设计和核心实现原理。

一、系统概述

DuckKB 采用「一库一服」的设计理念，每个实例独占一个目录，所有知识以 Git 托管的 JSONL 文本形式存在。
这种设计确保了数据的可追溯性和确定性还原。

核心特性包括：
- 混合检索：结合向量语义检索和全文关键词检索，使用 RRF 算法融合结果
- 向量缓存：基于内容哈希缓存 embedding，大幅降低 API 调用成本
- 本体驱动：通过 config.yaml 定义知识结构，DDL 自动生成
- 原子导入：事务包装 + 影子导出，确保数据一致性
- 安全查询：SQL 黑名单、自动 LIMIT、结果集大小限制

二、架构设计

DuckKB 引擎采用 Mixin 组合模式，按依赖顺序组合多个能力模块：
1. ConfigMixin - 配置加载
2. DBMixin - 数据库连接
3. OntologyMixin - 本体管理
4. StorageMixin - 数据存储
5. ChunkingMixin - 文本切片
6. TokenizerMixin - 分词处理
7. EmbeddingMixin - 向量嵌入
8. IndexMixin - 搜索索引
9. SearchMixin - 混合检索
10. ImportMixin - 知识导入

三、数据模型

每个节点类型对应一个数据库表，表结构由本体定义自动生成：
- __id：确定性 ID（SHA256 哈希）
- __created_at：创建时间
- __updated_at：更新时间
- __date：分区日期字段（派生列）
- 业务字段：根据 Schema 定义

四、核心流程

数据导入流程：
1. 读取 YAML 知识包
2. Schema 校验
3. 开启事务
4. 导入节点和边
5. 验证边引用完整性
6. 构建索引
7. 提交事务
8. 异步计算向量嵌入
9. 影子导出 + 原子替换

搜索流程：
1. 获取查询向量
2. 执行向量检索
3. 执行全文检索
4. RRF 融合排序
5. 返回结果
""".strip()


@pytest.fixture
def default_kb_path():
    """获取默认测试知识库路径。"""
    return Path(__file__).parent.parent / ".duckkb" / "default"
