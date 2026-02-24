from duckkb.config import settings


def test_default_config():
    assert settings.LOG_LEVEL == "INFO"
