from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str
    redis_url: str
    openai_api_key: str
    secret_key: str
    free_tier_daily_tokens: int = Field(
        default=1000,
        validation_alias=AliasChoices("FREE_TOKEN_LIMIT", "FREE_TIER_DAILY_TOKENS"),
    )
    pro_tier_daily_tokens: int = Field(
        default=50000,
        validation_alias=AliasChoices("PRO_TOKEN_LIMIT", "PRO_TIER_DAILY_TOKENS"),
    )

settings = Settings()
