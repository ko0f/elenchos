from openai import OpenAI

from lmbench.config import Settings


def create_client(settings: Settings) -> OpenAI:
    return OpenAI(
        base_url=settings.lm_studio_base_url,
        api_key=settings.lm_studio_api_key,
        timeout=settings.request_timeout_s,
    )


def resolve_model(client: OpenAI, settings: Settings) -> str:
    if settings.lm_studio_model:
        return settings.lm_studio_model

    models = client.models.list()
    if not models.data:
        raise RuntimeError("No models available from LM Studio. Load a model first.")

    return models.data[0].id
