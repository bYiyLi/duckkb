import logging
from rich.logging import RichHandler
from duckkb.config import settings

def setup_logging():
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)]
    )
    
    # Suppress noisy libraries if needed
    # logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger("duckkb")
