from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from elenchos.cli import app
from elenchos.providers.registry import get_provider

runner = CliRunner()


def test_models_list_unknown_provider():
    result = runner.invoke(app, ["models", "list", "--provider", "missing"])
    assert result.exit_code == 1
    assert "Unknown provider" in result.stdout


@patch("elenchos.cli.get_provider")
def test_models_list_renders_models(mock_get_provider):
    provider = MagicMock()
    provider.name = "lmstudio"
    provider.base_url = "http://localhost:1234/v1"
    provider.health_check.return_value = True
    provider.list_models.return_value = ["qwen2.5-coder-7b", "llama-3.2-3b"]
    mock_get_provider.return_value = provider

    result = runner.invoke(app, ["models", "list", "--provider", "lmstudio"])

    assert result.exit_code == 0
    mock_get_provider.assert_called_once_with("lmstudio")
    assert "qwen2.5-coder-7b" in result.stdout
    assert "llama-3.2-3b" in result.stdout


@patch("elenchos.cli.get_provider")
def test_models_list_unhealthy_provider(mock_get_provider):
    provider = MagicMock()
    provider.name = "openrouter"
    provider.base_url = "https://openrouter.ai/api/v1"
    provider.health_check.return_value = False
    mock_get_provider.return_value = provider

    result = runner.invoke(app, ["models", "list", "--provider", "openrouter"])

    assert result.exit_code == 1
    assert "unhealthy" in result.stdout.lower()


@patch("elenchos.providers.openai_compat.httpx.Client")
def test_openai_compat_provider_list_models(mock_client_cls):
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [{"id": "llama3.1:8b"}, {"id": "mistral:latest"}],
    }
    mock_client.get.return_value = mock_response
    mock_client_cls.return_value = mock_client

    provider = get_provider("ollama")
    models = provider.list_models()

    assert models == ["llama3.1:8b", "mistral:latest"]
    mock_client.get.assert_called_once()
    call_args = mock_client.get.call_args
    assert call_args.args[0].endswith("/models")


@patch("elenchos.providers.openai_compat.httpx.Client")
def test_openai_compat_provider_sends_auth_header(
    mock_client_cls,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_client.get.return_value = mock_response
    mock_client_cls.return_value = mock_client

    provider = get_provider("openrouter")
    provider.health_check()

    headers = mock_client.get.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer sk-or-test"
