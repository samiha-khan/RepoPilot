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


def test_settings_default_cors_origins_include_local_and_production_frontends() -> None:
    settings = Settings()

    assert settings.allowed_cors_origins == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://repo-pilot-okaku0jzj-skportfolio.vercel.app",
        "https://repo-pilot-sable.vercel.app",
    ]
