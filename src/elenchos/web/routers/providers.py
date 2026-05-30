import logging

from fastapi import APIRouter, HTTPException

from elenchos.providers.registry import get_provider, list_provider_names
from elenchos.web.deps import SettingsDep
from elenchos.web.schemas import ModelsResponse, ProviderResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["providers"])


@router.get("/providers", response_model=list[ProviderResponse])
def list_providers(settings: SettingsDep) -> list[ProviderResponse]:
    providers: list[ProviderResponse] = []
    for name in list_provider_names(settings):
        provider = get_provider(name, settings)
        providers.append(
            ProviderResponse(
                name=name,
                base_url=provider.base_url,
                healthy=provider.health_check(),
            )
        )
    return providers


@router.get("/providers/{name}/models", response_model=ModelsResponse)
def list_provider_models(name: str, settings: SettingsDep) -> ModelsResponse:
    known_names = list_provider_names(settings)
    if name not in known_names:
        known = ", ".join(known_names) or "(none)"
        raise HTTPException(
            status_code=404,
            detail=f"Unknown provider {name!r}. Known providers: {known}",
        )

    try:
        provider = get_provider(name, settings)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not provider.health_check():
        raise HTTPException(
            status_code=502,
            detail=(
                f"Provider {provider.name!r} is unhealthy at {provider.base_url}."
            ),
        )

    try:
        models = provider.list_models()
    except Exception as exc:
        logger.exception("Failed to list models for %s", name)
        raise HTTPException(
            status_code=502,
            detail=f"Error listing models: {exc}",
        ) from exc

    return ModelsResponse(models=models)
