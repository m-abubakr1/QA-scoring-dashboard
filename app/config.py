from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    api_key: str = ""  # if set, requests must send it in the X-API-Key header
    model: str = "gpt-4o-mini"
    timeout_seconds: float = 60.0

    # a local SQLite file by default, Postgres in docker-compose
    database_url: str = "sqlite:///./qa.db"

    # live scoring: score again after this many new lines
    score_every_lines: int = 6
    # alert when the live score falls this many points from the last one
    score_drop_alert: float = 15
    low_score_alert: float = 50

    # rate limiting, per client IP
    rate_limit_per_minute: float = 30
    rate_limit_burst: int = 10
    ws_max_connections_per_ip: int = 5

    # websockets
    ws_ping_seconds: float = 20
    ws_idle_timeout_seconds: float = 60


settings = Settings()
