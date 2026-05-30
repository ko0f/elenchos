import pytest

from elenchos.models import build_messages, default_generation_params
from elenchos.providers.registry import get_provider

pytestmark = pytest.mark.integration


def ollama_available() -> bool:
    try:
        provider = get_provider("ollama")
        return provider.health_check()
    except Exception:
        return False


@pytest.fixture
def ollama_model() -> str:
    provider = get_provider("ollama")
    models = provider.list_models()
    if not models:
        pytest.skip("No Ollama models available")
    return models[0]


_SKIP_REASON = "Ollama not configured or unreachable"


@pytest.mark.skipif(not ollama_available(), reason=_SKIP_REASON)
def test_ollama_health_check():
    provider = get_provider("ollama")
    assert provider.health_check() is True


@pytest.mark.skipif(not ollama_available(), reason=_SKIP_REASON)
def test_ollama_complete_returns_text(ollama_model: str):
    provider = get_provider("ollama")
    messages = build_messages("Reply with exactly one word: hello")
    completion = provider.complete(
        ollama_model,
        messages,
        default_generation_params(),
    )
    assert completion.text.strip()
    assert completion.latency_ms >= 0
