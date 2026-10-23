from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str = Field(min_length=10)
    telegram_proxy_url: str | None = None
    claudehub_api_key: str = Field(min_length=8)
    claudehub_base_url: str = "https://api.claudehub.fun"
    claudehub_model: str = "claude-haiku-5-5"
    database_url: str = "sqlite+aiosqlite:///./sushef.db"
    max_output_tokens: int = Field(default=2600, ge=256, le=8192)
    daily_ai_limit: int = Field(default=25, ge=1, le=1000)
    max_input_chars: int = Field(default=3500, ge=200, le=12000)
    telegram_rich_recipe_cards: bool = True  # Bot API 10.3; HTML fallback on unsupported server
    telegram_draft_preview: bool = True  # Bot API 9.5; non-streaming temporary preview
    telegram_seen_reaction: bool = True  # мгновенная реакция 👀 на сообщение: «Сушеф услышал»
    telegram_stream_answers: bool = True  # Bot API 10.3 sendRichMessageDraft: ответ по мере генерации
    vision_enabled: bool = False  # Включать лишь после проверки vision у ClaudeHub
    max_photo_bytes: int = Field(default=4000000, ge=100000, le=8000000)
    # Служба поддержки: числовые Telegram ID через запятую. Username — запасной
    # способ только при пустом списке ID: первый написавший боту владелец
    # этого username закрепляется в БД.
    support_admin_ids: str = "437862772"
    support_admin_username: str = "grunvald"
    support_daily_limit: int = Field(default=20, ge=1, le=200)
    # Оплата доступа к ИИ в Telegram Stars (валюта XTR, без provider_token).
    payments_enabled: bool = True
    stars_price: int = Field(default=100, ge=1, le=10000)
    subscription_days: int = Field(default=30, ge=1, le=366)
    free_trial_requests: int = Field(default=10, ge=0, le=1000)
    payment_exempt_ids: str = "437862772,719076753"

    @property
    def support_admin_id_set(self) -> frozenset[int]:
        return parse_ids(self.support_admin_ids)

    @property
    def payment_exempt_id_set(self) -> frozenset[int]:
        return parse_ids(self.payment_exempt_ids)


def parse_ids(raw: str) -> frozenset[int]:
    """Comma/space separated Telegram IDs; invalid fragments are ignored."""
    return frozenset(int(part) for part in raw.replace(",", " ").split()
                     if part.isdecimal())


def load_settings() -> Settings:
    return Settings()
