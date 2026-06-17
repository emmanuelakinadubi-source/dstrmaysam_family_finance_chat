from pydantic import BaseModel
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Family Finance Chat App"
    debug: bool = True
    database_url: str = "postgresql://postgres:adubi1214@db:5432/family_expense"

    class Config:
        env_file = ".env"


settings = Settings()
