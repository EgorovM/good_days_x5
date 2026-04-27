from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Публичный HTTPS-URL без завершающего слэша — картинки: {PUBLIC_BASE_URL}/static/images/...
    public_base_url: str | None = Field(default=None, validation_alias="PUBLIC_BASE_URL")
    redis_url: str | None = Field(default=None, validation_alias="REDIS_URL")
    session_ttl_seconds: int = Field(default=86_400, validation_alias="SESSION_TTL_SECONDS")
    outbox_max_attempts: int = Field(default=4, validation_alias="OUTBOX_MAX_ATTEMPTS")
    worker_concurrency: int = Field(default=24, validation_alias="WORKER_CONCURRENCY")
    dry_run_delivery: bool = Field(default=False, validation_alias="DRY_RUN_DELIVERY")

    telegram_bot_token: str | None = Field(default=None, validation_alias="TELEGRAM_BOT_TOKEN")
    telegram_webhook_secret: str | None = Field(default=None, validation_alias="TELEGRAM_WEBHOOK_SECRET")

    @field_validator("telegram_webhook_secret", mode="before")
    @classmethod
    def _empty_webhook_secret_is_none(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s if s else None
        return v

    vk_api_token: str | None = Field(default=None, validation_alias="VK_API_TOKEN")
    vk_group_id: int | None = Field(default=None, validation_alias="VK_GROUP_ID")
    vk_callback_confirmation: str | None = Field(default=None, validation_alias="VK_CALLBACK_CONFIRMATION")
    vk_secret: str | None = Field(default=None, validation_alias="VK_SECRET")

    @field_validator("redis_url", "vk_api_token", "vk_callback_confirmation", "vk_secret", mode="before")
    @classmethod
    def _strip_optional_vk_strings(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s if s else None
        return v

    @property
    def has_telegram(self) -> bool:
        return bool(self.telegram_bot_token)

    @property
    def has_vk(self) -> bool:
        return bool(self.vk_api_token and self.vk_group_id and self.vk_callback_confirmation)


def get_settings() -> Settings:
    return Settings()
