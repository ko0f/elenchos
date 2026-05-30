from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    lm_studio_base_url: str = "http://localhost:1234/v1"
    lm_studio_api_key: str = "not-needed"
    lm_studio_model: str = ""

    results_dir: str = "results"
    request_timeout_s: float = 300.0
    temperature: float = 0.0
    max_tokens: int = 1024
