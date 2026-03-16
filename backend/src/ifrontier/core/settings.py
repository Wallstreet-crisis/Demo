from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IF_", extra="ignore")

    app_name: str = "information-frontier"
    environment: str = "dev"

settings = Settings()
