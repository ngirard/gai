from types import SimpleNamespace

import pytest

from gai import generation
from gai.exceptions import GenerationError


def test_collect_output_concatenates_chunks():
    chunks = (SimpleNamespace(text=part) for part in ["foo", "bar"])

    assert generation.collect_output(chunks) == "foobar"


def test_extract_between_tags_success():
    text = "pre <O_main>captured</O_main> post"

    assert generation.extract_between_tags(text, "O_main") == "captured"


def test_extract_between_tags_missing_tag():
    with pytest.raises(GenerationError):
        generation.extract_between_tags("no tags here", "O_main")


def test_generate_capture_tag_writes_file(tmp_path, monkeypatch):
    config = {
        "model": "test-model",
        "temperature": 0.1,
        "response-mime-type": "text/plain",
    }

    monkeypatch.setenv("GOOGLE_API_KEY", "test")
    monkeypatch.setattr(generation, "render_user_instruction", lambda *_: "user")
    monkeypatch.setattr(generation, "render_system_instruction", lambda *_: "system")

    def fake_execute(*_args, **_kwargs):
        yield SimpleNamespace(text="prefix <O_main>answer</O_main> suffix")

    class DummyClient:
        def __init__(self, api_key: str):
            self.api_key = api_key

    monkeypatch.setattr(generation.genai, "Client", DummyClient)
    monkeypatch.setattr(generation, "execute_generation_stream", fake_execute)

    output_file = tmp_path / "capture.txt"
    generation.generate(config, {}, capture_tag="O_main", output_file=str(output_file))

    assert output_file.read_text(encoding="utf-8") == "answer"
