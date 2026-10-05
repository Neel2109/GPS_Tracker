import os
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    api_url: str = "http://localhost:8000"
    ws_url: str = "ws://localhost:8000"
    cors_origins: str = "http://localhost:5173,http://localhost:8000"
    database_url: str = "sqlite:///./trackguard.db"
    jwt_secret: str = Field(
        default="supersecretkey",
        validation_alias=AliasChoices("JWT_SECRET", "SECRET_KEY"),
    )
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    local_pin: str = ""
    local_user_email: str = "owner@trackguard.local"
    local_user_name: str = "TrackGuard Owner"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
