from pathlib import Path

import textwrap

from gai.template_interface import build_template_interface


def _base_config(root: Path) -> dict[str, list[str]]:
    return {
        "project-template-paths": [str(root)],
        "user-template-paths": [],
        "builtin-template-paths": [],
    }


def test_build_template_interface_detects_iocm(tmp_path):
    template_root = tmp_path / "templates"
    template_root.mkdir()
    template_path = template_root / "prompts" / "sample.j2"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(
        textwrap.dedent(
            """
            {{ I_document }}
            {{ C_style }}
            {{ M_model }}
            {{ helper_value }}
            <O_main>answer</O_main>
            """
        ).strip()
    )

    interface = build_template_interface(_base_config(template_root), "prompts/sample")

    assert interface.inputs == {"I_document": "document"}
    assert interface.controls == {"C_style": "style"}
    assert interface.mechanisms == {"M_model": "model"}
    assert "helper_value" in interface.other_variables
    assert "O_main" in interface.outputs


def test_build_template_interface_handles_empty_sections(tmp_path):
    template_root = tmp_path / "templates"
    template_root.mkdir()
    template_path = template_root / "plain.j2"
    template_path.write_text("Static content only")

    interface = build_template_interface(_base_config(template_root), "plain")

    assert interface.inputs == {}
    assert interface.controls == {}
    assert interface.mechanisms == {}
    assert interface.outputs == set()
    assert interface.other_variables == set()
