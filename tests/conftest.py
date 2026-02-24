import pytest

from duckkb.config import AppContext
from duckkb.engine.core.manager import KnowledgeBaseManager
import duckkb.mcp.server as server_module


@pytest.fixture
def mock_kb_path(tmp_path):
    try:
        AppContext.init(tmp_path)
        
        # Initialize Manager and inject into server module
        manager = KnowledgeBaseManager(tmp_path)
        server_module.manager = manager
        
        yield tmp_path
    finally:
        server_module.manager = None
        AppContext.reset()
