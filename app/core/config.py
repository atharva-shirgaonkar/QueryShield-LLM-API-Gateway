from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    redis_url: str
    openai_api_key: str
    secret_key: str
    free_tier_daily_tokens: int = 1000
    pro_tier_daily_tokens: int = 50000

    class Config:
        env_file = ".env"

settings = Settings()