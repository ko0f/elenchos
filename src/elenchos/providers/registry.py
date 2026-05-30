from elenchos.config import ElenchosSettings, resolve_provider_endpoint
from elenchos.providers.openai_compat import OpenAICompatProvider

_DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"


def list_provider_names() -> list[str]:
    return ["ollama"]


def get_provider(
    name: str,
    settings: ElenchosSettings | None = None,
) -> OpenAICompatProvider:
    settings = settings or ElenchosSettings()

    if name == "ollama":
        endpoint = resolve_provider_endpoint(
            "ollama",
            settings=settings,
            default_base_url=_DEFAULT_OLLAMA_BASE_URL,
        )
        return OpenAICompatProvider(
            name="ollama",
            base_url=endpoint.base_url,
            api_key=endpoint.api_key,
            timeout=settings.request_timeout_s,
        )

    known = ", ".join(list_provider_names()) or "(none)"
    raise ValueError(f"Unknown provider {name!r}. Known providers: {known}")
