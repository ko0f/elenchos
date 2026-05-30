from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Legacy LM Studio runner settings."""

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


class ElenchosSettings(BaseSettings):
    """Provider and data-dir settings (env prefix ELENCHOS_)."""

    model_config = SettingsConfigDict(
        env_prefix="ELENCHOS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Path.home() / ".elenchos"
    request_timeout_s: float = 300.0
    ollama_base_url: str | None = None
    ollama_api_key: str | None = None


@dataclass(frozen=True)
class ProviderEndpoint:
    base_url: str
    api_key: str | None = None


def normalize_openai_base_url(url: str) -> str:
    normalized = url.strip().rstrip("/")
    if not normalized.endswith("/v1"):
        return f"{normalized}/v1"
    return normalized


def load_yaml_config(settings: ElenchosSettings | None = None) -> dict:
    settings = settings or ElenchosSettings()
    config_path = settings.data_dir / "config.yaml"
    if not config_path.is_file():
        return {}

    with config_path.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)

    return payload if isinstance(payload, dict) else {}


def resolve_provider_endpoint(
    name: str,
    *,
    settings: ElenchosSettings | None = None,
    default_base_url: str | None = None,
) -> ProviderEndpoint:
    """Resolve provider endpoint: env > config.yaml > default."""
    settings = settings or ElenchosSettings()
    yaml_config = load_yaml_config(settings)
    provider_yaml = (yaml_config.get("providers") or {}).get(name) or {}

    env_base_url = getattr(settings, f"{name}_base_url", None)
    env_api_key = getattr(settings, f"{name}_api_key", None)

    base_url = env_base_url or provider_yaml.get("base_url") or default_base_url
    if not base_url:
        raise ValueError(
            f"No base URL configured for provider {name!r}. "
            f"Set ELENCHOS_{name.upper()}_BASE_URL or "
            f"{settings.data_dir / 'config.yaml'} providers.{name}.base_url"
        )

    api_key = env_api_key or provider_yaml.get("api_key")

    return ProviderEndpoint(
        base_url=normalize_openai_base_url(str(base_url)),
        api_key=str(api_key) if api_key else None,
    )
