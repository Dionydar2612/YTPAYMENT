from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_ENV: str = "development"
    SECRET_KEY: str = "insecure-dev-secret-change-me"
    SESSION_COOKIE_NAME: str = "session_token"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    DATABASE_URL: str = "postgresql://expense_user:expense_pass@db:5432/expense_db"

    DEFAULT_ADMIN_USERNAME: str = "dada"
    DEFAULT_ADMIN_PASSWORD: str = "123456"

    STORAGE_TYPE: str = "local"
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_MB: int = 5

    CURRENCY_DECIMALS: int = 2

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
