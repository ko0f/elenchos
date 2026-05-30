from pathlib import Path

import pytest

from elenchos.config import (
    BUILTIN_PROVIDERS,
    ElenchosSettings,
    list_configured_provider_names,
    normalize_openai_base_url,
    resolve_judge_config,
    resolve_provider_endpoint,
    resolve_run_defaults,
)
from elenchos.providers.registry import get_provider, list_provider_names


@pytest.fixture
def isolated_settings(tmp_path: Path) -> ElenchosSettings:
    """Settings pinned to an empty data dir so resolution does not leak host config."""
    return ElenchosSettings(data_dir=tmp_path)


def test_normalize_openai_base_url_adds_v1_suffix():
    assert (
        normalize_openai_base_url("http://ollama.example.com:11434")
        == "http://ollama.example.com:11434/v1"
    )


def test_normalize_openai_base_url_keeps_existing_v1():
    assert (
        normalize_openai_base_url("http://ollama.example.com:11434/v1")
        == "http://ollama.example.com:11434/v1"
    )


def test_resolve_provider_endpoint_cli_overrides_file(tmp_path: Path):
    config_dir = tmp_path / "elenchos"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        "providers:\n  ollama:\n    base_url: http://file-host:11434\n",
        encoding="utf-8",
    )

    settings = ElenchosSettings(data_dir=config_dir)
    endpoint = resolve_provider_endpoint(
        "ollama",
        settings=settings,
        cli_base_url="http://cli-host:11434",
    )

    assert endpoint.base_url == "http://cli-host:11434/v1"


def test_resolve_provider_endpoint_from_file(tmp_path: Path):
    config_dir = tmp_path / "elenchos"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        "providers:\n  ollama:\n    base_url: http://file-host:11434\n",
        encoding="utf-8",
    )

    settings = ElenchosSettings(data_dir=config_dir)
    endpoint = resolve_provider_endpoint("ollama", settings=settings)

    assert endpoint.base_url == "http://file-host:11434/v1"
    assert endpoint.api_key is None


def test_resolve_provider_endpoint_uses_builtin_defaults(
    isolated_settings: ElenchosSettings,
):
    endpoint = resolve_provider_endpoint("openrouter", settings=isolated_settings)
    assert endpoint.base_url == "https://openrouter.ai/api/v1"


def test_resolve_provider_endpoint_api_key_from_yaml(
    isolated_settings: ElenchosSettings,
):
    config_path = isolated_settings.data_dir / "config.yaml"
    config_path.write_text(
        "providers:\n  openrouter:\n    api_key: sk-or-test\n",
        encoding="utf-8",
    )
    endpoint = resolve_provider_endpoint("openrouter", settings=isolated_settings)
    assert endpoint.api_key == "sk-or-test"


def test_resolve_provider_endpoint_cli_api_key_overrides_yaml(
    isolated_settings: ElenchosSettings,
):
    config_path = isolated_settings.data_dir / "config.yaml"
    config_path.write_text(
        "providers:\n  openrouter:\n    api_key: from-yaml\n",
        encoding="utf-8",
    )
    endpoint = resolve_provider_endpoint(
        "openrouter",
        settings=isolated_settings,
        cli_api_key="from-cli",
    )
    assert endpoint.api_key == "from-cli"


def test_list_provider_names_includes_builtins(
    isolated_settings: ElenchosSettings,
):
    names = list_provider_names(isolated_settings)
    assert names == sorted(BUILTIN_PROVIDERS.keys())


def test_list_provider_names_includes_yaml_providers(tmp_path: Path):
    config_dir = tmp_path / "elenchos"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        "providers:\n  custom:\n    base_url: http://localhost:9999/v1\n",
        encoding="utf-8",
    )
    settings = ElenchosSettings(data_dir=config_dir)
    names = list_configured_provider_names(settings)
    assert "custom" in names
    assert "ollama" in names


def test_get_provider_ollama_defaults(isolated_settings: ElenchosSettings):
    provider = get_provider("ollama", settings=isolated_settings)
    assert provider.name == "ollama"
    assert provider.base_url == "http://localhost:11434/v1"
    assert provider.api_key is None


def test_get_provider_lmstudio_defaults(isolated_settings: ElenchosSettings):
    provider = get_provider("lmstudio", settings=isolated_settings)
    assert provider.name == "lmstudio"
    assert provider.base_url == "http://localhost:1234/v1"
    assert provider.api_key is None


def test_get_provider_openrouter_reads_api_key_from_yaml(
    isolated_settings: ElenchosSettings,
):
    config_path = isolated_settings.data_dir / "config.yaml"
    config_path.write_text(
        "providers:\n  openrouter:\n    api_key: sk-or-secret\n",
        encoding="utf-8",
    )
    provider = get_provider("openrouter", settings=isolated_settings)
    assert provider.name == "openrouter"
    assert provider.base_url == "https://openrouter.ai/api/v1"
    assert provider.api_key == "sk-or-secret"


def test_get_provider_custom_from_yaml(tmp_path: Path):
    config_dir = tmp_path / "elenchos"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        "providers:\n  custom:\n    base_url: http://custom-host:8080/v1\n",
        encoding="utf-8",
    )
    settings = ElenchosSettings(data_dir=config_dir)
    provider = get_provider("custom", settings=settings)
    assert provider.name == "custom"
    assert provider.base_url == "http://custom-host:8080/v1"


def test_get_provider_unknown_raises():
    with pytest.raises(ValueError, match="Unknown provider"):
        get_provider("not-a-provider")


def test_resolve_judge_config_from_yaml(tmp_path: Path):
    config_dir = tmp_path / "elenchos"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        "judge:\n  model: ollama/llama3.1:8b\n  mode: rubric\n",
        encoding="utf-8",
    )
    settings = ElenchosSettings(data_dir=config_dir)
    judge = resolve_judge_config(settings=settings)
    assert judge.model == "ollama/llama3.1:8b"
    assert judge.mode == "rubric"


def test_resolve_run_defaults_precedence(tmp_path: Path):
    config_dir = tmp_path / "elenchos"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        "defaults:\n  concurrency: 4\n  max_retries: 5\n",
        encoding="utf-8",
    )
    settings = ElenchosSettings(data_dir=config_dir)

    assert resolve_run_defaults(settings=settings) == (4, 5)
    assert resolve_run_defaults(settings=settings, cli_concurrency=2) == (2, 5)
    assert resolve_run_defaults(settings=settings, cli_max_retries=1) == (4, 1)
