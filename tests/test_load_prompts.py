from pathlib import Path

from elenchos.runner import load_prompts


def test_load_prompts(tmp_path: Path):
    prompts_file = tmp_path / "prompts.jsonl"
    prompts_file.write_text(
        '{"id": "one", "prompt": "Hello"}\n\n{"prompt": "World"}\n',
        encoding="utf-8",
    )

    cases = load_prompts(prompts_file)

    assert len(cases) == 2
    assert cases[0].id == "one"
    assert cases[0].prompt == "Hello"
    assert cases[1].id == "3"
    assert cases[1].prompt == "World"
