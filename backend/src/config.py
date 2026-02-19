from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Application
    app_env: str = "development"
    app_debug: bool = True
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    frontend_url: str = "http://localhost:3000"

    # Database — Railway provides DATABASE_URL with postgresql:// scheme;
    # we normalise it to postgresql+asyncpg:// for SQLAlchemy's async driver.
    database_url: str = "postgresql+asyncpg://overture:overture@localhost:5432/overture"
    redis_url: str = "redis://localhost:6379/0"

    @model_validator(mode="after")
    def _normalize_database_url(self) -> "Settings":
        url = self.database_url
        if url.startswith("postgresql://"):
            self.database_url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgres://"):
            self.database_url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        return self

    # LLM Providers
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    default_llm_provider: str = "openai"
    openai_model: str = "gpt-4.1"
    anthropic_model: str = "claude-sonnet-4-6"

    # Data Sources
    alpha_vantage_api_key: str = ""
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    news_api_key: str = ""

    # RL Training
    rl_replay_buffer_size: int = 10000
    rl_batch_size: int = 64
    rl_learning_rate: float = 0.001

    # Auth
    jwt_secret: str = "overture-change-me-in-production-2026"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
