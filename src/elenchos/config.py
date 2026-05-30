import logging
import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


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
    max_tokens: int = 131_072


class ElenchosSettings(BaseSettings):
    """Global settings (env prefix ELENCHOS_). Provider endpoints live in config.yaml."""

    model_config = SettingsConfigDict(
        env_prefix="ELENCHOS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Path.home() / ".elenchos"
    request_timeout_s: float = 300.0


@dataclass(frozen=True)
class ProviderDefaults:
    base_url: str
    api_key_env: str | None = None


BUILTIN_PROVIDERS: dict[str, ProviderDefaults] = {
    "ollama": ProviderDefaults(base_url="http://localhost:11434"),
    "lmstudio": ProviderDefaults(base_url="http://localhost:1234/v1"),
    "openrouter": ProviderDefaults(
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
    ),
}


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


def list_configured_provider_names(
    settings: ElenchosSettings | None = None,
) -> list[str]:
    """Return built-in plus user-defined provider names from config.yaml."""
    settings = settings or ElenchosSettings()
    yaml_config = load_yaml_config(settings)
    yaml_providers = (yaml_config.get("providers") or {}).keys()
    names = set(BUILTIN_PROVIDERS.keys()) | set(yaml_providers)
    return sorted(names)


def _provider_yaml(name: str, yaml_config: dict) -> dict:
    providers = yaml_config.get("providers") or {}
    provider_yaml = providers.get(name) or {}
    return provider_yaml if isinstance(provider_yaml, dict) else {}


def _resolve_api_key(
    name: str,
    *,
    provider_yaml: dict,
    defaults: ProviderDefaults | None,
    cli_api_key: str | None = None,
) -> str | None:
    """Resolve API key: CLI > api_key_env from config.yaml or built-in defaults."""
    if provider_yaml.get("api_key"):
        logger.warning(
            "Ignoring providers.%s.api_key in config.yaml; set api_key_env instead.",
            name,
        )

    if cli_api_key:
        return cli_api_key

    api_key_env = provider_yaml.get("api_key_env") or (
        defaults.api_key_env if defaults else None
    )
    if api_key_env:
        return os.environ.get(str(api_key_env))

    return None


@dataclass(frozen=True)
class JudgeConfig:
    model: str | None = None
    mode: str = "pairwise"


def resolve_run_defaults(
    *,
    settings: ElenchosSettings | None = None,
    cli_concurrency: int | None = None,
    cli_max_retries: int | None = None,
) -> tuple[int, int]:
    """Resolve run concurrency and retry limits: CLI > config.yaml > built-ins."""
    settings = settings or ElenchosSettings()
    yaml_config = load_yaml_config(settings)
    defaults = yaml_config.get("defaults") or {}
    if not isinstance(defaults, dict):
        defaults = {}

    concurrency = (
        cli_concurrency
        if cli_concurrency is not None
        else defaults.get("concurrency", 1)
    )
    max_retries = (
        cli_max_retries
        if cli_max_retries is not None
        else defaults.get("max_retries", 3)
    )
    return int(concurrency), int(max_retries)


def resolve_judge_config(
    *,
    settings: ElenchosSettings | None = None,
    cli_judge: str | None = None,
    cli_mode: str | None = None,
) -> JudgeConfig:
    """Resolve judge settings: CLI > config.yaml > defaults."""
    settings = settings or ElenchosSettings()
    yaml_config = load_yaml_config(settings)
    judge_yaml = yaml_config.get("judge") or {}
    if not isinstance(judge_yaml, dict):
        judge_yaml = {}

    model = cli_judge or judge_yaml.get("model")
    mode = cli_mode or judge_yaml.get("mode") or "pairwise"
    if mode not in {"pairwise", "rubric"}:
        raise ValueError(
            f"Invalid judge mode {mode!r}; expected 'pairwise' or 'rubric'."
        )

    return JudgeConfig(
        model=str(model) if model else None,
        mode=str(mode),
    )


def resolve_provider_endpoint(
    name: str,
    *,
    settings: ElenchosSettings | None = None,
    default_base_url: str | None = None,
    cli_base_url: str | None = None,
    cli_api_key: str | None = None,
) -> ProviderEndpoint:
    """Resolve provider endpoint: CLI > config.yaml > built-in defaults."""
    settings = settings or ElenchosSettings()
    yaml_config = load_yaml_config(settings)
    provider_yaml = _provider_yaml(name, yaml_config)
    defaults = BUILTIN_PROVIDERS.get(name)

    base_url = (
        cli_base_url
        or provider_yaml.get("base_url")
        or default_base_url
        or (defaults.base_url if defaults else None)
    )
    if not base_url:
        raise ValueError(
            f"No base URL configured for provider {name!r}. "
            f"Set {settings.data_dir / 'config.yaml'} providers.{name}.base_url"
        )

    api_key = _resolve_api_key(
        name,
        provider_yaml=provider_yaml,
        defaults=defaults,
        cli_api_key=cli_api_key,
    )

    return ProviderEndpoint(
        base_url=normalize_openai_base_url(str(base_url)),
        api_key=api_key,
    )
