"""Settings loaded once from the environment / etl/.env. DATA_PIPELINE.md §ETL pipeline design."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url_etl: str
    niti_source_dir: str = "/home/subhan/mentor_portal_db/UP Excise Data Collection"

    # pdf-markdown-pipeline sync (DATA_PIPELINE.md §pdf-markdown-pipeline sync).
    # MariaDB pdf_markdown_pipeline_local via the excise_mcp_kb_ro read-only
    # user (OPERATOR_SETUP.md §Data bank), not the app's own DB credentials.
    kb_ro_mysql_host: str = "127.0.0.1"
    kb_ro_mysql_port: int = 3306
    kb_ro_mysql_user: str = "excise_mcp_kb_ro"
    kb_ro_mysql_password: str = ""
    kb_ro_mysql_database: str = "pdf_markdown_pipeline_local"

    pdf_pipeline_root: str = "/home/subhan/Sites/pdf-markdown-pipeline/storage/app/public"
    pdf_pipeline_base_url: str = "https://docsrepo.exciseup.in"
    # This project is the UP Excise tool; pdf-markdown-pipeline hosts several
    # departments (Sugarcane included) on the same box, so the sync is scoped
    # to this department's slug rather than pulling every department's docs.
    pdf_pipeline_department_slug: str = "excise"


settings = Settings()  # type: ignore[call-arg]  # pydantic-settings fills required fields from env
