from pathlib import Path

import pytest

from elenchos.config import (
    ElenchosSettings,
    normalize_openai_base_url,
    resolve_provider_endpoint,
)


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


def test_resolve_provider_endpoint_from_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(
        "ELENCHOS_OLLAMA_BASE_URL",
        "http://remote-ollama:11434/v1",
    )
    endpoint = resolve_provider_endpoint("ollama")
    assert endpoint.base_url == "http://remote-ollama:11434/v1"
    assert endpoint.api_key is None


def test_resolve_provider_endpoint_env_overrides_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    config_dir = tmp_path / "elenchos"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        "providers:\n  ollama:\n    base_url: http://file-host:11434\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ELENCHOS_DATA_DIR", str(config_dir))
    monkeypatch.setenv("ELENCHOS_OLLAMA_BASE_URL", "http://env-host:11434")

    settings = ElenchosSettings()
    endpoint = resolve_provider_endpoint("ollama", settings=settings)

    assert endpoint.base_url == "http://env-host:11434/v1"


def test_resolve_provider_endpoint_from_file(tmp_path: Path):
    config_dir = tmp_path / "elenchos"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        "providers:\n"
        "  ollama:\n"
        "    base_url: http://file-host:11434\n"
        "    api_key: secret\n",
        encoding="utf-8",
    )

    settings = ElenchosSettings(data_dir=config_dir)
    endpoint = resolve_provider_endpoint("ollama", settings=settings)

    assert endpoint.base_url == "http://file-host:11434/v1"
    assert endpoint.api_key == "secret"
