import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR = Path.home() / ".elenchos"

_cli_data_dir: Path | None = None


def set_cli_data_dir(path: Path | None) -> None:
    """Override the data directory for the current CLI invocation."""
    global _cli_data_dir
    _cli_data_dir = path


def _resolve_data_dir() -> Path:
    if _cli_data_dir is not None:
        return _cli_data_dir
    return DEFAULT_DATA_DIR


@dataclass
class Settings:
    """Legacy LM Studio runner settings."""

    lm_studio_base_url: str = "http://localhost:1234/v1"
    lm_studio_api_key: str = "not-needed"
    lm_studio_model: str = ""
    results_dir: str = "results"
    request_timeout_s: float = 300.0
    temperature: float = 0.0
    max_tokens: int = 131_072


@dataclass
class ElenchosSettings:
    data_dir: Path = field(default_factory=_resolve_data_dir)
    request_timeout_s: float = 300.0


def get_settings() -> ElenchosSettings:
    return ElenchosSettings()


@dataclass(frozen=True)
class ProviderDefaults:
    base_url: str
    requires_api_key: bool = False


BUILTIN_PROVIDERS: dict[str, ProviderDefaults] = {
    "ollama": ProviderDefaults(base_url="http://localhost:11434"),
    "lmstudio": ProviderDefaults(base_url="http://localhost:1234/v1"),
    "openrouter": ProviderDefaults(
        base_url="https://openrouter.ai/api/v1",
        requires_api_key=True,
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
    settings = settings or get_settings()
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
    settings = settings or get_settings()
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
    cli_api_key: str | None = None,
) -> str | None:
    """Resolve API key: CLI > config.yaml providers.{name}.api_key."""
    if cli_api_key:
        return cli_api_key

    api_key = provider_yaml.get("api_key")
    if api_key:
        return str(api_key)

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
    settings = settings or get_settings()
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
    settings = settings or get_settings()
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
    settings = settings or get_settings()
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
        cli_api_key=cli_api_key,
    )

    return ProviderEndpoint(
        base_url=normalize_openai_base_url(str(base_url)),
        api_key=api_key,
    )
