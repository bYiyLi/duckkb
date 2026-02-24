
import jieba

from duckkb.config import settings
from duckkb.logger import logger

_jieba_initialized = False


def _init_jieba():
    global _jieba_initialized
    if not _jieba_initialized:
        user_dict = settings.KB_PATH / "user_dict.txt"
        if user_dict.exists():
            try:
                jieba.load_userdict(str(user_dict))
                logger.debug(f"Loaded user dict from {user_dict}")
            except Exception as e:
                logger.warning(f"Failed to load user dict: {e}")
        _jieba_initialized = True


def segment_text(text: str) -> str:
    """Segment text using Jieba. Returns space-separated string."""
    if not text:
        return ""
    _init_jieba()
    # Use cut_for_search for better recall
    return " ".join(jieba.cut_for_search(text))
