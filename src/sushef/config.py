from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str = Field(min_length=10)
    claudehub_api_key: str = Field(min_length=8)
    claudehub_base_url: str = "https://api.claudehub.fun"
    claudehub_model: str = "claude-opus-4-7"
    database_url: str = "sqlite+aiosqlite:///./sushef.db"
    max_output_tokens: int = Field(default=1300, ge=256, le=4096)
    daily_ai_limit: int = Field(default=25, ge=1, le=1000)
    max_input_chars: int = Field(default=3500, ge=200, le=12000)
    vision_enabled: bool = False  # Включать лишь после проверки vision у ClaudeHub
    max_photo_bytes: int = Field(default=4000000, ge=100000, le=8000000)


def load_settings() -> Settings:
    return Settings()
