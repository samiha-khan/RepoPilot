from app.core.config import Settings


def test_settings_converts_heroku_postgres_database_url() -> None:
    settings = Settings(
        database_url="postgres://user:password@example.com:5432/database",
    )

    assert (
        settings.database_url
        == "postgresql+psycopg://user:password@example.com:5432/database"
    )


def test_settings_keeps_psycopg_database_url_unchanged() -> None:
    database_url = "postgresql+psycopg://user:password@example.com:5432/database"

    settings = Settings(database_url=database_url)

    assert settings.database_url == database_url
