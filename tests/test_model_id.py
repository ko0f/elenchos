import pytest

from elenchos.models import ModelId, build_messages, parse_model_id


def test_parse_model_id_simple():
    model_id = parse_model_id("ollama/llama3.1:8b")
    assert model_id == ModelId(provider="ollama", model="llama3.1:8b")
    assert model_id.qualified == "ollama/llama3.1:8b"


def test_parse_model_id_nested_model_path():
    model_id = parse_model_id("openrouter/anthropic/claude-sonnet-4-6")
    assert model_id.provider == "openrouter"
    assert model_id.model == "anthropic/claude-sonnet-4-6"


@pytest.mark.parametrize(
    "value",
    [
        "no-slash",
        "/model-only",
        "provider/",
        "",
        "   ",
    ],
)
def test_parse_model_id_invalid(value: str):
    with pytest.raises(ValueError, match="provider/model"):
        parse_model_id(value)


def test_build_messages_user_only():
    messages = build_messages("Hello")
    assert len(messages) == 1
    assert messages[0].role == "user"
    assert messages[0].content == "Hello"


def test_build_messages_with_system():
    messages = build_messages("Hello", system="You are helpful.")
    assert len(messages) == 2
    assert messages[0].role == "system"
    assert messages[0].content == "You are helpful."
    assert messages[1].role == "user"
