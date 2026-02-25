import pytest

from duckkb.config import AppContext


@pytest.fixture
def mock_kb_path(tmp_path):
    try:
        AppContext.init(tmp_path)
        yield tmp_path
    finally:
        AppContext.reset()
