from pydantic import BaseModel
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Family Finance Chat App"
    debug: bool = True
    database_url: str = "postgresql://postgres:postgres@db:5432/family_finance"

    class Config:
        env_file = ".env"


settings = Settings()
