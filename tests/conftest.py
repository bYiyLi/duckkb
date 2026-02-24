import pytest
from duckkb.config import settings

@pytest.fixture
def mock_kb_path(tmp_path):
    settings.KB_PATH = tmp_path
    return tmp_path
