from elenchos.config import (
    BUILTIN_PROVIDERS,
    ElenchosSettings,
    get_settings,
    list_configured_provider_names,
    load_yaml_config,
    resolve_provider_endpoint,
)
from elenchos.providers.openai_compat import OpenAICompatProvider


def list_provider_names(
    settings: ElenchosSettings | None = None,
) -> list[str]:
    return list_configured_provider_names(settings)


def get_provider(
    name: str,
    settings: ElenchosSettings | None = None,
) -> OpenAICompatProvider:
    settings = settings or get_settings()
    defaults = BUILTIN_PROVIDERS.get(name)

    if defaults is None:
        yaml_config = load_yaml_config(settings)
        provider_yaml = (yaml_config.get("providers") or {}).get(name)
        if not isinstance(provider_yaml, dict) or not provider_yaml.get("base_url"):
            known = ", ".join(list_provider_names(settings)) or "(none)"
            raise ValueError(
                f"Unknown provider {name!r}. Known providers: {known}"
            )

    default_base_url = defaults.base_url if defaults else None
    endpoint = resolve_provider_endpoint(
        name,
        settings=settings,
        default_base_url=default_base_url,
    )
    return OpenAICompatProvider(
        name=name,
        base_url=endpoint.base_url,
        api_key=endpoint.api_key,
        timeout=settings.request_timeout_s,
    )
