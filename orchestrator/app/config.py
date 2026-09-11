"""Settings loaded once from the environment / orchestrator/.env. MCP_ENGINES.md §Config."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    orch_bearer_token: str
    database_url_readonly: str

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_sql_model: str = "qwen2.5-coder:7b-instruct-q4_K_M"
    ollama_chat_model: str = "llama3.1:8b-instruct-q4_K_M"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_allowed_models: str = "qwen2.5-coder:7b-instruct-q4_K_M,llama3.1:8b-instruct-q4_K_M"

    kb_embeddings_enabled: bool = False
    kb_embed_dim: int = 768
    kb_retrieve_k: int = 6

    chat_max_tool_calls: int = 4
    chat_context_turns: int = 8

    sandbox_user: str = "excise-sandbox"
    sandbox_scratch_root: str = "/var/tmp/excise-charts"
    sandbox_wallclock_seconds: int = 15
    sandbox_memory_mb: int = 1024
    # False until `systemd-run --user --uid=excise-sandbox ...` actually works
    # from this account — `loginctl enable-linger excise-sandbox` alone isn't
    # enough (confirmed live), the sudoers fallback in SECURITY.md §2 /
    # OPERATOR_SETUP.md §Sandbox execution route is the untried real path.
    # Until then bwrap.py runs the sandboxed script as the orchestrator's own
    # user instead of excise-sandbox — bwrap's own namespace/network/
    # filesystem confinement still fully applies, this only skips the extra
    # host-uid-separation layer.
    sandbox_uid_switch_enabled: bool = False

    query_row_limit_default: int = 5000
    statement_timeout: str = "10s"

    @property
    def allowed_models(self) -> list[str]:
        return [m.strip() for m in self.ollama_allowed_models.split(",") if m.strip()]

    def model_role(self, key: str) -> str:
        """Registry role for a model key, for /health and prompt selection."""
        if key == self.ollama_sql_model:
            return "sql"
        if key == self.ollama_chat_model:
            return "chat"
        if key == self.ollama_embed_model:
            return "embed"
        return "chat"  # an added registry entry (e.g. gemma2) defaults to the chat role


settings = Settings()  # type: ignore[call-arg]  # pydantic-settings fills required fields from env
