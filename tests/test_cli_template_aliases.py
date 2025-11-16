from gai.__main__ import _apply_user_template_override
from gai.cli import parse_template_args_from_list


def test_apply_user_template_override_adds_conf_flag():
    args = ["template", "render"]
    updated = _apply_user_template_override(args, "prompts/sample")

    assert updated[-2:] == ["--conf-user-instruction-template", "prompts/sample"]


def test_apply_user_template_override_skips_existing_flag():
    args = ["--conf-user-instruction-template", "existing"]
    updated = _apply_user_template_override(args, "prompts/sample")

    assert updated == args


def test_template_variable_aliases_inputs_and_controls():
    parsed = parse_template_args_from_list(["--document", "text"])

    assert parsed["document"] == "text"
    assert parsed["I_document"] == "text"
    assert parsed["C_document"] == "text"
