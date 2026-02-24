"""知识库引擎模块。"""

from duckkb.engine.cache import clean_cache
from duckkb.engine.crud import add_documents
from duckkb.engine.deleter import delete_documents
from duckkb.engine.searcher import query_raw_sql, smart_search
from duckkb.engine.sync import sync_knowledge_base

__all__ = [
    "add_documents",
    "clean_cache",
    "delete_documents",
    "query_raw_sql",
    "smart_search",
    "sync_knowledge_base",
]
