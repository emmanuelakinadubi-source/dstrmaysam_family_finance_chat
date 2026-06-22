from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Family Finance Chat App"
    debug: bool = True
    database_url: str = "postgresql://postgres:postgres@db:5432/family_finance"

    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_api_version: str = "2024-12-01-preview"
    azure_openai_deployment: str = "gpt-4.1-mini"
    azure_openai_embedding_deployment: str = "text-embedding-3-small"

    chroma_persist_dir: str = "/app/chroma_db"
    canvas_api_url: str = "https://www.canvas-events.co.uk/api/venues"

    class Config:
        env_file = ".env"


settings = Settings()
