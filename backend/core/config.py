from datetime import datetime
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "VoxTrace"
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    database_url: str = "postgresql+psycopg://postgres:password@localhost:5432/voxtrace_db"
    database_schema: str = "voxtrace"
    session_secret: str = Field(min_length=32)
    session_cookie_name: str = "voxtrace_session"
    session_cookie_secure: bool = False
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    session_max_age_seconds: int = Field(default=28800, gt=0)
    storage_root: str = "storage/audio"
    max_audio_size_mb: int = 100
    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"
    speechbrain_model_source: str = "speechbrain/spkrec-ecapa-voxceleb"
    speechbrain_model_dir: str = "storage/models/speechbrain/spkrec-ecapa-voxceleb"
    biometric_threshold_cosine: float = Field(default=0.6281865036, ge=-1.0, le=1.0)
    biometric_threshold_effective_at: datetime = datetime(2026, 10, 4, 23, 13, 27)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
