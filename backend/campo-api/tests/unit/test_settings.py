import pytest

from aquanqa_campo_api.core.settings import Settings


@pytest.mark.parametrize(
    ("minimum", "maximum", "expected"),
    [(None, None, (3, 10)), ("1", "8", (1, 8)), (None, "1", (1, 1))],
)
def test_warm_pool_defaults_respect_environment_limits(monkeypatch, minimum, maximum, expected):
    monkeypatch.setattr("aquanqa_campo_api.core.settings.load_dotenv", lambda: None)
    monkeypatch.setenv("AQUANQA_API_DATABASE_URL", "postgresql://localhost/test_settings")
    monkeypatch.setenv("AQUANQA_API_DATABASE", "test_settings")
    monkeypatch.setenv("AQUANQA_API_ENVIRONMENT", "test")
    for name, value in (
        ("AQUANQA_API_DATABASE_POOL_MIN_SIZE", minimum),
        ("AQUANQA_API_DATABASE_POOL_MAX_SIZE", maximum),
    ):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)

    settings = Settings.from_env()

    assert (settings.database_pool_min_size, settings.database_pool_max_size) == expected
