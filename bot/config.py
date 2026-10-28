import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    LASTFM_API_KEY: str = os.getenv("LASTFM_API_KEY", "")
    LASTFM_SHARED_SECRET: str = os.getenv("LASTFM_SHARED_SECRET", "")
    DB_PATH: str = os.getenv("DB_PATH", "bot.db")
    CANVAS_MODEL_PATH: str = os.getenv("CANVAS_MODEL_PATH", ".cache/canvas_models/yamnet.tflite")
    CANVAS_FFMPEG: str = os.getenv("CANVAS_FFMPEG", "ffmpeg")
    CANVAS_TEMP_DIR: str | None = os.getenv("CANVAS_TEMP_DIR") or None
    LASTFM_API_URL: str = os.getenv("LASTFM_API_URL", "https://ws.audioscrobbler.com/2.0/")
    USER_AGENT: str = os.getenv(
        "USER_AGENT",
        "NowPlayingTelegramBot/1.0 (aiohttp; +https://github.com/showwhatimlistening)"
    )
    # Timezone offset (hours from UTC) used for day/hour bucketing in /stats
    TZ_OFFSET_HOURS: float = float(os.getenv("TZ_OFFSET_HOURS", "3"))
    LASTFM_RATE_LIMIT_SEMAPHORE: int = 4
    LASTFM_REQUEST_TIMEOUT: float = 6.0
    COVER_DOWNLOAD_TIMEOUT: float = 6.0


config = Config()


def validate_config() -> None:
    errors = []
    if not config.BOT_TOKEN or config.BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        errors.append("BOT_TOKEN is not configured in .env")
    if not config.LASTFM_API_KEY or config.LASTFM_API_KEY == "YOUR_LASTFM_API_KEY":
        errors.append("LASTFM_API_KEY is not configured in .env")

    if errors:
        raise ValueError(
            "Configuration error:\n" + "\n".join(f" - {err}" for err in errors)
        )
