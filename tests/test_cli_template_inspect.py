from types import SimpleNamespace

from gai.cli import TemplateInterface, handle_template_inspect


def test_handle_template_inspect_outputs_sections(monkeypatch, capsys):
    interface = TemplateInterface(
        logical_name="prompts/sample",
        inputs={"I_document": "document"},
        controls={"C_style": "style"},
        mechanisms={"M_model": "model"},
        outputs={"O_main"},
        other_variables={"helper"},
    )

    monkeypatch.setattr("gai.cli.build_template_interface", lambda _config, _name: interface)

    parsed = SimpleNamespace(logical_name="prompts/sample")
    handle_template_inspect({}, parsed)

    captured = capsys.readouterr().out
    assert "I_document" in captured
    assert "O_main" in captured
    assert "Other variables" in captured
