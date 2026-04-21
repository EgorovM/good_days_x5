from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Публичный HTTPS-URL без завершающего слэша — картинки: {PUBLIC_BASE_URL}/static/images/...
    public_base_url: str | None = Field(default=None, validation_alias="PUBLIC_BASE_URL")

    telegram_bot_token: str | None = Field(default=None, validation_alias="TELEGRAM_BOT_TOKEN")
    telegram_webhook_secret: str | None = Field(default=None, validation_alias="TELEGRAM_WEBHOOK_SECRET")

    vk_api_token: str | None = Field(default=None, validation_alias="VK_API_TOKEN")
    vk_group_id: int | None = Field(default=None, validation_alias="VK_GROUP_ID")
    vk_callback_confirmation: str | None = Field(default=None, validation_alias="VK_CALLBACK_CONFIRMATION")
    vk_secret: str | None = Field(default=None, validation_alias="VK_SECRET")

    @property
    def has_telegram(self) -> bool:
        return bool(self.telegram_bot_token)

    @property
    def has_vk(self) -> bool:
        return bool(self.vk_api_token and self.vk_group_id and self.vk_callback_confirmation)


def get_settings() -> Settings:
    return Settings()
