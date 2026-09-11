"""Settings loaded once from the environment / etl/.env. DATA_PIPELINE.md §ETL pipeline design."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url_etl: str
    niti_source_dir: str = "/home/subhan/mentor_portal_db/UP Excise Data Collection"


settings = Settings()  # type: ignore[call-arg]  # pydantic-settings fills required fields from env
