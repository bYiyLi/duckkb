"""知识库缓存管理模块。

提供向量嵌入缓存的清理功能，防止缓存表无限增长。
"""

import asyncio

from duckkb.constants import CACHE_EXPIRE_DAYS
from duckkb.database.connection import get_db
from duckkb.logger import logger


async def clean_cache():
    """清理过期的向量缓存条目。

    删除超过 CACHE_EXPIRE_DAYS 天未使用的缓存记录，
    防止缓存表无限增长。
    """
    logger.info("Running cache GC...")
    try:
        await asyncio.to_thread(_execute_gc)
    except Exception as e:
        logger.error(f"Cache GC failed: {e}")


def _execute_gc():
    """执行缓存垃圾回收的实际数据库操作。"""
    with get_db(read_only=False) as conn:
        conn.execute(
            f"DELETE FROM _sys_cache WHERE last_used < current_timestamp - INTERVAL {CACHE_EXPIRE_DAYS} DAY"
        )
