from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "ragdb"
    db_user: str = "rag"
    db_password: str = "rag"

    embed_model: str = "BAAI/bge-m3"
    embed_dim: int = 1024
    reranker_model: str = "BAAI/bge-reranker-v2-m3"

    ollama_model: str = "gemma4:12b"
    ollama_base_url: str = "http://localhost:11434"

    @property
    def db_dsn(self) -> str:
        return (
            f"host={self.db_host} port={self.db_port} "
            f"dbname={self.db_name} user={self.db_user} password={self.db_password}"
        )


settings = Settings()
