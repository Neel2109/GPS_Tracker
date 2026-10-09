import os
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    api_url: str = "http://localhost:8000"
    ws_url: str = "ws://localhost:8000"
    cors_origins: str = "http://localhost:5173,http://localhost:8000"
    database_url: str = "sqlite+aiosqlite:///./trackguard.db"
    jwt_secret: str = Field(
        default="supersecretkey",
        validation_alias=AliasChoices("JWT_SECRET", "SECRET_KEY"),
    )
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    totp_encryption_key: str = ""
    phone_recovery_hmac_key: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    local_pin: str = ""
    local_user_email: str = "owner@trackguard.local"
    local_user_name: str = "TrackGuard Owner"
    local_user_phone: str = ""
    super_admin_phone: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
