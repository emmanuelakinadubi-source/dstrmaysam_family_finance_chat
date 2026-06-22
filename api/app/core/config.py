from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Event Intelligence Platform"
    debug: bool = True
    secret_key: str = "change-me-in-production"

    # Database
    database_url: str = "postgresql://postgres:postgres@db:5432/family_finance"

    # Azure OpenAI (our RAG pipeline)
    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_api_version: str = "2024-12-01-preview"
    azure_openai_deployment: str = "gpt-4.1-mini"
    azure_openai_embedding_deployment: str = "text-embedding-3-small"

    # ChromaDB — local persistent storage
    chroma_persist_dir: str = "/app/chroma_db"
    canvas_api_url: str = "https://www.canvas-events.co.uk/api/venues"

    # Observability
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    mlflow_tracking_uri: str = ""

    # Scheduler
    vendor_crawl_hour: int = 6
    vendor_crawl_minute: int = 0

    # File uploads
    upload_dir: str = "/app/data/uploads"
    max_file_size_mb: int = 50

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
