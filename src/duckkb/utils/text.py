"""
文本处理工具模块。

提供中文分词和文本哈希计算功能，用于文本预处理和缓存键生成。
"""

import hashlib

import jieba

from duckkb.config import AppContext
from duckkb.logger import logger


def _init_jieba() -> None:
    """
    初始化 Jieba 分词器。

    检查知识库目录下是否存在用户自定义词典（user_dict.txt），
    如果存在则加载，以增强专业术语的分词效果。

    Note:
        使用 AppContext 的 jieba_initialized 标志确保词典只加载一次，
        避免重复加载带来的性能开销。
    """
    ctx = AppContext.get()
    if ctx.jieba_initialized:
        return

    user_dict = ctx.kb_path / "user_dict.txt"
    if user_dict.exists():
        try:
            jieba.load_userdict(str(user_dict))
            logger.debug(f"Loaded user dict from {user_dict}")
        except Exception as e:
            logger.warning(f"Failed to load user dict: {e}")
    ctx.jieba_initialized = True


def segment_text(text: str) -> str:
    """
    对文本进行中文分词，返回空格分隔的字符串。

    使用 Jieba 的搜索引擎模式分词，该模式会对长词进行更细粒度的切分，
    适合知识库检索场景，能提高召回率。

    Args:
        text: 待分词的文本。

    Returns:
        空格分隔的分词结果字符串。如果输入为空，返回空字符串。

    Example:
        >>> segment_text("知识图谱技术")
        "知识 图谱 技术 知识图谱"
    """
    if not text:
        return ""
    _init_jieba()
    return " ".join(jieba.cut_for_search(text))


def compute_text_hash(text: str) -> str:
    """
    计算文本的 MD5 哈希值，用作嵌入缓存键。

    Args:
        text: 待计算哈希的文本。

    Returns:
        32 位十六进制 MD5 哈希字符串。

    Note:
        使用 MD5 是因为其计算速度快，且对于缓存键场景碰撞风险可接受。
        如需更高安全性，可替换为 SHA256。
    """
    return hashlib.md5(text.encode("utf-8")).hexdigest()
